"""Registry, service and REST routing of the commit / compare / checks reads."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from niuu.adapters.inbound.auth import extract_principal
from niuu.adapters.inbound.rest_repos import create_repos_router
from niuu.adapters.outbound.git_registry import GitProviderRegistry
from niuu.domain.delivery import CheckConclusion, CheckRecord
from niuu.domain.models import (
    ChangedFile,
    CommitDetail,
    CommitSummary,
    Principal,
    RefChecks,
    RefComparison,
)
from niuu.domain.services.repo import RepoService
from niuu.ports.git import GitAuthError, GitProviderResponseError, GitRepoNotFoundError
from tests.conftest import MockGitProvider

REPO = "https://github.com/niuulabs/niuu"
SHA = "a" * 40
WHEN = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)


def _files() -> tuple[ChangedFile, ...]:
    return (
        ChangedFile("src/a.py", "modified", 3, 1, patch="@@ a @@"),
        ChangedFile("src/pkg/b.py", "added", 5, 0, patch="@@ b @@"),
        ChangedFile(
            "docs/new.md",
            "renamed",
            0,
            0,
            previous_path="docs/old.md",
            patch_omitted_reason="no line changes (rename, copy or mode change)",
        ),
        ChangedFile("logo.png", "added", 0, 0, patch_omitted_reason="binary"),
    )


def _commit() -> CommitDetail:
    return CommitDetail(
        repo_url=REPO,
        sha=SHA,
        url=f"{REPO}/commit/{SHA}",
        parents=("b" * 40,),
        author_name="Regin",
        author_email="regin@example.test",
        authored_at=WHEN,
        message="feat: x",
        additions=8,
        deletions=1,
        files=_files(),
        files_total=4,
    )


def _comparison() -> RefComparison:
    return RefComparison(
        repo_url=REPO,
        base="main",
        head="regin",
        status="ahead",
        ahead_by=1,
        behind_by=0,
        merge_base_sha="b" * 40,
        url=f"{REPO}/compare/main...regin",
        commits=(CommitSummary(SHA, "feat: x", "Regin", WHEN, "u"),),
        files=_files(),
        files_total=4,
    )


def _checks() -> RefChecks:
    return RefChecks(
        repo_url=REPO,
        ref="regin",
        sha=SHA,
        checks=(
            CheckRecord(
                name="backend", conclusion=CheckConclusion.FAILING, details_url="https://ci"
            ),
            CheckRecord(name="lint", conclusion=CheckConclusion.PASSING),
        ),
    )


def _provider() -> MockGitProvider:
    provider = MockGitProvider()
    provider.commit_result = _commit()
    provider.comparison_result = _comparison()
    provider.ref_checks_result = _checks()
    return provider


def _registry(provider: MockGitProvider | None = None) -> GitProviderRegistry:
    registry = GitProviderRegistry()
    registry.register(provider or _provider())
    return registry


# --- Registry: routed to the provider that serves the URL, like list_branches ---


async def test_registry_routes_reads_to_the_serving_provider() -> None:
    provider = _provider()
    registry = _registry(provider)

    assert await registry.get_commit(REPO, "regin") == _commit()
    assert await registry.compare_refs(REPO, "main", "regin") == _comparison()
    assert await registry.get_ref_checks(REPO, "regin") == _checks()
    assert provider.read_calls == [
        ("get_commit", REPO, "regin"),
        ("compare_refs", REPO, "main", "regin"),
        ("get_ref_checks", REPO, "regin"),
    ]


@pytest.mark.parametrize("call", ["commit", "compare", "checks"])
async def test_registry_with_no_serving_provider_is_a_value_error(call: str) -> None:
    registry = GitProviderRegistry()

    with pytest.raises(ValueError, match="No git provider found"):
        if call == "commit":
            await registry.get_commit(REPO, "x")
        elif call == "compare":
            await registry.compare_refs(REPO, "a", "b")
        else:
            await registry.get_ref_checks(REPO, "x")


# --- Service: the caller's own account first, then shaping for an agent ---------


async def test_service_prefers_the_callers_own_provider() -> None:
    shared = _provider()
    personal = _provider()
    integrations = AsyncMock()
    integrations.find_git_provider_for = AsyncMock(return_value=personal)
    service = RepoService(_registry(shared), user_integration=integrations)

    await service.get_commit(REPO, "regin", user_id="u1")
    await service.compare_refs(REPO, "main", "regin", user_id="u1")
    await service.get_ref_checks(REPO, "regin", user_id="u1")

    assert len(personal.read_calls) == 3
    assert shared.read_calls == []


async def test_service_falls_to_the_shared_provider_only_when_the_caller_has_none() -> None:
    shared = _provider()
    integrations = AsyncMock()
    integrations.find_git_provider_for = AsyncMock(return_value=None)
    service = RepoService(_registry(shared), user_integration=integrations)

    await service.get_ref_checks(REPO, "regin", user_id="u1")
    await service.get_ref_checks(REPO, "regin")  # anonymous caller

    assert len(shared.read_calls) == 2


async def test_service_default_is_the_file_list_without_patches() -> None:
    service = RepoService(_registry())

    commit = await service.get_commit(REPO, "regin")

    assert commit.patch_included is False
    assert commit.files_total == 4
    assert [f.path for f in commit.files] == [f.path for f in _files()]
    assert all(f.patch is None for f in commit.files)
    # With no patch asked for there is nothing to explain about a missing one.
    assert all(f.patch_omitted_reason is None for f in commit.files)


async def test_service_patches_on_request_keep_the_providers_omission_reason() -> None:
    service = RepoService(_registry())

    commit = await service.get_commit(REPO, "regin", include_patch=True)

    by_path = {f.path: f for f in commit.files}
    assert commit.patch_included is True
    assert by_path["src/a.py"].patch == "@@ a @@"
    assert by_path["logo.png"].patch is None
    assert by_path["logo.png"].patch_omitted_reason == "binary"


async def test_service_path_filter_matches_files_directories_and_old_names() -> None:
    service = RepoService(_registry())

    commit = await service.get_commit(
        REPO,
        "regin",
        paths=["src/pkg/", "docs/old.md", "/src/a.py", "missing.py", "src/p"],
        include_patch=True,
    )

    assert [f.path for f in commit.files] == ["src/a.py", "src/pkg/b.py", "docs/new.md"]
    assert commit.files_total == 4
    # A mistyped path is reported, never read as "the commit did not touch it";
    # a bare name prefix is not a directory match.
    assert commit.unmatched_paths == ("missing.py", "src/p")


async def test_service_blank_path_matches_nothing() -> None:
    service = RepoService(_registry())

    commit = await service.get_commit(REPO, "regin", paths=["  "])

    assert commit.files == ()
    assert commit.unmatched_paths == ("  ",)


async def test_service_shapes_comparisons_the_same_way() -> None:
    service = RepoService(_registry())

    comparison = await service.compare_refs(
        REPO, "main", "regin", paths=["src/a.py"], include_patch=True
    )

    assert [f.path for f in comparison.files] == ["src/a.py"]
    assert comparison.files[0].patch == "@@ a @@"
    assert comparison.files_total == 4
    assert comparison.commits[0].subject == "feat: x"
    assert comparison.patch_included is True


# --- REST ------------------------------------------------------------------------


def _client(service: RepoService | None) -> TestClient:
    app = FastAPI()
    app.include_router(create_repos_router(service))
    app.dependency_overrides[extract_principal] = lambda: Principal(
        user_id="dev-user", email="dev@example.test", tenant_id="default", roles=[]
    )
    return TestClient(app)


def test_commit_route_returns_a_shaped_commit() -> None:
    client = _client(RepoService(_registry()))

    response = client.get(
        "/api/v1/niuu/repos/commit",
        params=[("repo_url", REPO), ("ref", "regin"), ("path", "src/a.py"), ("path", "nope")],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sha"] == SHA
    assert body["authored_at"] == WHEN.isoformat()
    assert body["files_total"] == 4
    assert [f["path"] for f in body["files"]] == ["src/a.py"]
    assert body["files"][0]["patch"] is None
    assert body["patch_included"] is False
    assert body["unmatched_paths"] == ["nope"]


def test_commit_route_includes_patches_on_request() -> None:
    client = _client(RepoService(_registry()))

    response = client.get(
        "/api/v1/niuu/repos/commit",
        params={"repo_url": REPO, "ref": "regin", "include_patch": "true"},
    )

    assert response.json()["files"][0]["patch"] == "@@ a @@"
    assert response.json()["patch_included"] is True


def test_commit_route_serialises_a_commit_without_a_date() -> None:
    provider = _provider()
    provider.commit_result = CommitDetail(**{**_commit().__dict__, "authored_at": None})
    client = _client(RepoService(_registry(provider)))

    response = client.get("/api/v1/niuu/repos/commit", params={"repo_url": REPO, "ref": "x"})

    assert response.json()["authored_at"] is None


def test_compare_route_returns_counts_commits_and_files() -> None:
    client = _client(RepoService(_registry()))

    response = client.get(
        "/api/v1/niuu/repos/compare",
        params={"repo_url": REPO, "base": "main", "head": "regin", "include_patch": "true"},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["ahead_by"], body["behind_by"]) == ("ahead", 1, 0)
    assert body["commits"][0] == {
        "sha": SHA,
        "subject": "feat: x",
        "author_name": "Regin",
        "authored_at": WHEN.isoformat(),
        "url": "u",
    }
    assert body["files_total"] == 4
    assert body["files"][0]["patch"] == "@@ a @@"


def test_checks_route_reports_status_counts_and_checks() -> None:
    client = _client(RepoService(_registry()))

    response = client.get("/api/v1/niuu/repos/checks", params={"repo_url": REPO, "ref": "regin"})

    assert response.status_code == 200
    body = response.json()
    assert body["sha"] == SHA
    assert body["status"] == "failing"
    assert body["counts"] == {"failing": 1, "passing": 1}
    assert body["checks"][0] == {
        "name": "backend",
        "conclusion": "failing",
        "details_url": "https://ci",
    }


READS = [
    ("/api/v1/niuu/repos/commit", {"repo_url": REPO, "ref": "r"}),
    ("/api/v1/niuu/repos/compare", {"repo_url": REPO, "base": "a", "head": "b"}),
    ("/api/v1/niuu/repos/checks", {"repo_url": REPO, "ref": "r"}),
]


@pytest.mark.parametrize(("path", "params"), READS)
@pytest.mark.parametrize(
    ("failure", "status", "needle"),
    [
        (ValueError("No git provider found for: x"), 404, "No connected Git host serves"),
        (GitRepoNotFoundError("Not found: commit 'r'"), 404, "Not found: commit 'r'"),
        (GitAuthError("token refused"), 403, "token refused"),
        (httpx.ConnectError("unreachable"), 502, "unreachable"),
        (GitProviderResponseError("incomplete comparison"), 502, "incomplete comparison"),
    ],
)
def test_read_failures_map_to_typed_http_errors(
    path: str, params: dict, failure: Exception, status: int, needle: str
) -> None:
    provider = _provider()
    for method in ("get_commit", "compare_refs", "get_ref_checks"):
        setattr(provider, method, AsyncMock(side_effect=failure))
    client = _client(RepoService(_registry(provider)))

    response = client.get(path, params=params)

    assert response.status_code == status
    assert needle in response.json()["detail"]


@pytest.mark.parametrize(("path", "params"), READS)
def test_reads_without_a_repo_service_are_unavailable(path: str, params: dict) -> None:
    response = _client(None).get(path, params=params)

    assert response.status_code == 503


@pytest.mark.parametrize(
    ("conclusions", "expected"),
    [
        ((), "unknown"),
        ((CheckConclusion.PASSING, CheckConclusion.SKIPPED), "passing"),
        ((CheckConclusion.PASSING, CheckConclusion.PENDING), "pending"),
        ((CheckConclusion.PASSING, CheckConclusion.UNKNOWN), "unknown"),
        ((CheckConclusion.PENDING, CheckConclusion.CANCELED), "failing"),
    ],
)
def test_ref_checks_aggregate_status(conclusions: tuple, expected: str) -> None:
    checks = tuple(CheckRecord(name=f"c{i}", conclusion=c) for i, c in enumerate(conclusions))

    assert RefChecks(REPO, "r", SHA, checks).status.value == expected
