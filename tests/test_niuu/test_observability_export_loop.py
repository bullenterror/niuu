"""Telemetry export must not export the logs the export itself produces.

Live on Ting at debug level, urllib3 logged every OTLP log post and those
records were exported in turn: ~145 lines a second, 99.7% of them urllib3.
"""

from __future__ import annotations

import logging

import pytest

from niuu import observability as obs_module
from niuu.domain.observability import ObservabilityConfig


def _record(thread_name: str, *, name: str = "urllib3.connectionpool") -> logging.LogRecord:
    record = logging.LogRecord(name, logging.DEBUG, __file__, 1, "POST /otlp/v1/logs", (), None)
    record.threadName = thread_name
    return record


@pytest.mark.parametrize(
    "thread_name",
    [
        "OtelBatchLogRecordProcessor",
        "OtelBatchSpanRecordProcessor",
        "OtelPeriodicExportingMetricReader",
    ],
)
def test_records_from_export_threads_are_kept_off_otlp(thread_name: str) -> None:
    assert obs_module._not_from_export_threads(_record(thread_name)) is False


def test_application_records_are_exported_whatever_their_logger() -> None:
    """urllib3 traffic the application makes is still exported; only the export's own is not."""
    assert obs_module._not_from_export_threads(_record("MainThread")) is True
    assert obs_module._not_from_export_threads(_record("ThreadPoolExecutor-0_0")) is True


def test_the_configured_otlp_handler_applies_the_filter() -> None:
    pytest.importorskip("opentelemetry.sdk")
    for module in (
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        "opentelemetry.exporter.otlp.proto.http.metric_exporter",
        "opentelemetry.exporter.otlp.proto.http._log_exporter",
    ):
        pytest.importorskip(module, exc_type=ImportError)
    telemetry = obs_module.configure_observability(
        ObservabilityConfig(
            enabled=True,
            trace_endpoint="http://127.0.0.1:4317",
            metric_endpoint="http://127.0.0.1:4318/v1/metrics",
            log_endpoint="http://127.0.0.1:4318/v1/logs",
            insecure=True,
        ),
        component="test",
    )
    handler = telemetry._log_handler

    assert handler.filter(_record("OtelBatchLogRecordProcessor")) is False
    assert handler.filter(_record("MainThread")) is not False
