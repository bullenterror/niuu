"""Ravn resident sessions through Ravn's OpenClaw-protocol shim.

A Ravn resident pod runs ``ravn.adapters.channels.gateway_openclaw``: an OpenClaw
Gateway that executes on Ravn, where every session key is its own Ravn
conversation with its own transcript. So a Ravn resident's sessions are driven by
the OpenClaw controller itself; this adapter supplies only what differs:

* the route: the shim's own port in the resident's workload, which the owning
  backend resolves (``ResidentOpenClawShimHost``: the resident's Service on Flux,
  an OpenShell TCP forward on OpenShell), not the backend's skuld proxy target;
* the token: each resident's shim checks its own token, HMAC-SHA256(master, resident
  id). Volundr holds only the master (``gateway_token``) and hands the derivation to
  the runtime controller, which writes that one resident's token into a Secret for
  its pod; a pod never sees the master or another resident's token;
* the machine identity: the shim trusts a device on first use behind that token, so
  the device key is derived from the master and the resident id instead of being
  minted and stored per resident;
* the participant: the resident itself, not NemoClaw.

The resident's default room (its ``skuld-v1`` chat endpoint, session id = resident
id) is a different endpoint and is unaffected.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from niuu.domain.models import SecretType
from niuu.ports.credentials import CredentialStorePort
from niuu.ports.session_proxy import SessionProxyTarget
from volundr.adapters.outbound.openclaw_gateway import (
    _RETRY_HISTORY_POLL_INTERVAL_SECONDS,
    _RETRY_HISTORY_TIMEOUT_SECONDS,
    OpenClawResidentSessionController,
    _GatewayConnection,
    _new_machine_credential,
)
from volundr.domain.models import ResidentDeploymentProfile, ResidentEngine, ResidentRuntime
from volundr.domain.ports import ResidentOpenClawShimHost

DEFAULT_SERVICE_PORT = 18790
_DEVICE_SEED_CONTEXT = b"niuu-ravn-resident-openclaw-device:"
#: Where Volundr keeps the master it generated itself (no gateway_token configured).
MASTER_CREDENTIAL = ("system", "resident-ravn-sessions", "gateway-token")
_MASTER_FIELD = "token"


async def ensure_resident_sessions_master(store: CredentialStorePort) -> str:
    """The Ravn residents' sessions master Volundr keeps in its credential store.

    Generated once, on first use, like the Hermes residents' API keys: only Volundr
    reads it (it derives each resident's shim token from it), so no cluster needs to
    provision it. A configured ``gateway_token`` replaces it.
    """
    owner_type, owner_id, name = MASTER_CREDENTIAL
    existing = await store.get_value(owner_type, owner_id, name)
    if existing and existing.get(_MASTER_FIELD):
        return existing[_MASTER_FIELD]
    await store.store(
        owner_type,
        owner_id,
        name,
        SecretType.API_KEY,
        {_MASTER_FIELD: secrets.token_urlsafe(48)},
        metadata={"purpose": "ravn-resident-sessions"},
    )
    # Read back what the store kept, so a concurrent first start converges on one value.
    stored = await store.get_value(owner_type, owner_id, name)
    if not stored or not stored.get(_MASTER_FIELD):
        raise RuntimeError("Ravn resident sessions master was not kept by the credential store")
    return stored[_MASTER_FIELD]


def resident_openclaw_token(master: str, runtime: ResidentRuntime) -> str:
    """The shim token of one resident: HMAC-SHA256(master, resident id), hex."""
    return hmac.new(
        master.encode("utf-8"),
        str(runtime.id).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


class RavnResidentSessionController(OpenClawResidentSessionController):
    """Ravn implementation of resident sessions, over the Ravn OpenClaw shim."""

    def __init__(
        self,
        runtime_controller: Any,
        credential_store: CredentialStorePort,
        *,
        gateway_token: str = "",
        service_host: str = "",
        service_port: int = DEFAULT_SERVICE_PORT,
        retry_history_timeout_seconds: float = _RETRY_HISTORY_TIMEOUT_SECONDS,
        retry_history_poll_interval_seconds: float = _RETRY_HISTORY_POLL_INTERVAL_SECONDS,
    ) -> None:
        if not gateway_token:
            raise ValueError(
                "RavnResidentSessionController requires gateway_token: the master secret "
                "each Ravn resident's own OpenClaw shim token is derived from"
            )
        if not service_host and not isinstance(runtime_controller, ResidentOpenClawShimHost):
            raise ValueError(
                "RavnResidentSessionController needs a backend that hosts the Ravn OpenClaw "
                f"shim ({getattr(runtime_controller, 'backend', runtime_controller)!r} does "
                "not implement ResidentOpenClawShimHost), or an explicit service_host"
            )
        super().__init__(
            runtime_controller,
            credential_store,
            retry_history_timeout_seconds=retry_history_timeout_seconds,
            retry_history_poll_interval_seconds=retry_history_poll_interval_seconds,
        )
        self._gateway_token = gateway_token
        # An explicit host template ({release}, {namespace}, {runtime_id}) overrides
        # the backend's own route to the shim.
        self._service_host = service_host
        self._service_port = int(service_port)
        # The backend that deploys the resident provisions the same per-resident token.
        if isinstance(runtime_controller, ResidentOpenClawShimHost):
            runtime_controller.set_resident_openclaw_tokens(self.resident_token)

    def resident_token(self, runtime: ResidentRuntime) -> str:
        """The token *runtime*'s shim checks (``RAVN_OPENCLAW_TOKEN`` in its pod)."""
        return resident_openclaw_token(self._gateway_token, runtime)

    @property
    def engine(self) -> ResidentEngine:
        return ResidentEngine.RAVN

    def provides_sessions(self, profile: ResidentDeploymentProfile) -> bool:
        """A profile that switches the shim off (resident.openclaw.enabled) has none."""
        values = profile.deployment.get("values")
        resident = values.get("resident") if isinstance(values, dict) else None
        shim = resident.get("openclaw") if isinstance(resident, dict) else None
        return not (isinstance(shim, dict) and shim.get("enabled") is False)

    def _proxy_target(self, runtime: ResidentRuntime) -> SessionProxyTarget | None:
        if not self._service_host:
            return self._runtime.resident_openclaw_target(runtime, self._service_port)
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
        return {**credentials, "gateway_token": self.resident_token(runtime), "device_token": ""}

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
