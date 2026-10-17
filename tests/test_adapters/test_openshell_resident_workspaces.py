"""OpenShell residents' own workspace claims, and the one-time copy onto them."""

from __future__ import annotations

import asyncio
import copy
import io
import logging
import re
import tarfile
import types

import pytest

from tests.test_adapters.test_openshell_gateway import (
    _codex_auth_document,
    _FakeCredentialStore,
    _FakeOpenShellGatewayClient,
    _FakeWorkloadTokenIssuer,
    _import_adapter,
    _resident_profile,
    _resident_runtime,
)
from volundr.adapters.outbound import openshell_resident_workspace as workspace_module
from volundr.domain.models import (
    ResidentDeploymentProfile,
    ResidentObservedState,
)

NAMESPACE = "openshell-sandboxes"
WORKSPACE = "/sandbox/workspace"
OLD_IMAGE = "ghcr.io/niuulabs/openshell:dev-old"
TARGET_IMAGE = "ghcr.io/niuulabs/openshell:niu-1099-openshell-resident"


class _ApiError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


def _fake_manifest(*, name, namespace, storage, storage_class, access_mode, labels):
    return types.SimpleNamespace(
        metadata=types.SimpleNamespace(
            name=name,
            namespace=namespace,
            labels=dict(labels),
            annotations=None,
            resource_version=None,
        ),
        spec=types.SimpleNamespace(
            access_modes=[access_mode],
            storage_class_name=storage_class,
            resources=types.SimpleNamespace(requests={"storage": storage}),
        ),
    )


class _FakeCoreApi:
    """PVCs with resourceVersion compare-and-swap; reads return copies, like the API."""

    def __init__(self, events: list[str]) -> None:
        self.pvcs: dict[str, types.SimpleNamespace] = {}
        self.events = events
        self._version = 0

    def _bump(self, pvc) -> types.SimpleNamespace:
        self._version += 1
        pvc.metadata.resource_version = str(self._version)
        return copy.deepcopy(pvc)

    async def create_namespaced_persistent_volume_claim(self, *, namespace, body):
        assert namespace == NAMESPACE
        if body.metadata.name in self.pvcs:
            raise _ApiError(409)
        stored = copy.deepcopy(body)
        stored.metadata.annotations = dict(stored.metadata.annotations or {})
        self.pvcs[body.metadata.name] = stored
        self.events.append(f"pvc-created:{body.metadata.name}")
        return self._bump(stored)

    async def read_namespaced_persistent_volume_claim(self, *, name, namespace):
        assert namespace == NAMESPACE
        if name not in self.pvcs:
            raise _ApiError(404)
        return copy.deepcopy(self.pvcs[name])

    async def patch_namespaced_persistent_volume_claim(self, *, name, namespace, body):
        if name not in self.pvcs:
            raise _ApiError(404)
        stored = self.pvcs[name]
        metadata = body.get("metadata", {})
        expected = metadata.get("resourceVersion")
        if expected is not None and expected != stored.metadata.resource_version:
            raise _ApiError(409)
        for key, value in (metadata.get("annotations") or {}).items():
            if value is None:
                stored.metadata.annotations.pop(key, None)
            else:
                stored.metadata.annotations[key] = value
        storage = (body.get("spec") or {}).get("resources", {}).get("requests", {}).get("storage")
        if storage:
            stored.spec.resources.requests["storage"] = storage
        return self._bump(stored)

    async def delete_namespaced_persistent_volume_claim(self, *, name, namespace):
        if name not in self.pvcs:
            raise _ApiError(404)
        del self.pvcs[name]
        self.events.append(f"pvc-deleted:{name}")

    def phase(self, name: str) -> str | None:
        return (self.pvcs[name].metadata.annotations or {}).get(
            workspace_module.ANNOTATION_MIGRATION_PHASE
        )


class _Sandbox:
    def __init__(self, name, *, labels, image, annotations, providers=(), workspace=None):
        self.name = name
        self.id = f"id-{name}"
        self.labels = dict(labels)
        self.image = image
        self.annotations = dict(annotations)
        self.providers = tuple(providers)
        #: /sandbox outside the workspace: absolute path -> bytes.
        self.home: dict[str, bytes] = {}
        #: The workspace: relative path -> bytes (the claim's dict when mounted).
        self.workspace: dict[str, bytes] = workspace if workspace is not None else {}
        self.running = False
        self.links: dict[str, str] = {}


class _SandboxFleetClient(_FakeOpenShellGatewayClient):
    """A gateway with several sandboxes, their files, and claims they mount."""

    def __init__(self, adapter, events: list[str]) -> None:
        super().__init__(adapter)
        self.sandboxes: dict[str, _Sandbox] = {}
        self.claim_files: dict[str, dict[str, bytes]] = {}
        self.events = events
        self.corrupt_restore = False
        self.fail_restore_with: BaseException | None = None

    # -- sandboxes ---------------------------------------------------------------
    def add(self, sandbox: _Sandbox) -> _Sandbox:
        self.sandboxes[sandbox.name] = sandbox
        return sandbox

    def by_id(self, sandbox_id: str) -> _Sandbox:
        return next(item for item in self.sandboxes.values() if item.id == sandbox_id)

    def create_sandbox(self, **kwargs):
        self.created = kwargs
        claim = _mounted_claim(kwargs.get("driver_config") or {})
        workspace = self.claim_files.setdefault(claim, {}) if claim else None
        sandbox = self.add(
            _Sandbox(
                kwargs["name"],
                labels=kwargs.get("labels") or {},
                image=kwargs.get("image") or "",
                annotations=kwargs.get("annotations") or {},
                providers=kwargs.get("providers") or (),
                workspace=workspace,
            )
        )
        self.events.append(f"created:{sandbox.name}")
        return self._proto(sandbox, ready=False)

    def get_sandbox(self, name: str):
        sandbox = self.sandboxes.get(name)
        return None if sandbox is None else self._proto(sandbox, ready=True)

    def _proto(self, sandbox: _Sandbox, *, ready: bool):
        return self._adapter.OpenShellSandbox(
            id=sandbox.id,
            name=sandbox.name,
            phase=(
                self._adapter.openshell_pb2.SANDBOX_PHASE_READY
                if ready
                else self._adapter.openshell_pb2.SANDBOX_PHASE_PROVISIONING
            ),
            ready=ready,
            labels=sandbox.labels,
            providers=sandbox.providers,
            image=sandbox.image,
            annotations=sandbox.annotations,
        )

    def delete_sandbox(self, name: str) -> bool:
        self.deleted.append(name)
        self.events.append(f"deleted:{name}")
        return self.sandboxes.pop(name, None) is not None

    # -- files and processes ---------------------------------------------------------
    def _resolve(self, sandbox: _Sandbox, path: str) -> tuple[dict[str, bytes], str]:
        if path == WORKSPACE or path.startswith(f"{WORKSPACE}/"):
            return sandbox.workspace, path[len(WORKSPACE) :].strip("/")
        return sandbox.home, path

    def write_files(self, *, sandbox_id: str, files: dict[str, bytes]) -> None:
        self.written_files.append({"sandbox_id": sandbox_id, "files": files})
        sandbox = self.by_id(sandbox_id)
        for path, content in files.items():
            store, key = self._resolve(sandbox, path)
            store[key] = content

    def exec_detached(self, **kwargs) -> int:
        self.execs.append(kwargs)
        sandbox = self.by_id(kwargs["sandbox_id"])
        sandbox.running = True
        self.events.append(f"launched:{sandbox.name}")
        return 0

    def exec_script(self, *, sandbox_id: str, script: str, env: dict) -> tuple[int, str]:
        self.bootstrap_execs.append({"sandbox_id": sandbox_id, "script": script, "env": env})
        sandbox = self.by_id(sandbox_id)
        if "du -sk" in script:
            lines = []
            for source in re.findall(r"(/sandbox/[\w./-]+)", script.split("do")[0]):
                entries = self._tree(sandbox, source)
                if entries is not None:
                    size = sum(len(content) for content in entries.values())
                    lines.append(f"{max(1, size // 1024)}\t{source}")
            return 0, "\n".join(lines) + "\n"
        if "kill -9" in script:
            sandbox.running = False
            self.events.append(f"stopped:{sandbox.name}")
            return 0, ""
        if "kill -0" in script:
            return (0 if sandbox.running else 1), ""
        if "find . -mindepth 1" in script:
            sandbox.workspace.clear()
            self.events.append(f"cleared:{sandbox.name}")
            return 0, ""
        if "ln -s" in script:
            link = re.search(r"link=(\S+)", script).group(1)
            target = re.search(r"target=(\S+)", script).group(1)
            sandbox.links[link] = target
            self.events.append(f"linked:{sandbox.name}:{link}")
            return 0, ""
        return 0, ""

    def _tree(self, sandbox: _Sandbox, source: str) -> dict[str, bytes] | None:
        if source == WORKSPACE:
            return dict(sandbox.workspace)
        prefix = f"{source}/"
        entries = {
            path[len(prefix) :]: content
            for path, content in sandbox.home.items()
            if path.startswith(prefix)
        }
        return entries or None

    def exec_to_file(self, *, sandbox_id, script, destination, max_bytes, timeout_seconds):
        sandbox = self.by_id(sandbox_id)
        source = re.search(r"cd (\S+)", script).group(1)
        archive = _tar(self._tree(sandbox, source) or {})
        self.events.append(f"archived:{sandbox.name}:{source}")
        if len(archive) > max_bytes:
            destination.write(archive[:max_bytes])
            return self._adapter.OpenShellTransfer(None, "", max_bytes, truncated=True)
        destination.write(archive)
        return self._adapter.OpenShellTransfer(0, "", len(archive))

    def exec_from_file(self, *, sandbox_id, command, source, timeout_seconds):
        if self.fail_restore_with is not None:
            raise self.fail_restore_with
        sandbox = self.by_id(sandbox_id)
        target = re.search(r"-C (\S+)", command[-1]).group(1)
        prefix = target[len(WORKSPACE) :].strip("/")
        with tarfile.open(fileobj=io.BytesIO(source.read()), mode="r") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                name = member.name.removeprefix("./")
                if self.corrupt_restore and name.endswith("memory.db"):
                    continue
                key = f"{prefix}/{name}" if prefix else name
                sandbox.workspace[key] = tar.extractfile(member).read()
        self.events.append(f"restored:{sandbox.name}:{target}")
        return self._adapter.OpenShellTransfer(0, "", 0)


def _mounted_claim(driver_config: dict) -> str:
    config = driver_config.get("kubernetes", driver_config)
    for volume in config.get("volumes", []):
        claim = volume.get("persistent_volume_claim")
        if claim:
            return claim["claim_name"]
    return ""


def _tar(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        root = tarfile.TarInfo(".")
        root.type = tarfile.DIRTYPE
        tar.addfile(root)
        seen: set[str] = set()
        for path in sorted(entries):
            parts = path.split("/")
            for depth in range(1, len(parts)):
                parent = "/".join(parts[:depth])
                if parent not in seen:
                    seen.add(parent)
                    info = tarfile.TarInfo(f"./{parent}")
                    info.type = tarfile.DIRTYPE
                    tar.addfile(info)
            info = tarfile.TarInfo(f"./{path}")
            info.size = len(entries[path])
            tar.addfile(info, io.BytesIO(entries[path]))
    return buffer.getvalue()


class _Harness:
    def __init__(self, monkeypatch, **kwargs) -> None:
        self.events: list[str] = []
        self.adapter = _import_adapter(monkeypatch)
        self.client = _SandboxFleetClient(self.adapter, self.events)
        self.core = _FakeCoreApi(self.events)
        self.credentials = _FakeCredentialStore(
            {"codex-credentials": {"auth.json": _codex_auth_document()}}
        )
        monkeypatch.setattr(workspace_module, "build_pvc_manifest", _fake_manifest)
        core = self.core

        async def get_core_api(_self):
            return core

        monkeypatch.setattr(self.adapter.OpenShellGatewayPodManager, "_get_core_api", get_core_api)
        self.manager = self.manager_for(**kwargs)

    def manager_for(self, **kwargs):
        settings = {
            "resident_workspace_namespace": NAMESPACE,
            "resident_workspace_migration_holder": "volundr-a",
            **kwargs,
        }
        manager = self.adapter.OpenShellGatewayPodManager(
            client=self.client,
            volundr_api_url="https://volundr.example.test",
            workload_audiences=["volundr-api", "mimir", "guild"],
            ready_timeout=1.0,
            **settings,
        )
        manager.set_credential_store(self.credentials)
        manager.set_workload_token_issuer(_FakeWorkloadTokenIssuer())
        return manager

    def old_sandbox(self, runtime, *, image: str = OLD_IMAGE) -> _Sandbox:
        sandbox = self.client.add(
            _Sandbox(
                f"r-{runtime.id.hex[:17]}",
                labels={"volundr.niuu.io/resident": str(runtime.id)},
                image=image,
                annotations={"volundr.niuu.io/image": image},
            )
        )
        sandbox.workspace.update(
            {
                ".ravn/openclaw/state.db": b"notification outbox",
                ".skuld/conversation_1.json": b'{"turns": 3}',
                "notes/plan.md": b"# plan",
            }
        )
        sandbox.home.update(
            {
                "/sandbox/.ravn/memory.db": b"episodes",
                "/sandbox/.ravn/daemon/queue.json": b"[]",
                "/sandbox/.volundr/ravn.yaml": b"rendered",
            }
        )
        sandbox.running = True
        return sandbox


def _running(runtime, sandbox_name: str):
    return runtime.model_copy(
        update={
            "observed_state": ResidentObservedState.ACTIVE,
            "backend_ref": {
                "kind": "OpenShellSandbox",
                "id": f"id-{sandbox_name}",
                "name": sandbox_name,
                "service_url": "http://openshell.example/proxy/session-1",
                "service_name": "skuld",
            },
        }
    )


def _awaiting_deployment(runtime):
    return runtime.model_copy(
        update={"observed_state": ResidentObservedState.PENDING, "backend_ref": {}}
    )


def _condition(observation, kind: str):
    return next((item for item in observation.conditions if item.type == kind), None)


def _claim_name(runtime) -> str:
    return f"resident-{runtime.id}-workspace"


def _profile_with(values: dict) -> ResidentDeploymentProfile:
    profile = _resident_profile()
    merged = {**profile.deployment["values"], **values}
    return profile.model_copy(update={"deployment": {**profile.deployment, "values": merged}})


@pytest.mark.asyncio
async def test_new_resident_gets_its_own_claim_mounted_at_the_workspace(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()

    observation = await harness.manager.deploy(runtime, _resident_profile())

    claim = harness.core.pvcs[_claim_name(runtime)]
    assert claim.metadata.labels == {
        "app.kubernetes.io/managed-by": "volundr",
        "volundr/pvc-type": "resident-workspace",
        "niuu.world/resident-id": str(runtime.id),
        "niuu.world/owner-id": runtime.owner_id,
        "niuu.world/tenant-id": runtime.tenant_id,
    }
    assert claim.spec.resources.requests == {"storage": "2Gi"}
    assert claim.spec.access_modes == ["ReadWriteOnce"]
    assert workspace_module.workspace_migration_state(claim) is None
    created = harness.client.created
    assert created["name"] == f"r-{runtime.id.hex[:17]}"
    assert created["annotations"]["volundr.niuu.io/workspace-claim"] == _claim_name(runtime)
    assert created["driver_config"]["volumes"] == [
        {
            "name": "forge-workspace",
            "persistent_volume_claim": {"claim_name": _claim_name(runtime), "read_only": False},
        }
    ]
    assert created["driver_config"]["containers"]["agent"]["volume_mounts"] == [
        {"name": "forge-workspace", "mount_path": WORKSPACE, "read_only": False}
    ]
    # Ravn's ~/.ravn state (memory.db, the queue, cron) is kept on the claim too.
    sandbox = harness.client.sandboxes[created["name"]]
    assert sandbox.links == {"/sandbox/.ravn": f"{WORKSPACE}/.ravn-home"}
    assert harness.events.index(f"linked:{sandbox.name}:/sandbox/.ravn") < harness.events.index(
        f"launched:{sandbox.name}"
    )
    assert observation.backend_ref["workspace_claim"] == _claim_name(runtime)
    assert observation.observed_state is ResidentObservedState.ACTIVE


@pytest.mark.asyncio
async def test_claim_size_and_class_come_from_settings_and_the_profile(monkeypatch):
    harness = _Harness(
        monkeypatch, resident_workspace_size="5Gi", resident_storage_class="harvester"
    )
    runtime = _resident_runtime()
    profile = _resident_profile().model_copy(
        update={
            "deployment": {
                **_resident_profile().deployment,
                "volumes": {"workspace": {"size": "8Gi"}},
            }
        }
    )

    await harness.manager.deploy(runtime, profile)

    claim = harness.core.pvcs[_claim_name(runtime)]
    assert claim.spec.resources.requests == {"storage": "8Gi"}
    assert claim.spec.storage_class_name == "harvester"


@pytest.mark.asyncio
async def test_delete_removes_the_sandbox_then_the_claim(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    observation = await harness.manager.deploy(runtime, _resident_profile())
    deployed = runtime.model_copy(update={"backend_ref": observation.backend_ref})

    await harness.manager.delete(deployed)

    assert _claim_name(runtime) not in harness.core.pvcs
    assert harness.events.index(f"deleted:{observation.backend_ref['name']}") < (
        harness.events.index(f"pvc-deleted:{_claim_name(runtime)}")
    )


@pytest.mark.asyncio
async def test_delete_leaves_a_claim_that_is_not_the_residents(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    foreign = _fake_manifest(
        name=_claim_name(runtime),
        namespace=NAMESPACE,
        storage="1Gi",
        storage_class=None,
        access_mode="ReadWriteOnce",
        labels={"app": "something-else"},
    )
    await harness.core.create_namespaced_persistent_volume_claim(namespace=NAMESPACE, body=foreign)

    await harness.manager.delete(runtime)

    assert _claim_name(runtime) in harness.core.pvcs


@pytest.mark.asyncio
async def test_existing_resident_is_migrated_verified_then_started_on_its_claim(
    monkeypatch, caplog
):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    old = harness.old_sandbox(runtime)
    runtime = _running(runtime, old.name)
    profile = _resident_profile()
    caplog.set_level(logging.INFO)

    # Reconcile changes nothing itself: it hands the resident to a deployment.
    pending = await harness.manager.reconcile(runtime, profile)
    assert pending.observed_state is ResidentObservedState.PENDING
    assert pending.backend_ref == {}
    assert _condition(pending, "WorkspaceMigration").reason == "Migrating"
    assert harness.core.pvcs == {}
    assert old.running

    observation = await harness.manager.deploy(_awaiting_deployment(runtime), profile)

    new_name = f"m-{runtime.id.hex[:17]}"
    events = harness.events
    # Archive with the processes stopped, restore and verify, and only then remove
    # the old sandbox and start the resident in the new one.
    assert events.index(f"stopped:{old.name}") < events.index(f"archived:{old.name}:{WORKSPACE}")
    assert events.index(f"archived:{old.name}:/sandbox/.ravn") < events.index(f"created:{new_name}")
    assert events.index(f"restored:{new_name}:{WORKSPACE}") < events.index(
        f"restored:{new_name}:{WORKSPACE}/.ravn-home"
    )
    assert events.index(f"restored:{new_name}:{WORKSPACE}/.ravn-home") < events.index(
        f"deleted:{old.name}"
    )
    assert events.index(f"deleted:{old.name}") < events.index(f"launched:{new_name}")
    assert old.name not in harness.client.sandboxes
    files = harness.client.claim_files[_claim_name(runtime)]
    assert files[".ravn/openclaw/state.db"] == b"notification outbox"
    assert files[".skuld/conversation_1.json"] == b'{"turns": 3}'
    assert files[".ravn-home/memory.db"] == b"episodes"
    assert files[".ravn-home/daemon/queue.json"] == b"[]"
    claim = harness.core.pvcs[_claim_name(runtime)]
    annotations = claim.metadata.annotations
    assert annotations[workspace_module.ANNOTATION_MIGRATION_PHASE] == "complete"
    assert annotations[workspace_module.ANNOTATION_MIGRATION_SOURCE] == old.name
    assert annotations[workspace_module.ANNOTATION_MIGRATION_DIGEST].startswith("files=5 ")
    assert workspace_module.ANNOTATION_MIGRATION_HOLDER not in annotations
    new = harness.client.sandboxes[new_name]
    assert new.image == TARGET_IMAGE
    assert new.annotations["volundr.niuu.io/replaced-image"] == OLD_IMAGE
    assert new.links == {"/sandbox/.ravn": f"{WORKSPACE}/.ravn-home"}
    # The resident's grants stayed in place for both sandboxes; nothing was revoked.
    assert harness.client.deleted_grants == []
    assert harness.credentials.deletes == []
    assert observation.backend_ref["name"] == new_name
    assert observation.backend_ref["workspace_claim"] == _claim_name(runtime)
    assert observation.backend_ref["image"] == TARGET_IMAGE
    assert observation.observed_state is ResidentObservedState.ACTIVE
    messages = [record.getMessage() for record in caplog.records]
    assert sum("workspace to a persistent volume" in message for message in messages) == 1
    assert any("verified; sandbox" in message for message in messages)

    # Afterwards the resident is an ordinary persisted resident: nothing more to do.
    settled = await harness.manager.reconcile(
        runtime.model_copy(update={"backend_ref": observation.backend_ref}), profile
    )
    assert _condition(settled, "WorkspaceMigration") is None
    assert settled.backend_ref["name"] == new_name


@pytest.mark.asyncio
async def test_failed_copy_keeps_the_old_sandbox_and_reports_why(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    old = harness.old_sandbox(runtime)
    runtime = _running(runtime, old.name)
    profile = _resident_profile()
    harness.client.corrupt_restore = True

    observation = await harness.manager.deploy(_awaiting_deployment(runtime), profile)

    new_name = f"m-{runtime.id.hex[:17]}"
    assert old.name in harness.client.sandboxes
    assert new_name not in harness.client.sandboxes
    assert old.home["/sandbox/.ravn/memory.db"] == b"episodes"
    assert old.running  # its processes were started again
    assert harness.client.deleted_grants == []
    assert harness.credentials.deletes == []
    condition = _condition(observation, "WorkspaceMigration")
    assert condition.reason == "VerificationFailed"
    assert "keeps running on its old sandbox" in condition.message
    assert observation.backend_ref["name"] == old.name
    assert "workspace_claim" not in observation.backend_ref
    assert observation.observed_state is ResidentObservedState.ACTIVE
    claim = harness.core.pvcs[_claim_name(runtime)]
    assert harness.core.phase(_claim_name(runtime)) == "copying"
    assert workspace_module.ANNOTATION_MIGRATION_HOLDER not in claim.metadata.annotations
    upgrade = _condition(observation, "PlatformUpgrade")
    assert upgrade.reason == "UpgradeHeld"

    # Reconcile reports it and leaves the sandbox alone: no retry on every pass.
    harness.client.corrupt_restore = False
    created_before = harness.events.count(f"created:{new_name}")
    reconciled = await harness.manager.reconcile(
        runtime.model_copy(update={"backend_ref": observation.backend_ref}), profile
    )
    assert _condition(reconciled, "WorkspaceMigration").reason == "VerificationFailed"
    assert harness.events.count(f"created:{new_name}") == created_before
    assert old.name in harness.client.sandboxes

    # Restart retries, and this time the copy verifies.
    restarted = await harness.manager.restart(
        runtime.model_copy(update={"backend_ref": observation.backend_ref}), profile
    )
    assert restarted.backend_ref["name"] == new_name
    assert old.name not in harness.client.sandboxes
    assert harness.core.phase(_claim_name(runtime)) == "complete"


@pytest.mark.asyncio
async def test_workspace_over_the_limit_changes_nothing(monkeypatch):
    harness = _Harness(monkeypatch, resident_workspace_migration_max_size="1Ki")
    runtime = _resident_runtime()
    old = harness.old_sandbox(runtime)
    old.workspace["big.bin"] = b"x" * 4096
    runtime = _running(runtime, old.name)

    observation = await harness.manager.deploy(_awaiting_deployment(runtime), _resident_profile())

    condition = _condition(observation, "WorkspaceMigration")
    assert condition.reason == "WorkspaceTooLarge"
    assert "over the 1Ki migration limit; nothing was changed" in condition.message
    assert harness.core.pvcs == {}
    assert f"stopped:{old.name}" not in harness.events
    assert not any(event.startswith("archived:") for event in harness.events)
    assert set(harness.client.sandboxes) == {old.name}
    assert observation.backend_ref["name"] == old.name


@pytest.mark.asyncio
async def test_workspace_larger_than_its_claim_changes_nothing(monkeypatch):
    harness = _Harness(monkeypatch, resident_workspace_size="1Ki")
    runtime = _resident_runtime()
    old = harness.old_sandbox(runtime)
    old.workspace["big.bin"] = b"x" * 4096
    runtime = _running(runtime, old.name)

    observation = await harness.manager.deploy(_awaiting_deployment(runtime), _resident_profile())

    condition = _condition(observation, "WorkspaceMigration")
    assert condition.reason == "WorkspaceTooLarge"
    assert "more than its 1Ki volume" in condition.message
    assert harness.core.pvcs == {}


@pytest.mark.asyncio
async def test_migration_resumes_after_volundr_restarts_mid_copy(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    old = harness.old_sandbox(runtime)
    runtime = _running(runtime, old.name)
    profile = _resident_profile()
    new_name = f"m-{runtime.id.hex[:17]}"
    # Völundr stops (its pod is replaced) while it restores the copy.
    harness.client.fail_restore_with = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await harness.manager.deploy(_awaiting_deployment(runtime), profile)

    assert harness.core.phase(_claim_name(runtime)) == "copying"
    assert {old.name, new_name} <= set(harness.client.sandboxes)
    harness.client.fail_restore_with = None

    # Another Völundr finds the lease still held by the first: it does not touch it.
    successor = harness.manager_for(resident_workspace_migration_holder="volundr-b")
    with pytest.raises(workspace_module.WorkspaceMigrationHeldError):
        await successor.deploy(_awaiting_deployment(runtime), profile)
    assert old.name in harness.client.sandboxes

    # Once the lease expires it takes over: the stale sandbox goes, the copy restarts.
    harness.core.pvcs[_claim_name(runtime)].metadata.annotations[
        workspace_module.ANNOTATION_MIGRATION_EXPIRES
    ] = "0"
    observation = await successor.deploy(_awaiting_deployment(runtime), profile)

    assert observation.backend_ref["name"] == new_name
    assert set(harness.client.sandboxes) == {new_name}
    assert harness.events.count(f"deleted:{new_name}") == 1
    assert harness.core.phase(_claim_name(runtime)) == "complete"
    files = harness.client.claim_files[_claim_name(runtime)]
    assert files[".ravn-home/memory.db"] == b"episodes"
    assert files["notes/plan.md"] == b"# plan"


@pytest.mark.asyncio
async def test_migration_finishes_when_only_the_verified_copy_is_left(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    claim_name = _claim_name(runtime)
    await harness.core.create_namespaced_persistent_volume_claim(
        namespace=NAMESPACE,
        body=_fake_manifest(
            name=claim_name,
            namespace=NAMESPACE,
            storage="2Gi",
            storage_class=None,
            access_mode="ReadWriteOnce",
            labels={
                "app.kubernetes.io/managed-by": "volundr",
                "volundr/pvc-type": "resident-workspace",
                "niuu.world/resident-id": str(runtime.id),
            },
        ),
    )
    harness.core.pvcs[claim_name].metadata.annotations = {
        workspace_module.ANNOTATION_MIGRATION_PHASE: "verified",
        workspace_module.ANNOTATION_MIGRATION_SOURCE: f"r-{runtime.id.hex[:17]}",
    }

    observation = await harness.manager.deploy(_awaiting_deployment(runtime), _resident_profile())

    assert harness.core.phase(claim_name) == "complete"
    assert observation.backend_ref["workspace_claim"] == claim_name


@pytest.mark.asyncio
async def test_partial_copy_without_its_source_is_never_started(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    claim_name = _claim_name(runtime)
    await harness.core.create_namespaced_persistent_volume_claim(
        namespace=NAMESPACE,
        body=_fake_manifest(
            name=claim_name,
            namespace=NAMESPACE,
            storage="2Gi",
            storage_class=None,
            access_mode="ReadWriteOnce",
            labels={
                "app.kubernetes.io/managed-by": "volundr",
                "volundr/pvc-type": "resident-workspace",
                "niuu.world/resident-id": str(runtime.id),
            },
        ),
    )
    harness.core.pvcs[claim_name].metadata.annotations = {
        workspace_module.ANNOTATION_MIGRATION_PHASE: "copying",
        workspace_module.ANNOTATION_MIGRATION_SOURCE: f"r-{runtime.id.hex[:17]}",
    }

    with pytest.raises(workspace_module.WorkspaceMigrationError, match="partial copy"):
        await harness.manager.deploy(_awaiting_deployment(runtime), _resident_profile())

    assert harness.client.sandboxes == {}


@pytest.mark.asyncio
async def test_a_claim_that_already_holds_a_workspace_is_never_overwritten(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    old = harness.old_sandbox(runtime)
    runtime = _running(runtime, old.name)
    claim_name = _claim_name(runtime)
    await harness.core.create_namespaced_persistent_volume_claim(
        namespace=NAMESPACE,
        body=_fake_manifest(
            name=claim_name,
            namespace=NAMESPACE,
            storage="2Gi",
            storage_class=None,
            access_mode="ReadWriteOnce",
            labels={
                "app.kubernetes.io/managed-by": "volundr",
                "volundr/pvc-type": "resident-workspace",
                "niuu.world/resident-id": str(runtime.id),
            },
        ),
    )
    harness.client.claim_files[claim_name] = {"precious.txt": b"newer state"}

    observation = await harness.manager.deploy(_awaiting_deployment(runtime), _resident_profile())

    assert _condition(observation, "WorkspaceMigration").reason == "ClaimInUse"
    assert harness.client.claim_files[claim_name] == {"precious.txt": b"newer state"}
    assert f"stopped:{old.name}" not in harness.events
    assert old.name in harness.client.sandboxes


@pytest.mark.asyncio
async def test_resident_on_its_own_existing_claim_is_untouched(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    old = harness.old_sandbox(runtime, image=TARGET_IMAGE)
    runtime = _running(runtime, old.name)
    profile = _profile_with(
        {"persistence": {"existingClaim": "volundr-sessions", "mountPath": WORKSPACE}}
    )

    observation = await harness.manager.reconcile(runtime, profile)

    assert harness.core.pvcs == {}
    assert _condition(observation, "WorkspaceMigration") is None
    assert observation.backend_ref["name"] == old.name
    assert not any(event.startswith(("stopped:", "archived:")) for event in harness.events)


@pytest.mark.asyncio
async def test_resident_already_on_its_claim_is_untouched(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    sandbox = harness.old_sandbox(runtime, image=TARGET_IMAGE)
    sandbox.annotations["volundr.niuu.io/workspace-claim"] = _claim_name(runtime)
    runtime = _running(runtime, sandbox.name)

    observation = await harness.manager.reconcile(runtime, _resident_profile())

    assert _condition(observation, "WorkspaceMigration") is None
    assert observation.backend_ref["workspace_claim"] == _claim_name(runtime)
    assert not any(
        event.startswith(("stopped:", "archived:", "created:")) for event in harness.events
    )


@pytest.mark.asyncio
async def test_profile_that_turns_persistence_off_keeps_the_held_upgrade(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    old = harness.old_sandbox(runtime)
    runtime = _running(runtime, old.name)

    observation = await harness.manager.reconcile(
        runtime, _profile_with({"persistence": {"enabled": False}})
    )

    assert harness.core.pvcs == {}
    assert _condition(observation, "PlatformUpgrade").reason == "UpgradeHeld"
    assert old.name in harness.client.sandboxes


@pytest.mark.asyncio
async def test_upgrade_proceeds_once_the_resident_is_on_its_claim(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    old = harness.old_sandbox(runtime)
    runtime = _running(runtime, old.name)
    profile = _resident_profile()
    migrated = await harness.manager.deploy(_awaiting_deployment(runtime), profile)
    on_claim = runtime.model_copy(update={"backend_ref": migrated.backend_ref})
    # The platform moves on to a newer image.
    newer = _profile_with(
        {"image": {"repository": "ghcr.io/niuulabs/openshell", "tag": "dev-newer"}}
    )

    upgrading = await harness.manager.reconcile(on_claim, newer)

    assert upgrading.observed_state is ResidentObservedState.PENDING
    assert upgrading.conditions[0].reason == "Upgrading"
    assert migrated.backend_ref["name"] not in harness.client.sandboxes
    # Its state is on the claim, so the recreated sandbox finds it there.
    redeployed = await harness.manager.deploy(_awaiting_deployment(runtime), newer)
    assert redeployed.backend_ref["image"] == "ghcr.io/niuulabs/openshell:dev-newer"
    assert redeployed.backend_ref["name"] == f"r-{runtime.id.hex[:17]}"
    assert harness.client.claim_files[_claim_name(runtime)][".ravn-home/memory.db"] == b"episodes"
    assert _claim_name(runtime) in harness.core.pvcs


@pytest.mark.asyncio
async def test_without_a_sandbox_namespace_residents_get_no_claim(monkeypatch):
    harness = _Harness(monkeypatch)
    manager = harness.manager_for(resident_workspace_namespace="")
    runtime = _resident_runtime()

    observation = await manager.deploy(runtime, _resident_profile())

    assert harness.core.pvcs == {}
    assert "volundr.niuu.io/workspace-claim" not in harness.client.created["annotations"]
    assert "workspace_claim" not in observation.backend_ref


def test_profile_cannot_point_the_managed_claim_elsewhere():
    runtime = _resident_runtime()
    profile = _profile_with({"persistence": {"mountPath": "/sandbox/elsewhere"}})

    with pytest.raises(ValueError, match="existingClaim"):
        workspace_module.resident_workspace_claim(
            runtime,
            profile,
            size="2Gi",
            storage_class="",
            access_mode="ReadWriteOnce",
            mount_path=WORKSPACE,
        )


def test_manifest_resolves_hard_links_and_ignores_the_root():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        root = tarfile.TarInfo(".")
        root.type = tarfile.DIRTYPE
        tar.addfile(root)
        info = tarfile.TarInfo("./a.txt")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"hi"))
        link = tarfile.TarInfo("./b.txt")
        link.type = tarfile.LNKTYPE
        link.linkname = "./a.txt"
        tar.addfile(link)
    buffer.seek(0)

    manifest = workspace_module.read_workspace_manifest(buffer)

    assert set(manifest.entries) == {"a.txt", "b.txt"}
    assert manifest.entries["a.txt"] == manifest.entries["b.txt"]
    assert manifest.files == 2


def test_manifest_rejects_a_stream_that_is_not_a_tar():
    with pytest.raises(workspace_module.WorkspaceVerificationError):
        workspace_module.read_workspace_manifest(io.BytesIO(b"profile banner\n" * 100))


def test_gateway_client_streams_archives_in_bounded_chunks(monkeypatch):
    adapter = _import_adapter(monkeypatch)
    proto = adapter.openshell_pb2
    proto.ExecSandboxInput = proto.ExecSandboxRequest
    sent: list = []

    def event(**payload):
        return proto.ExecSandboxRequest(**{"stdout": None, "stderr": None, "exit": None, **payload})

    class _Stub:
        def ExecSandboxInteractive(self, frames, **_kwargs):  # noqa: N802
            sent.extend(frames)
            return [event(exit=types.SimpleNamespace(exit_code=0))]

        def ExecSandbox(self, request, **_kwargs):  # noqa: N802
            sent.append(request)
            return [
                event(stdout=types.SimpleNamespace(data=b"x" * 10)),
                event(stdout=types.SimpleNamespace(data=b"y" * 10)),
                event(exit=types.SimpleNamespace(exit_code=0)),
            ]

    client = object.__new__(adapter.OpenShellGatewayClient)
    client._stub = _Stub()
    client._timeout = 30.0
    client._token_provider = types.SimpleNamespace(token=lambda: "token")
    source = io.BytesIO(b"z" * (adapter.EXEC_STDIN_CHUNK_BYTES * 2 + 5))

    restored = client.exec_from_file(
        sandbox_id="sandbox-1", command=["tar", "-xf", "-"], source=source, timeout_seconds=60
    )

    assert restored.exit_code == 0
    assert sent[0].start.no_login_shell is True
    assert [len(frame.stdin) for frame in sent[1:]] == [
        adapter.EXEC_STDIN_CHUNK_BYTES,
        adapter.EXEC_STDIN_CHUNK_BYTES,
        5,
    ]

    destination = io.BytesIO()
    truncated = client.exec_to_file(
        sandbox_id="sandbox-1",
        script="tar -cf - .",
        destination=destination,
        max_bytes=15,
        timeout_seconds=60,
    )
    assert truncated.truncated is True
    assert destination.getvalue() == b"x" * 10


@pytest.mark.parametrize(
    ("deployment", "message"),
    [
        ({"values": {"persistence": "yes"}}, "persistence must be an object"),
        ({"values": [], "volumes": {}}, "deployment.values must be an object"),
        ({"values": {}, "volumes": []}, "deployment.volumes must be an object"),
        ({"values": {}, "volumes": {"home": {}}}, "only a workspace volume"),
        ({"values": {}, "volumes": {"workspace": []}}, "workspace must be an object"),
        ({"values": {}, "volumes": {"workspace": {"iops": 3}}}, "unknown settings"),
        ({"values": {}, "volumes": {"workspace": {"size": ""}}}, "size must not be empty"),
    ],
)
def test_profile_workspace_settings_are_validated(deployment, message):
    profile = _resident_profile().model_copy(update={"deployment": deployment})

    with pytest.raises(ValueError, match=message):
        workspace_module.resident_workspace_claim(
            _resident_runtime(),
            profile,
            size="2Gi",
            storage_class="",
            access_mode="ReadWriteOnce",
            mount_path=WORKSPACE,
        )


@pytest.mark.parametrize("persistence", [{"enabled": False}, {"emptyDir": True}])
def test_profile_can_keep_the_workspace_in_the_sandbox(persistence):
    claim = workspace_module.resident_workspace_claim(
        _resident_runtime(),
        _profile_with({"persistence": persistence}),
        size="2Gi",
        storage_class="",
        access_mode="ReadWriteOnce",
        mount_path=WORKSPACE,
    )

    assert claim is None


def _claims(events=None):
    core = _FakeCoreApi(events if events is not None else [])

    async def api():
        return core

    return core, workspace_module.ResidentWorkspaceClaims(api, NAMESPACE)


def _claim(size: str = "2Gi"):
    return workspace_module.ResidentWorkspaceClaim(
        name=_claim_name(_RUNTIME),
        size=size,
        storage_class="",
        access_mode="ReadWriteOnce",
        mount_path=WORKSPACE,
    )


_RUNTIME = _resident_runtime()


@pytest.mark.asyncio
async def test_claims_need_a_namespace():
    with pytest.raises(ValueError, match="sandbox namespace"):
        workspace_module.ResidentWorkspaceClaims(lambda: None, "")


@pytest.mark.asyncio
async def test_a_smaller_existing_claim_is_expanded_never_shrunk(monkeypatch):
    monkeypatch.setattr(workspace_module, "build_pvc_manifest", _fake_manifest)
    core, claims = _claims()
    await claims.ensure(_RUNTIME, _claim("1Gi"))

    _, created = await claims.ensure(_RUNTIME, _claim("4Gi"))
    await claims.ensure(_RUNTIME, _claim("2Gi"))

    assert created is False
    assert core.pvcs[_claim_name(_RUNTIME)].spec.resources.requests == {"storage": "4Gi"}


@pytest.mark.asyncio
async def test_a_claim_of_the_same_name_that_is_not_the_residents_is_refused(monkeypatch):
    monkeypatch.setattr(workspace_module, "build_pvc_manifest", _fake_manifest)
    core, claims = _claims()
    await core.create_namespaced_persistent_volume_claim(
        namespace=NAMESPACE,
        body=_fake_manifest(
            name=_claim_name(_RUNTIME),
            namespace=NAMESPACE,
            storage="2Gi",
            storage_class=None,
            access_mode="ReadWriteOnce",
            labels={},
        ),
    )

    with pytest.raises(ValueError, match="is not resident"):
        await claims.ensure(_RUNTIME, _claim())


@pytest.mark.asyncio
async def test_lease_rereads_the_claim_after_a_concurrent_change(monkeypatch):
    monkeypatch.setattr(workspace_module, "build_pvc_manifest", _fake_manifest)
    core, claims = _claims()
    pvc, _ = await claims.ensure(_RUNTIME, _claim())
    lease = workspace_module.WorkspaceMigrationLease(claims, pvc, "volundr-a", 60)
    await lease.acquire("r-old")
    # The PV controller annotates the claim after the lease last read it.
    await core.patch_namespaced_persistent_volume_claim(
        name=pvc.metadata.name,
        namespace=NAMESPACE,
        body={"metadata": {"annotations": {"pv.kubernetes.io/bind-completed": "yes"}}},
    )

    await lease.set_phase(workspace_module.PHASE_VERIFIED)

    annotations = core.pvcs[pvc.metadata.name].metadata.annotations
    assert annotations[workspace_module.ANNOTATION_MIGRATION_PHASE] == "verified"
    assert annotations["pv.kubernetes.io/bind-completed"] == "yes"


@pytest.mark.asyncio
async def test_lease_taken_over_elsewhere_stops_the_migration(monkeypatch):
    monkeypatch.setattr(workspace_module, "build_pvc_manifest", _fake_manifest)
    core, claims = _claims()
    pvc, _ = await claims.ensure(_RUNTIME, _claim())
    lease = workspace_module.WorkspaceMigrationLease(claims, pvc, "volundr-a", 60)
    await lease.acquire("r-old")
    core.pvcs[pvc.metadata.name].metadata.annotations[
        workspace_module.ANNOTATION_MIGRATION_HOLDER
    ] = "volundr-b"
    core._bump(core.pvcs[pvc.metadata.name])

    with pytest.raises(workspace_module.WorkspaceMigrationLeaseLostError):
        await lease.renew()
    with pytest.raises(workspace_module.WorkspaceMigrationLeaseLostError):
        await lease.set_phase(workspace_module.PHASE_COMPLETE)
    assert lease.lost


@pytest.mark.asyncio
async def test_lease_on_a_deleted_claim_is_lost(monkeypatch):
    monkeypatch.setattr(workspace_module, "build_pvc_manifest", _fake_manifest)
    core, claims = _claims()
    pvc, _ = await claims.ensure(_RUNTIME, _claim())
    lease = workspace_module.WorkspaceMigrationLease(claims, pvc, "volundr-a", 60)
    await lease.acquire("r-old")
    await core.patch_namespaced_persistent_volume_claim(
        name=pvc.metadata.name, namespace=NAMESPACE, body={"metadata": {}}
    )
    del core.pvcs[pvc.metadata.name]

    with pytest.raises(workspace_module.WorkspaceMigrationLeaseLostError):
        await lease.renew()


@pytest.mark.asyncio
async def test_a_complete_claim_is_never_leased_for_a_copy(monkeypatch):
    monkeypatch.setattr(workspace_module, "build_pvc_manifest", _fake_manifest)
    _, claims = _claims()
    pvc, _ = await claims.ensure(
        _RUNTIME,
        _claim(),
        annotations={workspace_module.ANNOTATION_MIGRATION_PHASE: "complete"},
    )
    lease = workspace_module.WorkspaceMigrationLease(claims, pvc, "volundr-a", 60)

    with pytest.raises(workspace_module.WorkspaceClaimInUseError):
        await lease.acquire("r-old")


def test_manifest_records_symlinks_and_refuses_overlapping_sources():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        link = tarfile.TarInfo("./current")
        link.type = tarfile.SYMTYPE
        link.linkname = "releases/1"
        tar.addfile(link)
        fifo = tarfile.TarInfo("./pipe")
        fifo.type = tarfile.FIFOTYPE
        tar.addfile(fifo)
    buffer.seek(0)

    manifest = workspace_module.read_workspace_manifest(buffer)

    assert manifest.entries["current"] == ("symlink", 0, "releases/1")
    assert manifest.entries["pipe"] == ("special", 0, "")
    with pytest.raises(workspace_module.WorkspaceMigrationError, match="overlap"):
        manifest.merged(manifest)


def test_manifest_rejects_a_hard_link_to_nothing():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        link = tarfile.TarInfo("./b.txt")
        link.type = tarfile.LNKTYPE
        link.linkname = "./missing.txt"
        tar.addfile(link)
    buffer.seek(0)

    with pytest.raises(workspace_module.WorkspaceVerificationError, match="hard link"):
        workspace_module.read_workspace_manifest(buffer)


@pytest.mark.asyncio
async def test_restart_on_the_claim_keeps_ravn_home_on_it(monkeypatch):
    harness = _Harness(monkeypatch)
    runtime = _resident_runtime()
    sandbox = harness.old_sandbox(runtime, image=TARGET_IMAGE)
    sandbox.annotations["volundr.niuu.io/workspace-claim"] = _claim_name(runtime)
    runtime = _running(runtime, sandbox.name)

    observation = await harness.manager.restart(runtime, _resident_profile())

    assert sandbox.links == {"/sandbox/.ravn": f"{WORKSPACE}/.ravn-home"}
    assert harness.events.index(f"stopped:{sandbox.name}") < harness.events.index(
        f"linked:{sandbox.name}:/sandbox/.ravn"
    )
    assert observation.backend_ref["name"] == sandbox.name
    assert set(harness.client.sandboxes) == {sandbox.name}
