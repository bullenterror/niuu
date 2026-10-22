"""Tests for the Yggdrasil background realm poller."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from yggdrasil.connection_manager import ConnectionManager
from yggdrasil.models import RealmSummary
from yggdrasil.sse.poller import RealmPoller


@dataclass
class FakeRealmAdapter:
    realm_id: str
    summary: RealmSummary | None = None
    error: Exception | None = None

    async def get_summary(self) -> RealmSummary:
        if self.error is not None:
            raise self.error
        assert self.summary is not None
        return self.summary


@pytest.mark.asyncio
async def test_poller_broadcasts_only_changed_realm_summaries() -> None:
    summary = RealmSummary(realm_id="odin", health_status="healthy", metrics={"nodes": 3})
    adapter = FakeRealmAdapter("odin", summary)
    manager = ConnectionManager(max_clients=1)
    queue = manager.connect("odin")
    poller = RealmPoller([adapter], manager, poll_interval=15.0)

    await poller.poll_once()
    assert await queue.get() == summary

    await poller.poll_once()
    assert queue.empty()

    adapter.summary = RealmSummary(realm_id="odin", health_status="degraded", metrics={"nodes": 2})
    await poller.poll_once()
    assert await queue.get() == adapter.summary


@pytest.mark.asyncio
async def test_poller_logs_adapter_errors_and_continues(caplog: pytest.LogCaptureFixture) -> None:
    healthy_summary = RealmSummary(realm_id="thor", health_status="healthy")
    failing = FakeRealmAdapter("odin", error=RuntimeError("adapter unavailable"))
    healthy = FakeRealmAdapter("thor", summary=healthy_summary)
    manager = ConnectionManager(max_clients=1)
    broadcast = Mock(wraps=manager.broadcast)
    manager.broadcast = broadcast
    poller = RealmPoller([failing, healthy], manager, poll_interval=15.0)

    await poller.poll_once()

    assert poller.summary_for("odin") is None
    assert poller.summary_for("thor") == healthy_summary
    broadcast.assert_called_once_with(healthy_summary)
    assert "could not poll realm odin" in caplog.text
