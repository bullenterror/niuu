"""Flux HelmRelease adapter for pod management.

Creates HelmRelease custom resources in Kubernetes, which Flux
reconciles into running session pods. Selected via the dynamic
adapter pattern in config YAML.
"""

import copy
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from niuu.adapters.flux import (
    HELMRELEASE_GROUP,
    HELMRELEASE_PLURAL,
    HELMRELEASE_VERSION,
    FluxHelmReleases,
    create_flux_api_client,
)
from niuu.ports.session_proxy import SessionProxyTarget
from volundr.adapters.outbound.brokered_credentials import BrokeredCredentialPodManager
from volundr.adapters.outbound.k8s_storage_adapter import build_pvc_manifest
from volundr.adapters.outbound.resident_container_spec import (
    resident_flock_labels,
    resident_flock_profile_configured,
    resident_mesh_pod_metadata,
    resident_openclaw_shim_enabled,
)
from volundr.domain.models import (
    LABEL_MANAGED_BY,
    LABEL_PVC_TYPE,
    ResidentBackend,
    ResidentCondition,
    ResidentConditionStatus,
    ResidentDeploymentProfile,
    ResidentDesiredState,
    ResidentEndpoint,
    ResidentEngine,
    ResidentObservedState,
    ResidentRuntime,
    Session,
    SessionSpec,
    SessionStatus,
    _deep_merge,
)
from volundr.domain.ports import (
    PodManager,
    PodStartResult,
    ResidentOpenClawShimHost,
    ResidentRuntimeController,
    ResidentRuntimeObservation,
)

logger = logging.getLogger(__name__)

LABEL_RESIDENT_ID = "niuu.world/resident-id"
# Deliberately not volundr/owner: the resident pod does not carry that label
# (Valhalla's session podAffinity co-locates a user's skuld pods by it), so an
# owner-labelled claim would fail the PVC isolation policy (charts/volundr
# kyverno-pvc-isolation.yaml).
LABEL_RESIDENT_OWNER_ID = "niuu.world/owner-id"
LABEL_RESIDENT_TENANT_ID = "niuu.world/tenant-id"
# A resident's own volumes, keyed by the profile's deployment.volumes block.
RESIDENT_VOLUME_KINDS = ("home", "workspace")
RESIDENT_VOLUME_SETTINGS = frozenset({"storageClass", "size", "accessMode"})
_HTTP_NOT_FOUND = 404
_HTTP_CONFLICT = 409
#: Key of a Ravn resident's own OpenClaw shim token Secret (resident.openclaw.tokenSecret).
RESIDENT_OPENCLAW_TOKEN_KEY = "token"


@dataclass(frozen=True)
class ResidentVolumeClaim:
    """One PVC this controller creates and deletes for a single resident."""

    kind: str
    name: str
    size: str
    storage_class: str
    access_mode: str


class FluxPodManager(
    FluxHelmReleases,
    BrokeredCredentialPodManager,
    PodManager,
    ResidentRuntimeController,
    ResidentOpenClawShimHost,
):
    """Flux-native implementation of PodManager.

    Creates / deletes HelmRelease CRs via the Kubernetes API.
    Flux's helm-controller reconciles them into actual Helm releases.

    Constructor accepts plain kwargs (dynamic adapter pattern).
    """

    def __init__(
        self,
        *,
        namespace: str = "default",
        chart_name: str = "skuld",
        chart_version: str = "0.38.0",
        source_ref_kind: str = "HelmRepository",
        source_ref_name: str = "skuld",
        source_ref_namespace: str = "",
        timeout: str = "5m",
        interval: str = "5m",
        base_domain: str = "volundr.local",
        chat_scheme: str = "wss",
        code_scheme: str = "https",
        chat_path: str = "/session",
        code_path: str = "/",
        gateway_domain: str | None = None,
        session_defaults: dict | None = None,
        codex_auth_adapter: str = "skuld.codex_auth.VolundrCodexAuthProvider",
        codex_auth_kwargs: dict | None = None,
        resident_platform_base_url: str = "",
        resident_triggers_enabled: bool = False,
        resident_budget_enabled: bool = False,
        resident_home_size: str = "1Gi",
        resident_workspace_size: str = "2Gi",
        resident_storage_class: str = "",
        resident_access_mode: str = "ReadWriteOnce",
        **_extra: object,
    ):
        self._namespace = namespace
        self._chart_name = chart_name
        self._chart_version = chart_version
        self._source_ref_kind = source_ref_kind
        self._source_ref_name = source_ref_name
        self._source_ref_namespace = source_ref_namespace or namespace
        self._timeout = timeout
        self._interval = interval
        self._base_domain = base_domain
        self._chat_scheme = chat_scheme
        self._code_scheme = code_scheme
        self._chat_path = chat_path
        self._code_path = code_path
        self._gateway_domain = gateway_domain
        self._session_defaults = session_defaults or {}
        # Every managed resident gets platform reachability so its own
        # triggers/budget reporting (resident.triggers / resident.budget in
        # the skuld chart) can work — this is baseline platform
        # connectivity, not a Simple-mode-specific concern. Empty base URL
        # (the default) means the operator has not wired this controller to
        # a platform yet, so residents get no platform block at all rather
        # than one with an empty, unreachable base_url.
        self._resident_platform_base_url = resident_platform_base_url
        self._resident_triggers_enabled = resident_triggers_enabled
        self._resident_budget_enabled = resident_budget_enabled
        # Defaults for each resident's own home and workspace PVCs; a profile
        # overrides them per volume in deployment.volumes.<home|workspace>.
        # An empty storage class means the cluster's default class.
        # Each Ravn resident's own OpenClaw shim token, derived from Volundr's master by
        # the Ravn session controller (set_resident_openclaw_tokens). None: not configured.
        self._resident_openclaw_token: Callable[[ResidentRuntime], str] | None = None
        self._resident_volume_defaults = {
            "home": {
                "size": resident_home_size,
                "storageClass": resident_storage_class,
                "accessMode": resident_access_mode,
            },
            "workspace": {
                "size": resident_workspace_size,
                "storageClass": resident_storage_class,
                "accessMode": resident_access_mode,
            },
        }
        if not resident_platform_base_url and (
            resident_triggers_enabled or resident_budget_enabled
        ):
            # Without a base_url, _resident_values below never renders a
            # "platform" block at all — resident_triggers_enabled/
            # resident_budget_enabled would be silently ignored rather than
            # doing what the operator who set them clearly wants (residents
            # that execute triggers and report spend). Configured-but-
            # impossible is fatal, not a silent no-op. See no-fallbacks.md.
            raise ValueError(
                "FluxPodManager: resident_triggers_enabled/resident_budget_enabled "
                "require resident_platform_base_url to also be set — without it, "
                "residents get no platform block and these flags do nothing. Set "
                "podManager.kwargs.resident_platform_base_url (charts/volundr) "
                "or clear both flags."
            )
        self._configure_brokered_credentials(
            codex_auth_adapter=codex_auth_adapter,
            codex_auth_kwargs=codex_auth_kwargs,
        )
        self._api_client = None
        self._realm_repository = None

    def set_realm_repository(self, repository) -> None:
        """Enable resolving a resident's realm slug for its Helm values.

        Optional: without it, deploying a resident with ``realm_id`` set
        raises in ``_resolve_realm_slug`` rather than silently deploying with
        no realm/charter binding.
        """
        self._realm_repository = repository

    async def _resolve_realm_slug(self, runtime: ResidentRuntime) -> str:
        """Return the slug of the realm this resident is bound to, or "".

        Mirrors LocalContainerResidentRuntimeController._resolve_realm_slug.
        """
        if runtime.realm_id is None:
            return ""
        if self._realm_repository is None:
            raise RuntimeError(
                f"resident {runtime.name!r} has realm_id={runtime.realm_id} but this "
                "controller has no realm repository configured; call set_realm_repository "
                "at composition time."
            )
        realm = await self._realm_repository.get_realm(runtime.realm_id)
        if realm is None:
            raise RuntimeError(
                f"resident {runtime.name!r} names realm_id={runtime.realm_id}, but no "
                "such realm exists; clear the resident's realm binding or restore the realm."
            )
        return realm.slug

    async def _get_api(self):
        """Lazy-load kubernetes_asyncio custom objects API."""
        if self._api_client is None:
            self._api_client = await create_flux_api_client()
        from kubernetes_asyncio import client

        return client.CustomObjectsApi(self._api_client)

    async def _get_core_api(self):
        """CoreV1Api on the same client, for a resident's own PVCs."""
        await self._get_api()
        from kubernetes_asyncio import client

        return client.CoreV1Api(self._api_client)

    def _release_name(self, session: Session) -> str:
        return f"skuld-{session.id}"

    def _session_host(self, session_name: str) -> str:
        return f"{session_name}.{self._base_domain}"

    def _chat_endpoint(self, session_name: str, session_id: str = "") -> str:
        if self._gateway_domain:
            return f"wss://{self._gateway_domain}/s/{session_id}/session"
        return f"{self._chat_scheme}://{self._session_host(session_name)}{self._chat_path}"

    def initial_chat_endpoint(self, session: Session) -> str | None:
        return self._chat_endpoint(session.name, str(session.id))

    def _code_endpoint(self, session_name: str, session_id: str = "") -> str:
        if self._gateway_domain:
            return f"https://{self._gateway_domain}/s/{session_id}/"
        return f"{self._code_scheme}://{self._session_host(session_name)}{self._code_path}"

    def initial_code_endpoint(self, session: Session) -> str | None:
        return self._code_endpoint(session.name, str(session.id))

    async def start(
        self,
        session: Session,
        spec: SessionSpec,
    ) -> PodStartResult:
        """Create a HelmRelease CR for the session."""
        spec = self._with_brokered_credentials(spec)
        release_name = self._release_name(session)

        # Merge session defaults with spec values from contributors
        values = copy.deepcopy(self._session_defaults)
        _deep_merge(values, spec.values)

        # Translate pod_spec additions into Helm values
        if spec.pod_spec:
            if spec.pod_spec.env:
                env_vars = list(values.get("envVars") or [])
                env_names = {
                    str(entry.get("name"))
                    for entry in env_vars
                    if isinstance(entry, dict) and entry.get("name")
                }
                for env in spec.pod_spec.env:
                    env_dict = dict(env)
                    env_name = str(env_dict.get("name") or "")
                    if env_name and env_name in env_names:
                        env_vars = [
                            existing
                            for existing in env_vars
                            if not (
                                isinstance(existing, dict)
                                and str(existing.get("name") or "") == env_name
                            )
                        ]
                    env_vars.append(env_dict)
                    if env_name:
                        env_names.add(env_name)
                values["envVars"] = env_vars
            if spec.pod_spec.volumes:
                values["extraVolumes"] = [dict(v) for v in spec.pod_spec.volumes]
            if spec.pod_spec.volume_mounts:
                values["extraVolumeMounts"] = [dict(vm) for vm in spec.pod_spec.volume_mounts]
            if spec.pod_spec.init_containers:
                values["extraInitContainers"] = [
                    dict(container) for container in spec.pod_spec.init_containers
                ]
            if spec.pod_spec.extra_containers:
                values["extraContainers"] = [
                    dict(container) for container in spec.pod_spec.extra_containers
                ]
            if spec.pod_spec.service_account:
                values["serviceAccountName"] = spec.pod_spec.service_account
            if spec.pod_spec.labels:
                values["podLabels"] = dict(spec.pod_spec.labels)
            if spec.pod_spec.annotations:
                values["podAnnotations"] = dict(spec.pod_spec.annotations)

        _inject_workload_exchange_env(values)
        _inject_codex_auth_env(values)

        await self._apply_helmrelease(release_name, values)

        logger.info(
            "Created HelmRelease %s in namespace %s",
            release_name,
            self._namespace,
        )

        return PodStartResult(
            chat_endpoint=self._chat_endpoint(session.name, str(session.id)),
            code_endpoint=self._code_endpoint(session.name, str(session.id)),
            pod_name=release_name,
        )

    async def stop(self, session: Session) -> bool:
        """Delete the HelmRelease CR for the session."""
        release_name = self._release_name(session)
        return await self._delete_helmrelease(release_name)

    async def status(self, session: Session) -> SessionStatus:
        """Read HelmRelease status conditions and map to SessionStatus."""
        release_name = self._release_name(session)
        obj = await self._get_helmrelease(release_name)
        if obj is None:
            if session.status == SessionStatus.STARTING:
                return SessionStatus.STARTING
            if session.status == SessionStatus.PROVISIONING:
                # The release was created (provisioning began) and is now gone:
                # Flux remediation uninstalled it after a failed install. It
                # will never come back — reporting STARTING here spins forever
                # and STOPPED would surface as a successful completion upstream.
                logger.error(
                    "HelmRelease %s vanished while session %s was provisioning "
                    "— install failed and Flux uninstalled it; marking FAILED",
                    release_name,
                    session.id,
                )
                return SessionStatus.FAILED
            return SessionStatus.STOPPED

        return self._map_status(obj)

    @staticmethod
    def _map_status(obj: dict) -> SessionStatus:
        """Map HelmRelease .status.conditions to SessionStatus."""
        status = obj.get("status", {})
        conditions = status.get("conditions", [])

        for cond in conditions:
            if cond.get("type") != "Ready":
                continue
            if cond.get("status") == "True":
                return SessionStatus.RUNNING
            reason = cond.get("reason", "")
            if reason in (
                "InstallFailed",
                "UpgradeFailed",
                "ReconciliationFailed",
            ):
                return SessionStatus.FAILED
            return SessionStatus.STARTING

        # No Ready condition yet — still reconciling
        return SessionStatus.STARTING

    async def wait_for_ready(self, session: Session, timeout: float) -> SessionStatus:
        """Watch the HelmRelease CR until infrastructure is ready or failed."""
        # Check current status first to allow early return
        current = await self.status(session)
        if current in (SessionStatus.RUNNING, SessionStatus.FAILED):
            return current

        from kubernetes_asyncio import watch

        api = await self._get_api()
        release_name = self._release_name(session)

        w = watch.Watch()
        try:
            async for event in w.stream(
                api.list_namespaced_custom_object,
                group=HELMRELEASE_GROUP,
                version=HELMRELEASE_VERSION,
                namespace=self._namespace,
                plural=HELMRELEASE_PLURAL,
                field_selector=f"metadata.name={release_name}",
                timeout_seconds=int(timeout),
            ):
                if str(event.get("type") or "").upper() == "DELETED":
                    # Flux uninstalled the release mid-provisioning (install
                    # failed and remediation tore it down). Terminal — fail
                    # now instead of watching a void until the timeout.
                    logger.error(
                        "HelmRelease %s was deleted while waiting for readiness "
                        "— install failed and Flux uninstalled it; marking FAILED",
                        release_name,
                    )
                    return SessionStatus.FAILED
                obj = event.get("object", {})
                if not isinstance(obj, dict):
                    continue
                status = self._map_status(obj)
                if status == SessionStatus.RUNNING:
                    return SessionStatus.RUNNING
                if status == SessionStatus.FAILED:
                    return SessionStatus.FAILED
        except Exception as exc:
            logger.warning(
                "Watch stream error for HelmRelease %s: %s",
                release_name,
                exc,
                exc_info=True,
            )
            raise
        finally:
            w.stop()

        return await self.status(session)

    async def close(self) -> None:
        """Close the Kubernetes API client."""
        if self._api_client is not None:
            await self._api_client.close()
            self._api_client = None

    @property
    def backend(self) -> ResidentBackend:
        return ResidentBackend.HELMRELEASE

    def supports(self, profile: ResidentDeploymentProfile) -> bool:
        if (
            profile.backend is not ResidentBackend.HELMRELEASE
            or profile.engine is not ResidentEngine.RAVN
        ):
            return False
        values = profile.deployment.get("values") or {}
        return isinstance(values, dict) and resident_flock_profile_configured(profile, values)

    @staticmethod
    def _resident_release_name(runtime: ResidentRuntime) -> str:
        return f"resident-{runtime.id}"

    def _resident_service_account_values(self, runtime: ResidentRuntime) -> dict[str, Any]:
        """serviceAccountName for a resident's own workload identity.

        Only set when this controller has a platform to authenticate to
        (self._resident_platform_base_url) — a resident that never calls the
        platform has no need of a dedicated ServiceAccount or the RBAC that
        comes with one. When set, it is the *same* "resident-<uuid>" name as
        the release itself (_resident_release_name) — the chart's
        serviceaccount.yaml creates a ServiceAccount by this exact name (see
        charts/skuld/templates/serviceaccount.yaml), and the platform's
        workload-identity mapping's owner_id_claim_pattern
        (workloadIdentity.residentMapping in charts/volundr) extracts this
        same runtime id back out of the verified
        "system:serviceaccount:<namespace>:resident-<uuid>" subject — so
        GET/POST /api/v1/ravn/budget/* key rows by resident_runtimes.id, the
        same id the web already passes, instead of one id shared by every
        resident that matches a bare subject_prefix mapping.
        """
        if not self._resident_platform_base_url:
            return {}
        return {"serviceAccountName": self._resident_release_name(runtime)}

    def _backend_ref(self, runtime: ResidentRuntime) -> dict[str, Any]:
        release_name = self._resident_release_name(runtime)
        return {
            "apiVersion": f"{HELMRELEASE_GROUP}/{HELMRELEASE_VERSION}",
            "kind": "HelmRelease",
            "namespace": self._namespace,
            "name": release_name,
            "workloadSelector": f"app.kubernetes.io/instance={release_name}",
        }

    def _endpoints(self, runtime: ResidentRuntime) -> list[ResidentEndpoint]:
        return [
            ResidentEndpoint(
                kind="chat",
                protocol="skuld-v1",
                url=self._chat_endpoint(str(runtime.id), str(runtime.id)),
            )
        ]

    @staticmethod
    def _resident_claim_name(runtime: ResidentRuntime, kind: str) -> str:
        return f"resident-{runtime.id}-{kind}"

    def _resident_claims(
        self,
        runtime: ResidentRuntime,
        profile: ResidentDeploymentProfile,
    ) -> list[ResidentVolumeClaim]:
        """The PVCs this resident owns: its own home and its own workspace.

        A profile that names its own ``existingClaim`` (or turns the volume
        off, or uses ``persistence.emptyDir``) keeps that choice, and no PVC
        is created for that volume.
        """
        values = profile.deployment.get("values") or {}
        if not isinstance(values, dict):
            raise ValueError(f"Resident profile {profile.id} deployment.values must be an object")
        volumes = profile.deployment.get("volumes") or {}
        if not isinstance(volumes, dict):
            raise ValueError(f"Resident profile {profile.id} deployment.volumes must be an object")
        unknown = set(volumes) - set(RESIDENT_VOLUME_KINDS)
        if unknown:
            raise ValueError(
                f"Resident profile {profile.id} deployment.volumes has unknown "
                f"volumes {sorted(unknown)}; expected {list(RESIDENT_VOLUME_KINDS)}"
            )

        claims: list[ResidentVolumeClaim] = []
        if self._resident_owns_volume(values.get("homeVolume"), profile, "homeVolume"):
            claims.append(self._resident_claim(runtime, profile, "home", volumes.get("home")))
        if self._resident_owns_volume(values.get("persistence"), profile, "persistence"):
            claims.append(
                self._resident_claim(runtime, profile, "workspace", volumes.get("workspace"))
            )
        return claims

    @staticmethod
    def _resident_owns_volume(
        configured: object,
        profile: ResidentDeploymentProfile,
        key: str,
    ) -> bool:
        if configured is None:
            return True
        if not isinstance(configured, dict):
            raise ValueError(
                f"Resident profile {profile.id} deployment.values.{key} must be an object"
            )
        if configured.get("enabled") is False:
            return False
        if configured.get("emptyDir"):
            return False
        return not configured.get("existingClaim")

    def _resident_claim(
        self,
        runtime: ResidentRuntime,
        profile: ResidentDeploymentProfile,
        kind: str,
        configured: object,
    ) -> ResidentVolumeClaim:
        configured = configured or {}
        if not isinstance(configured, dict):
            raise ValueError(
                f"Resident profile {profile.id} deployment.volumes.{kind} must be an object"
            )
        unknown = set(configured) - RESIDENT_VOLUME_SETTINGS
        if unknown:
            raise ValueError(
                f"Resident profile {profile.id} deployment.volumes.{kind} has unknown "
                f"settings {sorted(unknown)}; expected {sorted(RESIDENT_VOLUME_SETTINGS)}"
            )
        settings = {**self._resident_volume_defaults[kind], **configured}
        for setting in ("size", "accessMode"):
            if not str(settings[setting] or ""):
                raise ValueError(
                    f"Resident profile {profile.id} deployment.volumes.{kind}.{setting} "
                    "must not be empty"
                )
        return ResidentVolumeClaim(
            kind=kind,
            name=self._resident_claim_name(runtime, kind),
            size=str(settings["size"]),
            storage_class=str(settings["storageClass"] or ""),
            access_mode=str(settings["accessMode"]),
        )

    @staticmethod
    def _resident_claim_values(claims: list[ResidentVolumeClaim]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for claim in claims:
            key = "homeVolume" if claim.kind == "home" else "persistence"
            values[key] = {"enabled": True, "existingClaim": claim.name}
        return values

    async def _ensure_resident_claims(
        self,
        runtime: ResidentRuntime,
        claims: list[ResidentVolumeClaim],
    ) -> None:
        """Create the resident's PVCs; an existing one must already be its own."""
        if not claims:
            return
        api = await self._get_core_api()
        for claim in claims:
            manifest = build_pvc_manifest(
                name=claim.name,
                namespace=self._namespace,
                storage=claim.size,
                storage_class=claim.storage_class or None,
                access_mode=claim.access_mode,
                labels={
                    LABEL_MANAGED_BY: self._managed_by,
                    # Not "home"/"workspace": those are the user home and
                    # session workspaces K8sStorageAdapter lists and manages.
                    LABEL_PVC_TYPE: f"resident-{claim.kind}",
                    LABEL_RESIDENT_ID: str(runtime.id),
                    LABEL_RESIDENT_OWNER_ID: runtime.owner_id,
                    LABEL_RESIDENT_TENANT_ID: runtime.tenant_id,
                },
            )
            try:
                await api.create_namespaced_persistent_volume_claim(
                    namespace=self._namespace,
                    body=manifest,
                )
                logger.info(
                    "Created resident %s PVC %s in namespace %s",
                    claim.kind,
                    claim.name,
                    self._namespace,
                )
                continue
            except Exception as exc:
                if getattr(exc, "status", None) != _HTTP_CONFLICT:
                    raise
            existing = await api.read_namespaced_persistent_volume_claim(
                name=claim.name,
                namespace=self._namespace,
            )
            labels = existing.metadata.labels or {}
            managed = labels.get(LABEL_MANAGED_BY) == self._managed_by
            owned = labels.get(LABEL_RESIDENT_ID) == str(runtime.id)
            if not (managed and owned):
                raise ValueError(
                    f"PVC {self._namespace}/{claim.name} exists but is not resident "
                    f"{runtime.id}'s own volume; delete or rename it before deploying"
                )

    async def _delete_resident_claims(self, runtime: ResidentRuntime) -> None:
        api = await self._get_core_api()
        for kind in RESIDENT_VOLUME_KINDS:
            name = self._resident_claim_name(runtime, kind)
            try:
                await api.delete_namespaced_persistent_volume_claim(
                    name=name,
                    namespace=self._namespace,
                )
                logger.info("Deleted resident %s PVC %s", kind, name)
            except Exception as exc:
                if getattr(exc, "status", None) != _HTTP_NOT_FOUND:
                    raise
                logger.debug("Resident %s PVC %s is already absent", kind, name)

    def set_resident_openclaw_tokens(
        self,
        resident_token: Callable[[ResidentRuntime], str],
    ) -> None:
        """Provision each Ravn resident's own shim token (RavnResidentSessionController)."""
        self._resident_openclaw_token = resident_token

    @staticmethod
    def _resident_openclaw_secret_name(runtime: ResidentRuntime) -> str:
        return f"resident-{runtime.id}-openclaw"

    def _resident_openclaw_enabled(
        self,
        runtime: ResidentRuntime,
        profile: ResidentDeploymentProfile,
    ) -> bool:
        values = profile.deployment.get("values") or {}
        return resident_openclaw_shim_enabled(
            runtime,
            values if isinstance(values, dict) else {},
            tokens_provisioned=self._resident_openclaw_token is not None,
        )

    def resident_openclaw_target(
        self,
        runtime: ResidentRuntime,
        port: int,
    ) -> SessionProxyTarget | None:
        """The shim's port on the resident's own Service (charts/skuld service.yaml)."""
        namespace = str(runtime.backend_ref.get("namespace") or "")
        release = str(runtime.backend_ref.get("name") or "")
        if not namespace or not release:
            return None
        host = f"{release}-skuld.{namespace}.svc.cluster.local"
        return SessionProxyTarget(
            service_url=f"http://{host}:{port}/",
            connect_host=host,
            connect_port=port,
        )

    async def _ensure_resident_openclaw_secret(
        self,
        runtime: ResidentRuntime,
        profile: ResidentDeploymentProfile,
    ) -> None:
        """Write the resident's own shim token; the pod never sees Volundr's master."""
        enabled = self._resident_openclaw_enabled(runtime, profile)
        resident_token = self._resident_openclaw_token
        if not enabled or resident_token is None:
            return
        name = self._resident_openclaw_secret_name(runtime)
        token = {RESIDENT_OPENCLAW_TOKEN_KEY: resident_token(runtime)}
        api = await self._get_core_api()
        try:
            await api.create_namespaced_secret(
                namespace=self._namespace,
                body={
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "type": "Opaque",
                    "metadata": {
                        "name": name,
                        "namespace": self._namespace,
                        "labels": {
                            LABEL_MANAGED_BY: self._managed_by,
                            LABEL_RESIDENT_ID: str(runtime.id),
                            LABEL_RESIDENT_OWNER_ID: runtime.owner_id,
                            LABEL_RESIDENT_TENANT_ID: runtime.tenant_id,
                        },
                    },
                    "stringData": token,
                },
            )
            logger.info("Created resident shim token Secret %s/%s", self._namespace, name)
            return
        except Exception as exc:
            if getattr(exc, "status", None) != _HTTP_CONFLICT:
                raise
        existing = await api.read_namespaced_secret(name=name, namespace=self._namespace)
        labels = existing.metadata.labels or {}
        if not (
            labels.get(LABEL_MANAGED_BY) == self._managed_by
            and labels.get(LABEL_RESIDENT_ID) == str(runtime.id)
        ):
            raise ValueError(
                f"Secret {self._namespace}/{name} exists but is not resident "
                f"{runtime.id}'s own shim token; delete or rename it before deploying"
            )
        # Keep it in step with the master Volundr derives from now.
        await api.patch_namespaced_secret(
            name=name,
            namespace=self._namespace,
            body={"stringData": token},
        )

    async def _delete_resident_openclaw_secret(self, runtime: ResidentRuntime) -> None:
        if self._resident_openclaw_token is None:
            # Without Ravn sessions Volundr writes no such Secret (and holds no Role for it).
            return
        name = self._resident_openclaw_secret_name(runtime)
        api = await self._get_core_api()
        try:
            await api.delete_namespaced_secret(name=name, namespace=self._namespace)
            logger.info("Deleted resident shim token Secret %s", name)
        except Exception as exc:
            if getattr(exc, "status", None) != _HTTP_NOT_FOUND:
                raise
            logger.debug("Resident shim token Secret %s is already absent", name)

    def _resident_values(
        self,
        runtime: ResidentRuntime,
        profile: ResidentDeploymentProfile,
        realm_slug: str = "",
    ) -> dict[str, Any]:
        configured_values = profile.deployment.get("values") or {}
        if not isinstance(configured_values, dict):
            raise ValueError(f"Resident profile {profile.id} deployment.values must be an object")
        values = self._with_cluster_volundr_api_url(configured_values)
        configured_resident = values.get("resident")
        configured_persona = ""
        if isinstance(configured_resident, dict):
            configured_persona = str(configured_resident.get("persona") or "")
        persona = runtime.persona_name or configured_persona
        if not persona:
            raise ValueError(f"Resident profile {profile.id} requires a persona")

        resident_values: dict[str, Any] = {
            "enabled": True,
            "name": runtime.name,
            "persona": persona,
            "routeId": str(runtime.id),
        }
        if self._resident_platform_base_url:
            resident_values["platform"] = {
                "enabled": True,
                "baseUrl": self._resident_platform_base_url,
            }
            if self._resident_triggers_enabled:
                resident_values["triggers"] = {"enabled": True}
            if self._resident_budget_enabled:
                resident_values["budget"] = {"enabled": True}
            # This release owns creating its ServiceAccount only because it
            # assigns one unique to this runtime (resident-<runtime.id> —
            # see _resident_service_account_values). Fleet-managed or
            # otherwise-shared ServiceAccount names must never be created
            # here (Helm ownership conflict, and uninstalling this one
            # release would delete an SA other residents still use) — see
            # charts/skuld's resident.serviceAccount.create (default false).
            resident_values["serviceAccount"] = {"create": True}
        if runtime.model:
            resident_values["llm"] = {"model": runtime.model}
        if runtime.flock_id is not None:
            resident_values["flock"] = {
                "id": str(runtime.flock_id),
                "memberId": str(runtime.flock_member_id or ""),
                "role": runtime.flock_role,
                "peerId": runtime.flock_peer_id,
            }
        if realm_slug:
            resident_values["realm"] = {"slug": realm_slug}
        if self._resident_openclaw_enabled(runtime, profile):
            resident_values["openclaw"] = {
                "enabled": True,
                "tokenSecret": {
                    "name": self._resident_openclaw_secret_name(runtime),
                    "key": RESIDENT_OPENCLAW_TOKEN_KEY,
                },
            }
        else:
            # Explicit either way: the chart's own default must not decide.
            resident_values["openclaw"] = {"enabled": False}

        flock_labels = resident_flock_labels(runtime, prefix="niuu.world")
        mesh_labels, mesh_annotations = resident_mesh_pod_metadata(runtime)

        runtime_values: dict[str, Any] = {
            "replicaCount": (0 if runtime.desired_state is ResidentDesiredState.SUSPENDED else 1),
            "session": {
                "id": str(runtime.id),
                "name": runtime.name,
                "ownerId": runtime.owner_id,
            },
            "resident": resident_values,
            # A resident is a resident runtime, not a Forge session: no
            # Forge session event log or activity exists for its id. Its
            # main-room history is skuld's own conversation file on its
            # workspace; usage goes to /resident-runtimes/<id>/usage.
            "broker": {"eventLogEnabled": False, "activityReportingEnabled": False},
            **self._resident_service_account_values(runtime),
            **self._resident_claim_values(self._resident_claims(runtime, profile)),
            "podLabels": {
                "niuu.world/managed": "true",
                "niuu.world/resident-id": str(runtime.id),
                "niuu.world/backend": runtime.backend.value,
                "niuu.world/engine": runtime.engine.value,
                **flock_labels,
                **mesh_labels,
            },
            "podAnnotations": {
                "niuu.world/resident-id": str(runtime.id),
                "niuu.world/resident-name": runtime.name,
                "niuu.world/owner-id": runtime.owner_id,
                "niuu.world/tenant-id": runtime.tenant_id,
                "niuu.world/visibility": "user",
                "niuu.world/profile-id": runtime.profile_id,
                **flock_labels,
                **mesh_annotations,
            },
        }
        if runtime.model:
            runtime_values["session"]["model"] = runtime.model
        _deep_merge(values, runtime_values)
        values = self._with_brokered_credential_values(values)
        _inject_workload_exchange_env(
            values,
            exchange_url=_resident_platform_exchange_url(values),
        )
        _inject_codex_auth_env(values)
        return values

    def _with_cluster_volundr_api_url(self, configured_values: dict[str, Any]) -> dict[str, Any]:
        """Profile values on top of this cluster's own Völundr API URL.

        A resident's cluster-local calls (its Forge event log, activity and
        usage reports, the Codex credential broker) belong to the Völundr that
        runs it, exactly as a session pod's do, so it gets the same
        ``volundr.apiUrl`` session pods get from ``session_defaults``. The
        platform (``resident.platform``) stays the target for platform APIs and
        the workload-token exchange. A profile that sets its own
        ``volundr.apiUrl`` keeps it.
        """
        session_volundr = self._session_defaults.get("volundr")
        cluster_api_url = ""
        if isinstance(session_volundr, dict):
            cluster_api_url = str(session_volundr.get("apiUrl") or "")
        if not cluster_api_url:
            return copy.deepcopy(configured_values)
        values: dict[str, Any] = {"volundr": {"apiUrl": cluster_api_url}}
        _deep_merge(values, copy.deepcopy(configured_values))
        return values

    async def deploy(
        self,
        runtime: ResidentRuntime,
        profile: ResidentDeploymentProfile,
    ) -> ResidentRuntimeObservation:
        release_name = self._resident_release_name(runtime)
        realm_slug = await self._resolve_realm_slug(runtime)
        await self._ensure_resident_claims(runtime, self._resident_claims(runtime, profile))
        await self._ensure_resident_openclaw_secret(runtime, profile)
        await self._apply_helmrelease(
            release_name,
            self._resident_values(runtime, profile, realm_slug),
            labels={
                "niuu.world/kind": "resident",
                "niuu.world/resident-id": str(runtime.id),
                "niuu.world/backend": runtime.backend.value,
                **resident_flock_labels(runtime, prefix="niuu.world"),
            },
            annotations={
                "niuu.world/owner-id": runtime.owner_id,
                "niuu.world/tenant-id": runtime.tenant_id,
                "niuu.world/profile-id": runtime.profile_id,
                **resident_flock_labels(runtime, prefix="niuu.world"),
            },
        )
        return ResidentRuntimeObservation(
            observed_state=ResidentObservedState.DEPLOYING,
            backend_ref=self._backend_ref(runtime),
            endpoints=self._endpoints(runtime),
            conditions=[
                ResidentCondition(
                    type="BackendReady",
                    status=ResidentConditionStatus.UNKNOWN,
                    reason="ReconciliationPending",
                    message="Flux is reconciling the resident HelmRelease",
                )
            ],
        )

    async def reconcile(
        self,
        runtime: ResidentRuntime,
        profile: ResidentDeploymentProfile,
    ) -> ResidentRuntimeObservation:
        release_name = self._resident_release_name(runtime)
        helmrelease = await self._get_helmrelease(release_name)
        if helmrelease is None:
            return await self.deploy(runtime, profile)

        desired_replicas = 0 if runtime.desired_state is ResidentDesiredState.SUSPENDED else 1
        values = (helmrelease.get("spec") or {}).get("values") or {}
        if values.get("replicaCount", 1) != desired_replicas:
            await self._set_replica_count(runtime, desired_replicas)

        deployment = await self._get_resident_deployment(release_name)
        return self._resident_observation(runtime, helmrelease, deployment)

    def _resident_observation(
        self,
        runtime: ResidentRuntime,
        helmrelease: dict[str, Any],
        deployment: dict[str, Any] | None,
    ) -> ResidentRuntimeObservation:
        backend_ref = self._backend_ref(runtime)
        deployment_name = self._deployment_name(deployment)
        if deployment_name:
            backend_ref["deploymentName"] = deployment_name
        return ResidentRuntimeObservation(
            observed_state=self._observed_state(runtime, helmrelease, deployment),
            backend_ref=backend_ref,
            endpoints=self._endpoints(runtime),
            conditions=self._normalized_conditions(helmrelease, deployment),
        )

    async def restart(
        self,
        runtime: ResidentRuntime,
        profile: ResidentDeploymentProfile,
    ) -> ResidentRuntimeObservation:
        restarted_at = datetime.now(UTC).isoformat()
        await self._patch_helmrelease(
            self._resident_release_name(runtime),
            {
                "spec": {
                    "values": {
                        "podAnnotations": {"niuu.world/restarted-at": restarted_at},
                    }
                }
            },
        )
        return await self._observe_after_lifecycle(runtime)

    async def suspend(self, runtime: ResidentRuntime) -> ResidentRuntimeObservation:
        await self._set_replica_count(runtime, 0)
        return await self._observe_after_lifecycle(runtime)

    async def resume(self, runtime: ResidentRuntime) -> ResidentRuntimeObservation:
        await self._set_replica_count(runtime, 1)
        return await self._observe_after_lifecycle(runtime)

    async def delete(self, runtime: ResidentRuntime) -> bool:
        """Delete the HelmRelease, then the resident's own PVCs and shim token Secret."""
        existed = await self._delete_helmrelease(self._resident_release_name(runtime))
        await self._delete_resident_claims(runtime)
        await self._delete_resident_openclaw_secret(runtime)
        return existed

    async def _set_replica_count(self, runtime: ResidentRuntime, replicas: int) -> None:
        await self._patch_helmrelease(
            self._resident_release_name(runtime),
            {"spec": {"values": {"replicaCount": replicas}}},
        )

    async def _observe_after_lifecycle(
        self,
        runtime: ResidentRuntime,
    ) -> ResidentRuntimeObservation:
        """Observe immediately after an explicit patch without needing profile data."""
        release_name = self._resident_release_name(runtime)
        helmrelease = await self._get_helmrelease(release_name)
        if helmrelease is None:
            return ResidentRuntimeObservation(
                observed_state=ResidentObservedState.FAILED,
                backend_ref=self._backend_ref(runtime),
                endpoints=self._endpoints(runtime),
                conditions=[
                    ResidentCondition(
                        type="BackendReady",
                        status=ResidentConditionStatus.FALSE,
                        reason="HelmReleaseNotFound",
                        message=f"HelmRelease {self._namespace}/{release_name} does not exist",
                    )
                ],
            )
        deployment = await self._get_resident_deployment(release_name)
        return self._resident_observation(runtime, helmrelease, deployment)

    async def _get_resident_deployment(self, release_name: str) -> dict[str, Any] | None:
        await self._get_api()
        from kubernetes_asyncio import client

        apps = client.AppsV1Api(self._api_client)
        result = await apps.list_namespaced_deployment(
            namespace=self._namespace,
            label_selector=f"app.kubernetes.io/instance={release_name}",
        )
        items = (
            result.get("items", []) if isinstance(result, dict) else getattr(result, "items", [])
        )
        if not items:
            return None
        deployment = items[0]
        if isinstance(deployment, dict):
            return deployment
        if hasattr(deployment, "to_dict"):
            return deployment.to_dict()
        return self._api_client.sanitize_for_serialization(deployment)

    @staticmethod
    def _deployment_name(deployment: dict[str, Any] | None) -> str:
        if not deployment:
            return ""
        metadata = deployment.get("metadata") or {}
        return str(metadata.get("name") or "")

    @classmethod
    def _observed_state(
        cls,
        runtime: ResidentRuntime,
        helmrelease: dict[str, Any],
        deployment: dict[str, Any] | None,
    ) -> ResidentObservedState:
        values = (helmrelease.get("spec") or {}).get("values") or {}
        replicas = values.get("replicaCount", 1)
        if runtime.desired_state is ResidentDesiredState.SUSPENDED:
            if replicas != 0:
                return ResidentObservedState.DEPLOYING
            if deployment is None:
                return ResidentObservedState.DEPLOYING
            deployment_spec = deployment.get("spec") or {}
            desired_replicas = int(deployment_spec.get("replicas") or 0)
            if desired_replicas == 0 and cls._available_replicas(deployment) == 0:
                return ResidentObservedState.SUSPENDED
            return ResidentObservedState.DEPLOYING

        ready = cls._ready_condition(helmrelease)
        if (
            ready
            and ready.get("status") == "False"
            and ready.get("reason")
            in {
                "InstallFailed",
                "UpgradeFailed",
                "ReconciliationFailed",
            }
        ):
            return ResidentObservedState.FAILED
        if not ready or ready.get("status") != "True" or deployment is None:
            return ResidentObservedState.DEPLOYING

        for condition in (deployment.get("status") or {}).get("conditions") or []:
            if condition.get("status") != "False":
                continue
            if condition.get("reason") in {"ProgressDeadlineExceeded", "ReplicaFailure"}:
                return ResidentObservedState.FAILED

        if cls._available_replicas(deployment) > 0:
            return ResidentObservedState.ACTIVE
        return ResidentObservedState.DEPLOYING

    @staticmethod
    def _available_replicas(deployment: dict[str, Any]) -> int:
        status = deployment.get("status") or {}
        return int(status.get("available_replicas") or status.get("availableReplicas") or 0)

    @staticmethod
    def _ready_condition(helmrelease: dict[str, Any]) -> dict[str, Any] | None:
        for condition in (helmrelease.get("status") or {}).get("conditions") or []:
            if condition.get("type") == "Ready":
                return condition
        return None

    @classmethod
    def _normalized_conditions(
        cls,
        helmrelease: dict[str, Any],
        deployment: dict[str, Any] | None,
    ) -> list[ResidentCondition]:
        normalized = [
            cls._normalize_condition("HelmRelease", condition)
            for condition in (helmrelease.get("status") or {}).get("conditions") or []
        ]
        if deployment is not None:
            normalized.extend(
                cls._normalize_condition("Deployment", condition)
                for condition in (deployment.get("status") or {}).get("conditions") or []
            )
        return normalized

    @staticmethod
    def _normalize_condition(source: str, condition: dict[str, Any]) -> ResidentCondition:
        raw_status = str(condition.get("status") or "Unknown").lower()
        status = ResidentConditionStatus.UNKNOWN
        if raw_status == "true":
            status = ResidentConditionStatus.TRUE
        if raw_status == "false":
            status = ResidentConditionStatus.FALSE
        transition = condition.get("lastTransitionTime") or condition.get("last_transition_time")
        if isinstance(transition, str):
            transition = datetime.fromisoformat(transition.replace("Z", "+00:00"))
        if not isinstance(transition, datetime):
            transition = datetime.now(UTC)
        return ResidentCondition(
            type=f"{source}{condition.get('type') or 'Condition'}",
            status=status,
            reason=str(condition.get("reason") or ""),
            message=str(condition.get("message") or ""),
            last_transition_at=transition,
        )


def _resident_platform_exchange_url(values: dict) -> str:
    """The platform's workload-token exchange for a resident, or "".

    Mirrors charts/skuld's skuld.residentWorkloadExchangeUrl: the explicit
    resident.platform.workloadExchangeUrl, else the platform base URL's. A
    resident without a platform has only its cluster's Völundr.
    """
    resident = values.get("resident")
    platform = resident.get("platform") if isinstance(resident, dict) else None
    if not isinstance(platform, dict) or not platform.get("enabled"):
        return ""
    explicit = str(platform.get("workloadExchangeUrl") or "").strip()
    if explicit:
        return explicit
    base_url = str(platform.get("baseUrl") or "").rstrip("/")
    if not base_url:
        return ""
    return f"{base_url}/api/v1/tokens/workload/exchange"


def _inject_workload_exchange_env(values: dict, *, exchange_url: str = "") -> None:
    """Propagate workload token exchange URL into all session containers.

    ``exchange_url`` names the exchange explicitly; without it the exchange is
    the one on ``volundr.apiUrl``.
    """
    if not exchange_url:
        volundr_cfg = values.get("volundr")
        if not isinstance(volundr_cfg, dict):
            return
        api_url = str(volundr_cfg.get("apiUrl") or "").rstrip("/")
        if not api_url:
            return
        exchange_url = f"{api_url}/api/v1/tokens/workload/exchange"
    env_entry = {
        "name": "NIUU_WORKLOAD_IDENTITY_EXCHANGE_URL",
        "value": exchange_url,
    }

    env_vars = list(values.get("envVars") or [])
    if not _has_env(env_vars, env_entry["name"]):
        env_vars.append(env_entry)
        values["envVars"] = env_vars

    extra_containers = values.get("extraContainers")
    if not isinstance(extra_containers, list):
        return
    for container in extra_containers:
        if not isinstance(container, dict):
            continue
        container_env = list(container.get("env") or [])
        if _has_env(container_env, env_entry["name"]):
            continue
        container_env.append(dict(env_entry))
        container["env"] = container_env


def _inject_codex_auth_env(values: dict) -> None:
    """Give every session container the Codex broker, not just the broker pod.

    A flock persona runs the same Codex transport Skuld does but builds it
    itself, so it needs the same SKULD__CODEX_AUTH__* contract. Reaching only
    the main container left all six research personas opening the Codex
    websocket with no credential — 401 on every turn, while the session itself
    looked healthy.
    """
    environment = BrokeredCredentialPodManager._brokered_credential_environment_values(values)
    if not environment:
        return

    entries = [{"name": name, "value": value} for name, value in sorted(environment.items())]

    env_vars = list(values.get("envVars") or [])
    for entry in entries:
        if not _has_env(env_vars, entry["name"]):
            env_vars.append(dict(entry))
    values["envVars"] = env_vars

    extra_containers = values.get("extraContainers")
    if not isinstance(extra_containers, list):
        return
    for container in extra_containers:
        if not isinstance(container, dict):
            continue
        container_env = list(container.get("env") or [])
        for entry in entries:
            if _has_env(container_env, entry["name"]):
                continue
            container_env.append(dict(entry))
        container["env"] = container_env


def _has_env(env: list, name: str) -> bool:
    return any(isinstance(entry, dict) and entry.get("name") == name for entry in env)
