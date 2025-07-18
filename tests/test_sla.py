"""Tests for SLA monitoring logic."""

from __future__ import annotations

from pathlib import Path
import sys
import types
import os

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "backend" / "monitoring" / "src")
)

otel_mod = types.ModuleType("opentelemetry.exporter.otlp.proto.http.trace_exporter")
otel_mod.OTLPSpanExporter = object  # type: ignore[attr-defined]
sys.modules.setdefault(
    "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    otel_mod,
)
os.makedirs("/run/secrets", exist_ok=True)

from monitoring import main  # noqa: E402


def test_check_sla_triggers_alert(monkeypatch):
    """Alert should be triggered when average latency is high."""
    triggered = {}

    def fake_trigger(duration):
        triggered["hours"] = duration

    monkeypatch.setattr(main, "trigger_sla_violation", fake_trigger)

    monkeypatch.setattr(main, "_record_latencies", lambda: [7200.0, 10800.0])
    recorded = []

    class DummyStore:
        def add_latency(self, metric):
            recorded.append(metric)

    monkeypatch.setattr(main, "metrics_store", DummyStore())
    monkeypatch.setattr(main.settings, "SLA_THRESHOLD_HOURS", 2)
    avg = main._check_sla()
    assert triggered["hours"] == avg / 3600
    assert avg == 9000.0
    assert len(recorded) == 2


def test_check_sla_below_threshold(monkeypatch):
    """No alert should be sent when average latency is low."""
    monkeypatch.setattr(main, "_record_latencies", lambda: [60.0, 30.0])
    monkeypatch.setattr(main, "metrics_store", object())
    monkeypatch.setattr(main.settings, "SLA_THRESHOLD_HOURS", 2)
    called = []

    def fake_trigger(duration):
        called.append(duration)

    monkeypatch.setattr(main, "trigger_sla_violation", fake_trigger)
    avg = main._check_sla()
    assert called == []
    assert avg == 45.0
