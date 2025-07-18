"""Tests for :mod:`backend.optimization.metrics`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.optimization.metrics import MetricsAnalyzer, ResourceMetric


def test_average_cpu_memory() -> None:
    """Validate average CPU and memory calculations."""
    metrics = [
        ResourceMetric(
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
            cpu_percent=10 * i,
            memory_mb=256.0,
        )
        for i in range(4)
    ]
    analyzer = MetricsAnalyzer(metrics)
    assert analyzer.average_cpu() == sum(10 * i for i in range(4)) / 4
    assert analyzer.average_memory() == 256.0


def test_top_recommendations() -> None:
    """Ensure prioritized recommendations are returned."""
    metrics = [
        ResourceMetric(
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
            cpu_percent=90,
            memory_mb=2048,
        )
        for i in range(15)
    ]
    analyzer = MetricsAnalyzer(metrics)
    recs = analyzer.top_recommendations()
    assert recs
    assert any("CPU" in r for r in recs)
    assert len(recs) <= 3
