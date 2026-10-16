"""Dynamic resident engine adapter composition tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from niuu.adapters.memory_credential_store import MemoryCredentialStore
from volundr.config import Settings
from volundr.domain.models import ResidentBackend, ResidentEngine
from volundr.domain.ports import ResidentOpenClawShimHost, ResidentSessionController
from volundr.main import _create_resident_session_controllers, _resolve_ravn_sessions_master


class _SessionController(ResidentSessionController):
    def __init__(
        self,
        *,
        runtime_controller: object,
        credential_store: object,
        marker: str = "",
    ) -> None:
        self.runtime_controller = runtime_controller
        self.credential_store = credential_store
        self.marker = marker

    @property
    def engine(self) -> ResidentEngine:
        return ResidentEngine.HERMES

    async def list_sessions(self, runtime):
        return []

    async def create_session(self, runtime, *, title: str, model: str):
        raise NotImplementedError

    async def delete_session(self, runtime, session_id):
        raise NotImplementedError

    async def connect_chat(self, runtime, session_id):
        raise NotImplementedError


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "resident_runtimes": {
                "session_controllers": [
                    {
                        "adapter": "tests.fake.HermesController",
                        "runtime_backend": "openshell",
                        "kwargs": {"marker": "configured"},
                    }
                ]
            }
        }
    )


def test_resident_session_controller_receives_bound_backend_and_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_controller = SimpleNamespace(backend=ResidentBackend.OPENSHELL)
    credential_store = object()
    monkeypatch.setattr(
        "volundr.composition_builders.import_class",
        lambda _path: _SessionController,
    )

    controllers = _create_resident_session_controllers(
        _settings(),
        [runtime_controller],  # type: ignore[list-item]
        credential_store,
    )

    assert len(controllers) == 1
    controller = controllers[0]
    assert isinstance(controller, _SessionController)
    assert controller.runtime_controller is runtime_controller
    assert controller.credential_store is credential_store
    assert controller.marker == "configured"


def test_resident_session_controller_requires_its_runtime_backend() -> None:
    with pytest.raises(RuntimeError, match="requires unavailable backend openshell"):
        _create_resident_session_controllers(_settings(), [], object())


def test_default_openclaw_adapter_is_optional_without_openshell_backend() -> None:
    settings = Settings()

    assert settings.resident_runtimes.session_controllers[0].optional is True
    assert _create_resident_session_controllers(settings, [], object()) == []


class _ShimHost(ResidentOpenClawShimHost):
    """A resident backend that hosts the Ravn OpenClaw shim (Flux, OpenShell)."""

    def __init__(self, backend: ResidentBackend) -> None:
        self.backend = backend
        self.resident_token = None

    def set_resident_openclaw_tokens(self, resident_token) -> None:
        self.resident_token = resident_token

    def resident_openclaw_target(self, runtime, port):
        return None


_MASTER = "master-for-default-ravn-sessions"


def _ravn_settings(**resident_runtimes) -> Settings:
    return Settings.model_validate(
        {"resident_runtimes": {"session_controllers": [], **resident_runtimes}}
    )


def test_ravn_sessions_are_wired_on_every_shim_host_by_default() -> None:
    from volundr.adapters.outbound.ravn_gateway import (
        RavnResidentSessionController,
        resident_openclaw_token,
    )

    flux = _ShimHost(ResidentBackend.HELMRELEASE)
    openshell = _ShimHost(ResidentBackend.OPENSHELL)
    plain = SimpleNamespace(backend=ResidentBackend.LOCAL)

    controllers = _create_resident_session_controllers(
        _ravn_settings(ravn_gateway_token=_MASTER),
        [flux, openshell, plain],  # type: ignore[list-item]
        object(),
    )

    assert [type(c) for c in controllers] == [RavnResidentSessionController] * 2
    assert [c.runtime_backend for c in controllers] == [
        ResidentBackend.HELMRELEASE,
        ResidentBackend.OPENSHELL,
    ]
    assert all(c.engine is ResidentEngine.RAVN for c in controllers)
    runtime = SimpleNamespace(id="3f2b8c1e-6d4a-4e9b-9c57-1a2b3c4d5e6f")
    assert flux.resident_token(runtime) == resident_openclaw_token(_MASTER, runtime)


def test_a_configured_ravn_controller_wins_on_its_backend(monkeypatch) -> None:
    """Valhalla's explicit helmrelease controller keeps its own master secret."""
    monkeypatch.setenv("RESIDENT_SESSION_CONTROLLER_0_SK_GATEWAY_TOKEN", "valhalla-master")
    flux = _ShimHost(ResidentBackend.HELMRELEASE)
    openshell = _ShimHost(ResidentBackend.OPENSHELL)
    settings = _ravn_settings(
        ravn_gateway_token=_MASTER,
        session_controllers=[
            {
                "adapter": "volundr.adapters.outbound.ravn_gateway.RavnResidentSessionController",
                "runtime_backend": "helmrelease",
                "secret_kwargs_env": {
                    "gateway_token": "RESIDENT_SESSION_CONTROLLER_0_SK_GATEWAY_TOKEN"
                },
            }
        ],
    )

    controllers = _create_resident_session_controllers(settings, [flux, openshell], object())

    assert [c.runtime_backend for c in controllers] == [
        ResidentBackend.HELMRELEASE,
        ResidentBackend.OPENSHELL,
    ]
    assert controllers[0]._gateway_token == "valhalla-master"
    assert controllers[1]._gateway_token == _MASTER


def test_no_default_ravn_sessions_without_a_master_token(caplog) -> None:
    flux = _ShimHost(ResidentBackend.HELMRELEASE)

    with caplog.at_level("WARNING"):
        controllers = _create_resident_session_controllers(_ravn_settings(), [flux], object())

    assert controllers == []
    assert flux.resident_token is None
    assert "Ravn resident sessions are off on helmrelease" in caplog.text


def test_default_ravn_sessions_can_be_switched_off() -> None:
    flux = _ShimHost(ResidentBackend.HELMRELEASE)
    settings = _ravn_settings(ravn_gateway_token=_MASTER, ravn_sessions_enabled=False)

    assert _create_resident_session_controllers(settings, [flux], object()) == []
    assert flux.resident_token is None


class TestRavnSessionsMaster:
    """With no master configured, Volundr keeps its own in its credential store."""

    async def test_generated_once_and_kept(self) -> None:
        from volundr.adapters.outbound.ravn_gateway import MASTER_CREDENTIAL

        store = MemoryCredentialStore()
        hosts = [_ShimHost(ResidentBackend.OPENSHELL)]

        first = await _resolve_ravn_sessions_master(_ravn_settings(), hosts, store)
        again = await _resolve_ravn_sessions_master(_ravn_settings(), hosts, store)

        assert first and first == again
        assert await store.get_value(*MASTER_CREDENTIAL) == {"token": first}
        controllers = _create_resident_session_controllers(
            _ravn_settings(), hosts, store, ravn_sessions_master=first
        )
        assert [c.runtime_backend for c in controllers] == [ResidentBackend.OPENSHELL]
        assert controllers[0]._gateway_token == first

    async def test_configured_master_wins_and_nothing_is_stored(self) -> None:
        store = MemoryCredentialStore()
        settings = _ravn_settings(ravn_gateway_token=_MASTER)

        master = await _resolve_ravn_sessions_master(
            settings, [_ShimHost(ResidentBackend.OPENSHELL)], store
        )

        assert master == _MASTER
        assert await store.list("system", "resident-ravn-sessions") == []

    async def test_none_when_no_backend_needs_a_default(self, monkeypatch) -> None:
        """Valhalla: its explicit helmrelease controller covers its only shim host."""
        monkeypatch.setenv("RESIDENT_SESSION_CONTROLLER_0_SK_GATEWAY_TOKEN", "valhalla-master")
        store = MemoryCredentialStore()
        settings = _ravn_settings(
            session_controllers=[
                {
                    "adapter": (
                        "volundr.adapters.outbound.ravn_gateway.RavnResidentSessionController"
                    ),
                    "runtime_backend": "helmrelease",
                    "secret_kwargs_env": {
                        "gateway_token": "RESIDENT_SESSION_CONTROLLER_0_SK_GATEWAY_TOKEN"
                    },
                }
            ],
        )
        flux = _ShimHost(ResidentBackend.HELMRELEASE)

        assert await _resolve_ravn_sessions_master(settings, [flux], store) == ""
        assert await store.list("system", "resident-ravn-sessions") == []
        [controller] = _create_resident_session_controllers(settings, [flux], store)
        assert controller._gateway_token == "valhalla-master"

    async def test_none_when_switched_off_or_without_a_shim_host(self) -> None:
        store = MemoryCredentialStore()
        off = _ravn_settings(ravn_sessions_enabled=False)

        assert (
            await _resolve_ravn_sessions_master(off, [_ShimHost(ResidentBackend.OPENSHELL)], store)
            == ""
        )
        plain = SimpleNamespace(backend=ResidentBackend.LOCAL)
        assert await _resolve_ravn_sessions_master(_ravn_settings(), [plain], store) == ""  # type: ignore[list-item]
        assert await store.list("system", "resident-ravn-sessions") == []

    async def test_a_store_that_cannot_keep_it_leaves_sessions_off(self, caplog) -> None:
        class _Broken(MemoryCredentialStore):
            async def get_value(self, *_args):
                raise ConnectionError("openbao is down")

        with caplog.at_level("WARNING"):
            master = await _resolve_ravn_sessions_master(
                _ravn_settings(), [_ShimHost(ResidentBackend.OPENSHELL)], _Broken()
            )

        assert master == ""
        assert "Ravn resident sessions are off on openshell" in caplog.text
