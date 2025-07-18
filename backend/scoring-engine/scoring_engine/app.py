"""FastAPI application exposing scoring API."""

# mypy: ignore-errors

from __future__ import annotations

import os
import uuid
import asyncio
import logging
import json
from datetime import datetime
from threading import Event, Thread
from pathlib import Path
from typing import Any, Callable, Coroutine, cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from backend.shared.metrics import register_metrics
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.shared.config import settings
from backend.shared.tracing import configure_tracing
from backend.shared.profiling import add_profiling
from backend.shared.logging import configure_logging
from backend.shared import add_error_handlers, configure_sentry
from backend.shared.kafka import KafkaConsumerWrapper, SchemaRegistryClient
from backend.shared.db import session_scope
from backend.shared.db.models import Embedding
from .scoring import Signal, calculate_score
from .weight_repository import get_weights, update_weights, get_centroid
from .centroid_job import start_centroid_scheduler

# Cache metric keys
CACHE_HIT_KEY = "cache_hits"
CACHE_MISS_KEY = "cache_misses"

# Prometheus metrics
CACHE_HIT_COUNTER = Counter("cache_hits_total", "Number of cache hits")
CACHE_MISS_COUNTER = Counter("cache_misses_total", "Number of cache misses")
SCORE_TIME_HISTOGRAM = Histogram("score_compute_seconds", "Time spent computing score")


class WeightsUpdate(BaseModel):
    """Request payload for updating weight parameters."""

    freshness: float
    engagement: float
    novelty: float
    community_fit: float
    seasonality: float


class ScoreRequest(BaseModel):
    """Request payload for scoring a signal."""

    timestamp: datetime
    engagement_rate: float
    embedding: list[float]
    source: str | None = "global"
    metadata: dict[str, float] | None = None
    centroid: list[float] | None = None
    median_engagement: float | None = None
    topics: list[str] | None = None


configure_logging()
logger = logging.getLogger(__name__)

SERVICE_NAME = os.getenv("SERVICE_NAME", "scoring-engine")
app = FastAPI(title="Scoring Engine")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
configure_tracing(app, SERVICE_NAME)
configure_sentry(app, SERVICE_NAME)
add_profiling(app)
add_error_handlers(app)
register_metrics(app)
REDIS_URL = settings.redis_url
CACHE_TTL_SECONDS = settings.score_cache_ttl
redis_client = Redis.from_url(REDIS_URL)
start_centroid_scheduler()


# Background Kafka consumer setup
_stop_event = Event()
_consumer_thread: Thread | None = None


def _create_consumer() -> KafkaConsumerWrapper:
    """Return Kafka consumer subscribed to the ``signals.ingested`` topic."""
    registry = SchemaRegistryClient(settings.schema_registry_url)
    schema_dir = Path(__file__).resolve().parents[3] / "schemas"
    for path in schema_dir.glob("*.json"):
        with open(path) as fh:
            schema = json.load(fh)
        try:
            registry.register(path.stem, schema)
        except Exception:  # pragma: no cover - ignore duplicates
            pass
    return KafkaConsumerWrapper(
        settings.kafka_bootstrap_servers, registry, ["signals.ingested"]
    )


def consume_signals(stop_event: Event, consumer: KafkaConsumerWrapper) -> None:
    """Persist embeddings from Kafka messages until ``stop_event`` is set."""
    for _, message in consumer:
        if stop_event.is_set():
            break
        embedding = message.get("embedding")
        if embedding is None:
            continue
        source = cast(str, message.get("source", "global"))
        with session_scope() as session:
            session.add(Embedding(source=source, embedding=embedding))
            session.flush()


@app.on_event("startup")
async def start_consumer() -> None:
    """Launch background Kafka consumer."""
    global _consumer_thread
    if os.getenv("KAFKA_SKIP") == "1":
        return
    consumer = _create_consumer()
    _stop_event.clear()
    _consumer_thread = Thread(
        target=consume_signals, args=(_stop_event, consumer), daemon=True
    )
    _consumer_thread.start()


@app.on_event("shutdown")
async def stop_consumer() -> None:
    """Stop background Kafka consumer."""
    _stop_event.set()
    if _consumer_thread is not None:
        _consumer_thread.join(timeout=5)


async def trending_factor(topics: list[str]) -> float:
    """Return multiplier based on cached trending topics."""
    if not topics:
        return 1.0
    scores = await asyncio.gather(
        *[redis_client.zscore("trending:keywords", t) for t in topics]
    )
    max_score = max((s or 0.0) for s in scores)
    return 1.0 + max_score / 100.0


def _identify_user(request: Request) -> str:
    """Return identifier for logging, header ``X-User`` or client IP."""
    return cast(str, request.headers.get("X-User", request.client.host))


@app.middleware("http")
async def add_correlation_id(
    request: Request,
    call_next: Callable[[Request], Coroutine[Any, Any, Response]],
) -> Response:
    """Ensure each request includes a correlation ID."""
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    try:
        import sentry_sdk

        sentry_sdk.set_tag("correlation_id", correlation_id)
    except Exception:  # pragma: no cover - sentry optional
        pass
    logger.info(
        "request received",
        extra={
            "correlation_id": correlation_id,
            "user": _identify_user(request),
            "path": request.url.path,
            "method": request.method,
        },
    )
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.get("/weights")
async def read_weights() -> JSONResponse:
    """Return current weighting parameters."""
    weights = await run_in_threadpool(get_weights)
    return JSONResponse(
        {
            "freshness": weights.freshness,
            "engagement": weights.engagement,
            "novelty": weights.novelty,
            "community_fit": weights.community_fit,
            "seasonality": weights.seasonality,
        }
    )


@app.put("/weights")
async def update_weights_endpoint(body: WeightsUpdate) -> JSONResponse:
    """Update weighting parameters via JSON payload."""
    weights = await run_in_threadpool(update_weights, **body.model_dump())
    return JSONResponse(
        {
            "freshness": weights.freshness,
            "engagement": weights.engagement,
            "novelty": weights.novelty,
            "community_fit": weights.community_fit,
            "seasonality": weights.seasonality,
        }
    )


@app.post("/weights/feedback")
async def feedback_weights(body: WeightsUpdate) -> JSONResponse:
    """Update weights from feedback loop."""
    weights = await run_in_threadpool(update_weights, **body.model_dump())
    return JSONResponse(
        {
            "freshness": weights.freshness,
            "engagement": weights.engagement,
            "novelty": weights.novelty,
            "community_fit": weights.community_fit,
            "seasonality": weights.seasonality,
        }
    )


@app.get("/centroid/{source}")
async def centroid_endpoint(source: str) -> JSONResponse:
    """Return current centroid for ``source``."""
    centroid = await run_in_threadpool(get_centroid, source)
    if centroid is None:
        return JSONResponse(status_code=404, content={"detail": "not found"})
    return JSONResponse({"centroid": [float(x) for x in centroid]})


@app.post("/score")
async def score_signal(payload: ScoreRequest) -> JSONResponse:
    """Score a signal and cache hot results."""
    key = json.dumps(payload.model_dump(), sort_keys=True, default=str)
    cached = await redis_client.get(key)
    if cached is not None:
        await redis_client.incr(CACHE_HIT_KEY)
        CACHE_HIT_COUNTER.inc()
        return JSONResponse({"score": float(cached), "cached": True})
    await redis_client.incr(CACHE_MISS_KEY)
    CACHE_MISS_COUNTER.inc()
    signal = Signal(
        source=payload.source or "global",
        timestamp=payload.timestamp,
        engagement_rate=payload.engagement_rate,
        embedding=payload.embedding,
        metadata=payload.metadata or {},
    )
    median_engagement = float(payload.median_engagement or 0)
    topics = payload.topics or []
    factor = await trending_factor(topics)
    with SCORE_TIME_HISTOGRAM.time():
        score = calculate_score(signal, median_engagement, topics, factor)
    await redis_client.setex(key, CACHE_TTL_SECONDS, score)
    return JSONResponse({"score": score, "cached": False})


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service liveness."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Return service readiness."""
    return {"status": "ready"}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "scoring_engine.app:app",
        host="0.0.0.0",
        port=5002,
        log_level="info",
    )
