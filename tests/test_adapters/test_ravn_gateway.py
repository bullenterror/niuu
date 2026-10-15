"""Ravn resident sessions: Volundr's controller against Ravn's real OpenClaw shim.

The shim is booted on a real socket with a stub Ravn behind it, and driven by the
production controller, so these prove the two protocol halves agree: session
lifecycle, one Ravn conversation per session, and chat frames in the same shared
contract the OpenClaw controller produces.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from niuu.adapters.memory_credential_store import MemoryCredentialStore
from tests.test_ravn.test_openclaw_gateway import (
    StubRavnGateway,
    _Event,
    plain_turn,
    running_shim,
)
from volundr.adapters.outbound.ravn_gateway import (
    RavnResidentSessionController,
    resident_openclaw_token,
)
from volundr.composition_builders import _create_resident_session_controllers
from volundr.config import Settings
from volundr.domain.models import (
    ResidentBackend,
    ResidentEngine,
    ResidentRuntime,
    ResidentSessionStatus,
)
from volundr.domain.ports import ResidentSessionController

#: Volundr's master secret. A resident's shim only ever holds its derived token.
MASTER = "master-9f8e7d6c5b4a39281706f5e4d3c2b1a0"
_RESIDENT_FRAMES = {"assistant", "content_block_delta", "result", "error"}


class _FluxRoutes:
    """The helm-release runtime controller: it provisions each resident's shim token."""

    backend = ResidentBackend.HELMRELEASE

    def __init__(self) -> None:
        self.resident_token: Any = None

    def set_resident_openclaw_tokens(self, resident_token: Any) -> None:
        self.resident_token = resident_token

    async def approve_resident_device(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the Ravn shim trusts devices on first use; no pairing")


def _runtime(**update: Any) -> ResidentRuntime:
    runtime = ResidentRuntime(
        owner_id="user-a",
        tenant_id="tenant-a",
        name="Muninn",
        persona_name="product-steward",
        model="gpt-5.6-sol",
        backend=ResidentBackend.HELMRELEASE,
        engine=ResidentEngine.RAVN,
        profile_id="ravn-helm",
    )
    backend_ref = {"namespace": "skuld", "name": f"resident-{runtime.id}"}
    return runtime.model_copy(update={"backend_ref": backend_ref, **update})


def _controller(port: int, **kwargs: Any) -> RavnResidentSessionController:
    return RavnResidentSessionController(
        _FluxRoutes(),
        MemoryCredentialStore(),
        gateway_token=MASTER,
        service_host="127.0.0.1",
        service_port=port,
        **kwargs,
    )


def _resident_shim(tmp_path: Any, runtime: ResidentRuntime, **kwargs: Any) -> Any:
    """The shim as the resident's pod runs it: agent id main, its own derived token."""
    return running_shim(
        tmp_path,
        agent_id="main",
        token=resident_openclaw_token(MASTER, runtime),
        **kwargs,
    )


def _port(url: str) -> int:
    return int(url.rsplit(":", 1)[1])


async def _frames_until_turn_ends(connection: Any) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    while True:
        frame = await asyncio.wait_for(connection.receive(), timeout=10)
        frames.append(frame)
        if frame["type"] in {"result", "error"}:
            return frames


class TestRavnSessionsThroughTheShim:
    async def test_create_list_chat_and_delete(self, tmp_path) -> None:
        runtime = _runtime()
        async with _resident_shim(tmp_path, runtime) as shim:
            controller = _controller(_port(shim.url))

            session = await controller.create_session(runtime, title="Research", model="")
            assert session.chat_endpoint == f"/s/{runtime.id}/sessions/{session.id}/session"

            listed = await controller.list_sessions(runtime)
            # The shim's own default session is not a Volundr session; only niuu-<uuid> keys are.
            assert [(s.id, s.title) for s in listed] == [(session.id, "Research")]
            assert listed[0].status is ResidentSessionStatus.IDLE

            connection = await controller.connect_chat(runtime, session.id)
            try:
                assert (await connection.receive())["type"] == "capabilities"
                assert await connection.receive() == {"type": "conversation_history", "turns": []}
                await connection.send({"type": "user", "content": "ping", "request_id": "r-1"})
                frames = await _frames_until_turn_ends(connection)
            finally:
                await connection.close()

            confirmed = next(f for f in frames if f["type"] == "user_confirmed")
            assert confirmed["request_id"] == "r-1"
            resident = [f for f in frames if f["type"] in _RESIDENT_FRAMES]
            assert [f["type"] for f in resident] == [
                "assistant",
                "content_block_delta",
                "content_block_delta",
                "result",
            ]
            assert resident[0]["participant"]["display_name"] == "Muninn"
            assert resident[0]["participant"]["persona"] == "product-steward"
            text = "".join(
                f["delta"]["text"] for f in resident if f["type"] == "content_block_delta"
            )
            assert text == "pong", "cumulative shim deltas must not double the answer"
            assert shim.stub.seen == [(f"agent:main:niuu-{session.id}", "ping")]

            await controller.delete_session(runtime, session.id)
            assert await controller.list_sessions(runtime) == []
            assert shim.stub.dropped == [f"agent:main:niuu-{session.id}"]

    async def test_sessions_are_separate_conversations_with_their_own_history(
        self, tmp_path
    ) -> None:
        runtime = _runtime()
        async with _resident_shim(tmp_path, runtime) as shim:
            controller = _controller(_port(shim.url))
            first = await controller.create_session(runtime, title="One", model="")
            second = await controller.create_session(runtime, title="Two", model="")

            for session, message in ((first, "alpha"), (second, "beta")):
                connection = await controller.connect_chat(runtime, session.id)
                try:
                    await connection.receive()
                    await connection.receive()
                    await connection.send({"type": "user", "content": message})
                    await _frames_until_turn_ends(connection)
                finally:
                    await connection.close()

            assert {key for key, _ in shim.stub.seen} == {
                f"agent:main:niuu-{first.id}",
                f"agent:main:niuu-{second.id}",
            }
            connection = await controller.connect_chat(runtime, first.id)
            try:
                await connection.receive()
                history = await connection.receive()
            finally:
                await connection.close()
            assert [(t["role"], t["content"]) for t in history["turns"]] == [
                ("user", "alpha"),
                ("assistant", "pong"),
            ]
            assert history["turns"][1]["participant_meta"]["display_name"] == "Muninn"

    async def test_interrupt_aborts_the_turn(self, tmp_path) -> None:
        stub = StubRavnGateway(script=plain_turn(), delay=0.3)
        runtime = _runtime()
        async with _resident_shim(tmp_path, runtime, stub=stub) as shim:
            controller = _controller(_port(shim.url))
            session = await controller.create_session(runtime, title="Slow", model="")
            connection = await controller.connect_chat(runtime, session.id)
            try:
                await connection.receive()
                await connection.receive()
                await connection.send({"type": "user", "content": "slow"})
                while (await asyncio.wait_for(connection.receive(), timeout=10))[
                    "type"
                ] != "assistant":
                    pass
                await connection.send({"type": "interrupt"})
                frames = await _frames_until_turn_ends(connection)
            finally:
                await connection.close()
            assert frames[-1] == {"type": "error", "error": "aborted"}

    async def test_a_wrong_master_is_refused(self, tmp_path) -> None:
        runtime = _runtime()
        async with _resident_shim(tmp_path, runtime) as shim:
            controller = RavnResidentSessionController(
                _FluxRoutes(),
                MemoryCredentialStore(),
                gateway_token="not-the-master",
                service_host="127.0.0.1",
                service_port=_port(shim.url),
            )
            with pytest.raises(Exception, match="invalid gateway token"):
                await controller.list_sessions(runtime)

    async def test_one_residents_token_does_not_open_another_residents_shim(self, tmp_path) -> None:
        async with _resident_shim(tmp_path, _runtime()) as shim:
            controller = _controller(_port(shim.url))
            with pytest.raises(Exception, match="invalid gateway token"):
                await controller.list_sessions(_runtime())


class TestRavnRepliesStreamOnce:
    """A reply reaches clients exactly once, whatever Ravn executor produced it."""

    async def test_cli_executor_turn_is_not_doubled(self, tmp_path) -> None:
        """The live Valhalla turn: a CLI executor streams fragments, then re-sends the
        whole message as one more thought, then the response. Before the fix clients
        got the fragments and then the full text again as a last delta."""
        fragments = ["I", "’m", " doing", " well", " and", " ready", " to", " help", "."]
        answer = "".join(fragments)
        script = [_Event("thought", {"text": fragment}) for fragment in fragments]
        script += [_Event("thought", {"text": answer}), _Event("response", {"text": answer})]
        runtime = _runtime()
        async with _resident_shim(tmp_path, runtime, stub=StubRavnGateway(script=script)) as shim:
            controller = _controller(_port(shim.url))
            session = await controller.create_session(runtime, title="Hello", model="")
            connection = await controller.connect_chat(runtime, session.id)
            try:
                await connection.receive()
                await connection.receive()
                await connection.send({"type": "user", "content": "How are you?"})
                frames = await _frames_until_turn_ends(connection)
            finally:
                await connection.close()

        resident = [f for f in frames if f["type"] in _RESIDENT_FRAMES]
        assert [f["type"] for f in resident] == [
            "assistant",
            *["content_block_delta"] * len(fragments),
            "result",
        ]
        deltas = [f["delta"]["text"] for f in resident if f["type"] == "content_block_delta"]
        assert deltas == fragments
        assert "".join(deltas) == answer

    async def test_text_after_a_tool_does_not_repeat_the_text_before_it(self, tmp_path) -> None:
        script = [
            _Event("thought", {"text": "Let me look."}),
            _Event("tool_start", {"tool_name": "read_file", "input": {}}),
            _Event("tool_result", {"tool_name": "read_file", "result": "# niuu"}),
            _Event("thought", {"text": "It is "}),
            _Event("thought", {"text": "niuu."}),
            _Event("response", {"text": "It is niuu."}),
        ]
        runtime = _runtime()
        async with _resident_shim(tmp_path, runtime, stub=StubRavnGateway(script=script)) as shim:
            controller = _controller(_port(shim.url))
            session = await controller.create_session(runtime, title="Tools", model="")
            connection = await controller.connect_chat(runtime, session.id)
            try:
                await connection.receive()
                await connection.receive()
                await connection.send({"type": "user", "content": "Which heading?"})
                frames = await _frames_until_turn_ends(connection)
            finally:
                await connection.close()

        text = "".join(f["delta"]["text"] for f in frames if f["type"] == "content_block_delta")
        assert text == "Let me look.It is niuu."


class TestRavnControllerWiring:
    def test_engine_is_ravn(self) -> None:
        assert _controller(1).engine is ResidentEngine.RAVN

    def test_hands_the_per_resident_token_to_the_runtime_controller(self) -> None:
        routes = _FluxRoutes()
        RavnResidentSessionController(routes, MemoryCredentialStore(), gateway_token=MASTER)
        runtime = _runtime()
        token = routes.resident_token(runtime)
        assert token == resident_openclaw_token(MASTER, runtime)
        assert len(token) == 64 and int(token, 16) >= 0
        assert MASTER not in token

    def test_gateway_token_is_required(self) -> None:
        with pytest.raises(ValueError, match="gateway_token"):
            RavnResidentSessionController(_FluxRoutes(), MemoryCredentialStore())

    def test_route_is_the_resident_service_shim_port(self) -> None:
        controller = RavnResidentSessionController(
            _FluxRoutes(), MemoryCredentialStore(), gateway_token=MASTER
        )
        runtime = _runtime()
        target = controller._proxy_target(runtime)
        host = f"resident-{runtime.id}-skuld.skuld.svc.cluster.local"
        assert target is not None
        assert target.service_url == f"http://{host}:18790/"
        assert (target.connect_host, target.connect_port) == (host, 18790)

    def test_no_route_before_the_backend_reports_the_release(self) -> None:
        assert _controller(1)._proxy_target(_runtime(backend_ref={})) is None

    async def test_device_identity_is_stable_per_resident_and_never_stored(self) -> None:
        store = MemoryCredentialStore()
        controller = RavnResidentSessionController(_FluxRoutes(), store, gateway_token=MASTER)
        runtime = _runtime()
        first = await controller._machine_credentials(runtime)
        again = await controller._machine_credentials(runtime)
        other = await controller._machine_credentials(_runtime())
        assert first == again
        assert first["device_id"] != other["device_id"]
        assert first["gateway_token"] == resident_openclaw_token(MASTER, runtime)
        assert first["gateway_token"] != MASTER
        assert other["gateway_token"] != first["gateway_token"]
        assert first["device_token"] == ""
        await controller._remember_device_token(runtime, {**first, "device_token": "d"})
        assert await store.get_value("resident", str(runtime.id), "openclaw-gateway") is None

    def test_composition_builds_it_against_the_helmrelease_backend(self, monkeypatch) -> None:
        monkeypatch.setenv("RESIDENT_SESSION_CONTROLLER_0_SK_GATEWAY_TOKEN", MASTER)
        settings = Settings.model_validate(
            {
                "resident_runtimes": {
                    "session_controllers": [
                        {
                            "adapter": (
                                "volundr.adapters.outbound.ravn_gateway."
                                "RavnResidentSessionController"
                            ),
                            "runtime_backend": "helmrelease",
                            "secret_kwargs_env": {
                                "gateway_token": "RESIDENT_SESSION_CONTROLLER_0_SK_GATEWAY_TOKEN"
                            },
                        }
                    ]
                }
            }
        )
        controllers = _create_resident_session_controllers(
            settings,
            [_FluxRoutes()],  # type: ignore[list-item]
            MemoryCredentialStore(),
        )
        assert len(controllers) == 1
        assert isinstance(controllers[0], ResidentSessionController)
        assert controllers[0].engine is ResidentEngine.RAVN
