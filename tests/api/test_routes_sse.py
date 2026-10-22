"""Contract tests for the Yggdrasil realm summary SSE endpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from fastapi import HTTPException, Request

from yggdrasil.config import YggdrasilSettings
from yggdrasil.main import create_app
from yggdrasil.models import RealmSummary
from yggdrasil.stream import REALM_SUMMARY_EVENT


@dataclass
class FakeRealmAdapter:
    """In-memory realm adapter used by the stream contract tests."""

    realm_id: str
    summary: RealmSummary

    async def get_summary(self) -> RealmSummary:
        return self.summary


def _request(app, *, disconnected: bool = False) -> Request:
    return Request(
        {
            "type": "http",
            "app": app,
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "method": "GET",
            "path": "/api/v1/yggdrasil/realms/odin/stream",
            "query_string": b"",
        }
    )


def _route(app):
    return next(
        route
        for route in app.state.sse_router.routes
        if route.path == "/api/v1/yggdrasil/realms/{realm_id}/stream"
    )


@pytest.mark.asyncio
async def test_stream_sends_current_realm_summary_as_an_sse_frame() -> None:
    summary = RealmSummary(realm_id="odin", health_status="healthy", metrics={"nodes": 3})
    app = create_app(adapters=[FakeRealmAdapter("odin", summary)])
    await app.state.realm_poller.poll_once()

    response = await _route(app).endpoint(_request(app), "odin")
    frame = await anext(response.body_iterator)
    await response.body_iterator.aclose()

    assert response.media_type == "text/event-stream"
    assert response.headers["x-accel-buffering"] == "no"
    assert frame.startswith(f"event: {REALM_SUMMARY_EVENT}\n")
    payload = frame.removeprefix(f"event: {REALM_SUMMARY_EVENT}\ndata: ").removesuffix("\n\n")
    assert json.loads(payload) == summary.model_dump(mode="json")
    assert app.state.connection_manager.active_client_count == 0


@pytest.mark.asyncio
async def test_stream_returns_503_when_client_limit_is_reached() -> None:
    summary = RealmSummary(realm_id="odin", health_status="healthy")
    app = create_app(
        settings=YggdrasilSettings(max_sse_clients=1),
        adapters=[FakeRealmAdapter("odin", summary)],
    )
    await app.state.realm_poller.poll_once()
    route = _route(app)

    response = await route.endpoint(_request(app), "odin")
    await anext(response.body_iterator)

    with pytest.raises(HTTPException) as error:
        await route.endpoint(_request(app), "odin")

    await response.body_iterator.aclose()
    assert error.value.status_code == 503
    assert app.state.connection_manager.active_client_count == 0


def test_poll_interval_uses_yggdrasil_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YGGDRASIL_POLL_INTERVAL", raising=False)
    assert YggdrasilSettings().poll_interval == 15.0

    monkeypatch.setenv("YGGDRASIL_POLL_INTERVAL", "2.5")
    assert YggdrasilSettings().poll_interval == 2.5
