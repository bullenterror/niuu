"""Cross-harness verification for canonical step telemetry."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import contextmanager

import pytest

from niuu.ports.cli import CLITransport
from ravn.adapters.executors.cli import CliTransportExecutor
from ravn.agent import RavnAgent
from ravn.domain.models import Session, StreamEvent, StreamEventType, TokenUsage
from ravn.harness_telemetry import HARNESS_STEP_EVENT
from ravn.ports.llm import LLMPort
from tests.ravn.fixtures.fakes import InMemoryChannel
from tests.test_ravn.conftest import AllowAllPermission


class _RecordingSpan:
    def set_attribute(self, _name: str, _value: object) -> None:
        return None


class _RecordingTelemetry:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    @contextmanager
    def span(self, _name: str, **_kwargs: object):
        yield _RecordingSpan()

    def event(self, name: str, **kwargs: object) -> None:
        self.events.append((name, kwargs))

    def set_attributes(self, _attributes: dict[str, object]) -> None:
        return None

    def count(self, *_args: object, **_kwargs: object) -> None:
        return None

    def duration(self, *_args: object, **_kwargs: object) -> None:
        return None

    def record(self, *_args: object, **_kwargs: object) -> None:
        return None

    def gauge(self, *_args: object, **_kwargs: object) -> None:
        return None

    def inject(self) -> dict[str, str]:
        return {}


class _NoTextLLM(LLMPort):
    async def stream(self, *_args: object, **_kwargs: object) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(
            type=StreamEventType.MESSAGE_DONE,
            usage=TokenUsage(
                input_tokens=3,
                output_tokens=0,
                cache_read_tokens=4,
                cache_write_tokens=2,
                thinking_tokens=1,
            ),
        )

    async def generate(self, *_args: object, **_kwargs: object):
        raise AssertionError("generate is not used by a normal harness step")


class _CliTransport(CLITransport):
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_message(self, _content: str) -> None:
        self._last_result = {
            "type": "result",
            "result": "complete",
            "stop_reason": "end_turn",
            "modelUsage": {
                "test-model": {
                    "inputTokens": 3,
                    "outputTokens": 1,
                    "cacheReadInputTokens": 4,
                    "cacheCreationInputTokens": 2,
                    "thinkingTokens": 1,
                }
            },
        }
        await self._emit(self._last_result)

    @property
    def session_id(self) -> str | None:
        return None

    @property
    def last_result(self) -> dict | None:
        return self._last_result

    @property
    def is_alive(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_native_and_cli_emit_one_canonical_step_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry = _RecordingTelemetry()
    monkeypatch.setattr("ravn.agent.get_observability", lambda: telemetry)
    monkeypatch.setattr("ravn.adapters.executors.cli.get_observability", lambda: telemetry)
    monkeypatch.setattr("ravn.harness_telemetry.get_observability", lambda: telemetry)

    native = RavnAgent(
        llm=_NoTextLLM(),
        tools=[],
        channel=InMemoryChannel(),
        permission=AllowAllPermission(),
        system_prompt="test system",
        model="test-model",
        max_tokens=64,
        max_iterations=1,
        task_id="native-task",
    )
    await native.run_turn("test")

    cli = CliTransportExecutor(
        transport_adapter="tests.test_ravn.test_harness_telemetry._CliTransport"
    ).build(
        channel=InMemoryChannel(),
        system_prompt="test system",
        session=Session(),
        model="test-model",
        max_iterations=1,
        checkpoint_port=None,
        task_id="cli-task",
        persona="tester",
        workspace_dir="/tmp/workspace",
        permission_mode="workspace_write",
        tools=[],
    )
    await cli.run_turn("test")

    records = [kwargs["content"] for name, kwargs in telemetry.events if name == HARNESS_STEP_EVENT]
    assert len(records) == 2
    native_record, cli_record = records
    assert native_record.keys() == cli_record.keys()
    assert native_record["harness_type"] == "native"
    assert cli_record["harness_type"] == "cli-backed"
    assert native_record["context_section_estimates"] is not None
    assert cli_record["context_section_estimates"] is None
    assert native_record["unavailable"]["timing.ttft_ms"] == "no_streamed_text_token"
    assert cli_record["unavailable"]["timing.ttft_ms"] == "no_streamed_text_token"
    for field in (
        "step_id",
        "phase",
        "model",
        "provider",
        "compaction_applied",
        "provider_duration_ms",
        "tool_wall_time_ms",
        "usage",
        "stop_reason",
        "recovery_state",
    ):
        assert field in native_record


@pytest.mark.asyncio
async def test_cross_harness_step_events_export_without_content_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from niuu.observability import Observability

    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = Observability(
        tracer_provider=tracer_provider,
        meter_provider=MeterProvider(),
        capture_content=False,
    )
    monkeypatch.setattr("ravn.agent.get_observability", lambda: telemetry)
    monkeypatch.setattr("ravn.adapters.executors.cli.get_observability", lambda: telemetry)
    monkeypatch.setattr("ravn.harness_telemetry.get_observability", lambda: telemetry)

    native = RavnAgent(
        llm=_NoTextLLM(),
        tools=[],
        channel=InMemoryChannel(),
        permission=AllowAllPermission(),
        system_prompt="test system",
        model="test-model",
        max_tokens=64,
        max_iterations=1,
        task_id="native-task",
    )
    await native.run_turn("test")

    cli = CliTransportExecutor(
        transport_adapter="tests.test_ravn.test_harness_telemetry._CliTransport"
    ).build(
        channel=InMemoryChannel(),
        system_prompt="test system",
        session=Session(),
        model="test-model",
        max_iterations=1,
        checkpoint_port=None,
        task_id="cli-task",
        persona="tester",
        workspace_dir="/tmp/workspace",
        permission_mode="workspace_write",
        tools=[],
    )
    await cli.run_turn("test")

    events = [
        event
        for span in exporter.get_finished_spans()
        for event in span.events
        if event.name == HARNESS_STEP_EVENT
    ]
    assert len(events) == 2
    for event in events:
        attributes = event.attributes
        assert "ravn.content" not in attributes
        assert attributes["ravn.harness.context.section_estimates.available"] in (True, False)
        assert attributes["gen_ai.usage.cache_read_tokens"] == 4
        assert attributes["gen_ai.usage.cache_write_tokens"] == 2
        assert attributes["gen_ai.usage.thinking_tokens"] == 1

    native_event = next(
        event for event in events if event.attributes["ravn.harness.type"] == "native"
    )
    cli_event = next(
        event for event in events if event.attributes["ravn.harness.type"] == "cli-backed"
    )
    assert native_event.attributes["ravn.harness.context.section_estimates.available"] is True
    assert "ravn.harness.context.section_estimates" in native_event.attributes
    assert cli_event.attributes["ravn.harness.context.section_estimates.available"] is False
    assert (
        cli_event.attributes[
            "ravn.harness.context.section_estimates.unavailable_reason"
        ]
        == "cli_transport_does_not_expose_prompt_sections"
    )
    assert any(
        span.name == "ravn harness step" and native_event in span.events
        for span in exporter.get_finished_spans()
    )

    telemetry.shutdown()
