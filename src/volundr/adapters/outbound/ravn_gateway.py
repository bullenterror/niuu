"""Ravn resident sessions through Ravn's OpenClaw-protocol shim.

A Ravn resident pod runs ``ravn.adapters.channels.gateway_openclaw``: an OpenClaw
Gateway that executes on Ravn, where every session key is its own Ravn
conversation with its own transcript. So a Ravn resident's sessions are driven by
the OpenClaw controller itself; this adapter supplies only what differs:

* the route: the shim's port on the resident's in-cluster Service, not a backend
  proxy target;
* the machine identity: the shim trusts a device on first use behind one shared
  gateway token, so the device key is derived from that token and the resident id
  instead of being minted and stored per resident;
* the participant: the resident itself, not NemoClaw.

The resident's default room (its ``skuld-v1`` chat endpoint, session id = resident
id) is a different endpoint and is unaffected.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from niuu.ports.credentials import CredentialStorePort
from niuu.ports.session_proxy import SessionProxyTarget
from volundr.adapters.outbound.openclaw_gateway import (
    _RETRY_HISTORY_POLL_INTERVAL_SECONDS,
    _RETRY_HISTORY_TIMEOUT_SECONDS,
    OpenClawResidentSessionController,
    _GatewayConnection,
    _new_machine_credential,
)
from volundr.domain.models import ResidentEngine, ResidentRuntime

DEFAULT_SERVICE_HOST = "{release}-skuld.{namespace}.svc.cluster.local"
DEFAULT_SERVICE_PORT = 18790
_DEVICE_SEED_CONTEXT = b"niuu-ravn-resident-openclaw-device:"


class RavnResidentSessionController(OpenClawResidentSessionController):
    """Ravn implementation of resident sessions, over the Ravn OpenClaw shim."""

    def __init__(
        self,
        runtime_controller: Any,
        credential_store: CredentialStorePort,
        *,
        gateway_token: str = "",
        service_host: str = DEFAULT_SERVICE_HOST,
        service_port: int = DEFAULT_SERVICE_PORT,
        retry_history_timeout_seconds: float = _RETRY_HISTORY_TIMEOUT_SECONDS,
        retry_history_poll_interval_seconds: float = _RETRY_HISTORY_POLL_INTERVAL_SECONDS,
    ) -> None:
        if not gateway_token:
            raise ValueError(
                "RavnResidentSessionController requires gateway_token: the token every "
                "Ravn resident's OpenClaw shim reads from RAVN_OPENCLAW_TOKEN"
            )
        super().__init__(
            runtime_controller,
            credential_store,
            retry_history_timeout_seconds=retry_history_timeout_seconds,
            retry_history_poll_interval_seconds=retry_history_poll_interval_seconds,
        )
        self._gateway_token = gateway_token
        self._service_host = service_host
        self._service_port = int(service_port)

    @property
    def engine(self) -> ResidentEngine:
        return ResidentEngine.RAVN

    def _proxy_target(self, runtime: ResidentRuntime) -> SessionProxyTarget | None:
        namespace = str(runtime.backend_ref.get("namespace") or "")
        release = str(runtime.backend_ref.get("name") or "")
        if not namespace or not release:
            return None
        host = self._service_host.format(
            release=release,
            namespace=namespace,
            runtime_id=runtime.id,
        )
        return SessionProxyTarget(
            service_url=f"http://{host}:{self._service_port}/",
            connect_host=host,
            connect_port=self._service_port,
        )

    async def _machine_credentials(self, runtime: ResidentRuntime) -> dict[str, str]:
        seed = hmac.new(
            self._gateway_token.encode("utf-8"),
            _DEVICE_SEED_CONTEXT + str(runtime.id).encode("ascii"),
            hashlib.sha256,
        ).digest()
        credentials = _new_machine_credential(Ed25519PrivateKey.from_private_bytes(seed))
        return {**credentials, "gateway_token": self._gateway_token, "device_token": ""}

    async def _remember_device_token(
        self,
        runtime: ResidentRuntime,
        credentials: dict[str, str],
    ) -> None:
        """The shim's device token is derived from the gateway token; nothing to keep."""

    def _participant(self, runtime: ResidentRuntime) -> dict[str, Any]:
        persona = runtime.persona_name or runtime.name
        return {
            "peer_id": runtime.flock_peer_id or f"flock-{persona}",
            "persona": persona,
            "display_name": runtime.name,
            "participant_type": "resident",
            "status": "idle",
        }

    async def _prepare_chat(self, connection: _GatewayConnection, session_key: str) -> None:
        # The shim relays a session's chat events only to connections subscribed to it.
        await connection.request("sessions.subscribe", {"sessionKey": session_key})
