"""Entrypoint for the signal ingestion service application."""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Callable, Coroutine, cast

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends, FastAPI, Request, Response
from backend.shared.security import require_status_api_key
from fastapi.middleware.cors import CORSMiddleware

from .database import get_session, init_db
from backend.shared.db import run_migrations_if_needed
from .scheduler import create_scheduler
from .ingestion import ingest
from . import dedup
from . import trending as trending_mod
from .logging_config import configure_logging
from .settings import settings
from backend.shared.config import settings as shared_settings
from backend.shared.tracing import configure_tracing
from backend.shared.profiling import add_profiling
from backend.shared.metrics import register_metrics
from backend.shared.security import add_security_headers
from backend.shared.responses import json_cached
from backend.shared.http import close_async_clients

from backend.shared import add_error_handlers, configure_sentry

configure_logging()
logger = logging.getLogger(__name__)
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=shared_settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
configure_tracing(app, settings.app_name)
configure_sentry(app, settings.app_name)
add_profiling(app)
add_error_handlers(app)
register_metrics(app)
add_security_headers(app)


@lru_cache(maxsize=256)
def _cached_user(x_user: str | None, client_host: str) -> str:
    """Return user identifier from ``x_user`` or ``client_host``."""
    return x_user or client_host


scheduler = create_scheduler()


def _identify_user(request: Request) -> str:
    """Return identifier for logging, header ``X-User`` or client IP."""
    client_host = cast(str, request.client.host)
    return _cached_user(request.headers.get("X-User"), client_host)


@app.on_event("startup")
async def startup() -> None:
    """Initialize resources."""
    await run_migrations_if_needed("backend/shared/db/alembic_signal_ingestion.ini")
    await init_db()
    dedup.initialize(settings.dedup_ttl)
    scheduler.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    """Stop background tasks."""
    scheduler.shutdown()
    await close_async_clients()


@app.middleware("http")
async def add_correlation_id(
    request: Request,
    call_next: Callable[[Request], Coroutine[None, None, Response]],
) -> Response:
    """Ensure every request contains a correlation ID."""
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


@app.get("/health")
async def health() -> Response:
    """Return service liveness."""
    return json_cached({"status": "ok"})


@app.get("/ready")
async def ready(request: Request) -> Response:
    """Return service readiness."""
    require_status_api_key(request)
    return json_cached({"status": "ready"})


@app.post("/ingest")
async def ingest_signals(
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Trigger signal ingestion."""
    await ingest(session)
    return {"status": "ingested"}


@app.get("/trending")
async def trending(limit: int = 10, offset: int = 0) -> list[str]:
    """Return trending keywords with pagination."""
    return trending_mod.get_top_keywords(limit, offset)


if __name__ == "__main__":  # pragma: no cover
    import asyncio
    import uvloop
    import uvicorn

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    uvicorn.run(
        "signal_ingestion.main:app",
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level,
    )
