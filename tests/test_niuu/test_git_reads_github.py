"""GitHub reads: one commit, a comparison, and CI for a ref with no pull request."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from niuu.adapters.outbound.github import GitHubProvider
from niuu.domain.delivery import CheckConclusion
from niuu.domain.models import CIStatus
from niuu.ports.git import GitAuthError, GitProviderResponseError, GitRepoNotFoundError

REPO = "https://github.com/niuulabs/niuu"
API = "https://api.github.com/repos/niuulabs/niuu"
SHA = "a" * 40
PARENT = "b" * 40


@pytest.fixture
def provider() -> GitHubProvider:
    return GitHubProvider(name="GitHub", base_url="https://api.github.com", token="t")


def _commit_body(**overrides) -> dict:
    body = {
        "sha": SHA,
        "html_url": f"{REPO}/commit/{SHA}",
        "parents": [{"sha": PARENT}],
        "commit": {
            "message": "feat: add the thing\n\nbody text",
            "author": {
                "name": "Regin Coder",
                "email": "regin@example.test",
                "date": "2026-10-26T10:00:00Z",
            },
        },
        "stats": {"additions": 5, "deletions": 2, "total": 7},
        "files": [
            {
                "filename": "src/a.py",
                "status": "modified",
                "additions": 3,
                "deletions": 2,
                "patch": "@@ -1 +1 @@\n-old\n+new",
            },
            {"filename": "logo.png", "status": "added", "additions": 0, "deletions": 0},
            {
                "filename": "docs/b.md",
                "status": "renamed",
                "previous_filename": "docs/a.md",
                "additions": 0,
                "deletions": 0,
            },
            {"filename": "big.json", "status": "modified", "additions": 900, "deletions": 4},
        ],
    }
    body.update(overrides)
    return body


@respx.mock
async def test_get_commit_maps_identity_message_and_files(provider: GitHubProvider) -> None:
    route = respx.get(f"{API}/commits/regin").mock(
        return_value=httpx.Response(200, json=_commit_body())
    )

    commit = await provider.get_commit(REPO, "regin")

    assert route.called
    assert commit.sha == SHA
    assert commit.parents == (PARENT,)
    assert commit.author_name == "Regin Coder"
    assert commit.author_email == "regin@example.test"
    assert commit.authored_at == datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
    assert commit.message.startswith("feat: add the thing")
    assert (commit.additions, commit.deletions) == (5, 2)
    assert commit.files_total == 4
    by_path = {f.path: f for f in commit.files}
    assert by_path["src/a.py"].patch == "@@ -1 +1 @@\n-old\n+new"
    assert by_path["src/a.py"].patch_omitted_reason is None
    assert by_path["docs/b.md"].previous_path == "docs/a.md"
    assert by_path["docs/b.md"].patch_omitted_reason == (
        "no line changes (rename, copy or mode change)"
    )
    assert by_path["big.json"].patch is None
    assert "too large" in by_path["big.json"].patch_omitted_reason
    assert by_path["big.json"].additions == 900


@respx.mock
async def test_get_commit_follows_file_pagination_without_duplicating(
    provider: GitHubProvider,
) -> None:
    next_url = f"{API}/commits/regin?per_page=100&page=2"
    respx.get(f"{API}/commits/regin", params={"page": 2}).mock(
        return_value=httpx.Response(
            200,
            json=_commit_body(
                files=[
                    {"filename": "src/a.py", "status": "modified", "additions": 3, "deletions": 2},
                    {"filename": "src/z.py", "status": "added", "additions": 1, "deletions": 0},
                ]
            ),
        )
    )
    respx.get(f"{API}/commits/regin").mock(
        return_value=httpx.Response(
            200,
            json=_commit_body(),
            headers={"link": f'<{next_url}>; rel="next"'},
        )
    )

    commit = await provider.get_commit(REPO, "regin")

    assert [f.path for f in commit.files] == [
        "src/a.py",
        "logo.png",
        "docs/b.md",
        "big.json",
        "src/z.py",
    ]
    assert commit.files_total == 5


@respx.mock
async def test_get_commit_quotes_slashes_in_branch_refs(provider: GitHubProvider) -> None:
    route = respx.get(f"{API}/commits/feat/x").mock(
        return_value=httpx.Response(200, json=_commit_body())
    )

    await provider.get_commit(REPO, "feat/x")

    assert route.called


@respx.mock
async def test_get_commit_pagination_that_never_advances_is_fatal(
    provider: GitHubProvider,
) -> None:
    loop = f"{API}/commits/regin?per_page=100&page=2"
    respx.get(f"{API}/commits/regin").mock(
        return_value=httpx.Response(
            200, json=_commit_body(), headers={"link": f'<{loop}>; rel="next"'}
        )
    )

    with pytest.raises(GitProviderResponseError, match="did not advance"):
        await provider.get_commit(REPO, "regin")


@respx.mock
async def test_get_commit_without_a_sha_is_fatal(provider: GitHubProvider) -> None:
    respx.get(f"{API}/commits/regin").mock(
        return_value=httpx.Response(200, json=_commit_body(sha=""))
    )

    with pytest.raises(GitProviderResponseError, match="omitted its SHA"):
        await provider.get_commit(REPO, "regin")


@respx.mock
async def test_get_commit_with_a_garbled_date_is_fatal(provider: GitHubProvider) -> None:
    body = _commit_body()
    body["commit"]["author"]["date"] = "yesterday"
    respx.get(f"{API}/commits/regin").mock(return_value=httpx.Response(200, json=body))

    with pytest.raises(GitProviderResponseError, match="unparseable timestamp"):
        await provider.get_commit(REPO, "regin")


@respx.mock
async def test_get_commit_tolerates_a_commit_without_author_or_date(
    provider: GitHubProvider,
) -> None:
    respx.get(f"{API}/commits/regin").mock(
        return_value=httpx.Response(
            200, json={"sha": SHA, "commit": {}, "parents": [], "files": []}
        )
    )

    commit = await provider.get_commit(REPO, "regin")

    assert commit.authored_at is None
    assert commit.author_name == ""
    assert commit.files == ()


@pytest.mark.parametrize("status", [404, 422])
@respx.mock
async def test_unknown_ref_or_repo_is_not_found(provider: GitHubProvider, status: int) -> None:
    respx.get(f"{API}/commits/nope").mock(return_value=httpx.Response(status, json={}))

    with pytest.raises(GitRepoNotFoundError, match="nope"):
        await provider.get_commit(REPO, "nope")


@respx.mock
async def test_refused_credentials_are_an_auth_error_naming_the_remedy(
    provider: GitHubProvider,
) -> None:
    respx.get(f"{API}/commits/regin").mock(return_value=httpx.Response(403, json={}))

    with pytest.raises(GitAuthError, match="'repo' scope"):
        await provider.get_commit(REPO, "regin")


@pytest.mark.parametrize(
    ("status", "headers"),
    [(403, {"x-ratelimit-remaining": "0"}), (429, {})],
)
@respx.mock
async def test_rate_limit_is_a_provider_error_not_an_auth_error(
    provider: GitHubProvider, status: int, headers: dict
) -> None:
    respx.get(f"{API}/commits/regin").mock(
        return_value=httpx.Response(status, json={}, headers=headers)
    )

    with pytest.raises(httpx.HTTPStatusError, match="rate limit exhausted"):
        await provider.get_commit(REPO, "regin")


@respx.mock
async def test_provider_outage_surfaces_as_http_error(provider: GitHubProvider) -> None:
    respx.get(f"{API}/commits/regin").mock(return_value=httpx.Response(500))

    with pytest.raises(httpx.HTTPStatusError):
        await provider.get_commit(REPO, "regin")


@respx.mock
async def test_unexpected_success_status_is_fatal(provider: GitHubProvider) -> None:
    respx.get(f"{API}/commits/regin").mock(return_value=httpx.Response(204))

    with pytest.raises(GitProviderResponseError, match="Unexpected HTTP 204"):
        await provider.get_commit(REPO, "regin")


@respx.mock
async def test_later_page_failure_is_typed_like_the_first(provider: GitHubProvider) -> None:
    next_url = f"{API}/commits/regin?per_page=100&page=2"
    respx.get(f"{API}/commits/regin", params={"page": 2}).mock(return_value=httpx.Response(404))
    respx.get(f"{API}/commits/regin").mock(
        return_value=httpx.Response(
            200, json=_commit_body(), headers={"link": f'<{next_url}>; rel="next"'}
        )
    )

    with pytest.raises(GitRepoNotFoundError):
        await provider.get_commit(REPO, "regin")


@pytest.mark.parametrize("call", ["commit", "compare", "checks"])
async def test_unparseable_repo_url_is_not_found(provider: GitHubProvider, call: str) -> None:
    with pytest.raises(GitRepoNotFoundError, match="Cannot parse repository URL"):
        if call == "commit":
            await provider.get_commit("not a url", "x")
        elif call == "compare":
            await provider.compare_refs("not a url", "a", "b")
        else:
            await provider.get_ref_checks("not a url", "x")


def _compare_body(**overrides) -> dict:
    body = {
        "status": "diverged",
        "ahead_by": 2,
        "behind_by": 1,
        "total_commits": 2,
        "html_url": f"{REPO}/compare/main...regin",
        "merge_base_commit": {"sha": PARENT},
        "commits": [
            {
                "sha": "1" * 40,
                "html_url": f"{REPO}/commit/{'1' * 40}",
                "commit": {
                    "message": "feat: one\n\nlong body",
                    "author": {"name": "A", "date": "2026-10-25T09:00:00Z"},
                },
            },
            {
                "sha": "2" * 40,
                "html_url": f"{REPO}/commit/{'2' * 40}",
                "commit": {"message": "", "author": {"name": "B"}},
            },
        ],
        "files": [
            {
                "filename": "src/a.py",
                "status": "modified",
                "additions": 1,
                "deletions": 1,
                "patch": "@@ x @@",
            }
        ],
    }
    body.update(overrides)
    return body


@respx.mock
async def test_compare_maps_counts_commits_and_files(provider: GitHubProvider) -> None:
    respx.get(f"{API}/compare/main...regin").mock(
        return_value=httpx.Response(200, json=_compare_body())
    )

    comparison = await provider.compare_refs(REPO, "main", "regin")

    assert (comparison.status, comparison.ahead_by, comparison.behind_by) == ("diverged", 2, 1)
    assert comparison.merge_base_sha == PARENT
    assert comparison.url.endswith("/compare/main...regin")
    assert [c.subject for c in comparison.commits] == ["feat: one", ""]
    assert comparison.commits[0].authored_at == datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
    assert comparison.commits[1].authored_at is None
    assert [f.path for f in comparison.files] == ["src/a.py"]
    assert comparison.files_total == 1


@respx.mock
async def test_compare_follows_pages_and_ignores_repeated_entries(
    provider: GitHubProvider,
) -> None:
    body = _compare_body()
    page_two = _compare_body(
        commits=[
            body["commits"][1],
            {
                "sha": "3" * 40,
                "html_url": "u",
                "commit": {"message": "three", "author": {"name": "C"}},
            },
        ],
        total_commits=3,
        files=[
            body["files"][0],
            {"filename": "src/b.py", "status": "added", "additions": 1, "deletions": 0},
        ],
    )
    body["total_commits"] = 3
    next_url = f"{API}/compare/main...regin?per_page=100&page=2"
    respx.get(f"{API}/compare/main...regin", params={"page": 2}).mock(
        return_value=httpx.Response(200, json=page_two)
    )
    respx.get(f"{API}/compare/main...regin").mock(
        return_value=httpx.Response(200, json=body, headers={"link": f'<{next_url}>; rel="next"'})
    )

    comparison = await provider.compare_refs(REPO, "main", "regin")

    assert [c.sha[0] for c in comparison.commits] == ["1", "2", "3"]
    assert [f.path for f in comparison.files] == ["src/a.py", "src/b.py"]


@respx.mock
async def test_compare_that_returns_fewer_commits_than_reported_is_fatal(
    provider: GitHubProvider,
) -> None:
    respx.get(f"{API}/compare/main...regin").mock(
        return_value=httpx.Response(200, json=_compare_body(total_commits=300))
    )

    with pytest.raises(GitProviderResponseError, match="incomplete"):
        await provider.compare_refs(REPO, "main", "regin")


@respx.mock
async def test_compare_with_an_unknown_ref_is_not_found(provider: GitHubProvider) -> None:
    respx.get(f"{API}/compare/main...ghost").mock(return_value=httpx.Response(404))

    with pytest.raises(GitRepoNotFoundError, match="ghost"):
        await provider.compare_refs(REPO, "main", "ghost")


def _status_body(statuses: list[dict] | None = None, sha: str = SHA) -> dict:
    return {"sha": sha, "state": "failure", "statuses": statuses or []}


@respx.mock
async def test_ref_checks_reports_runs_and_statuses_worst_first(
    provider: GitHubProvider,
) -> None:
    respx.get(f"{API}/commits/regin/check-runs").mock(
        return_value=httpx.Response(
            200,
            json={
                "check_runs": [
                    {"name": "lint", "status": "completed", "conclusion": "success"},
                    {
                        "name": "backend",
                        "status": "completed",
                        "conclusion": "failure",
                        "details_url": "https://ci.test/backend",
                    },
                    {"name": "web", "status": "in_progress", "conclusion": None},
                ]
            },
        )
    )
    respx.get(f"{API}/commits/regin/status").mock(
        return_value=httpx.Response(
            200,
            json=_status_body(
                [{"context": "codecov/patch", "state": "success", "target_url": "https://c.test"}]
            ),
        )
    )

    result = await provider.get_ref_checks(REPO, "regin")

    assert result.sha == SHA
    assert result.ref == "regin"
    assert [c.name for c in result.checks] == ["backend", "web", "codecov/patch", "lint"]
    assert result.checks[0].conclusion is CheckConclusion.FAILING
    assert result.checks[0].details_url == "https://ci.test/backend"
    assert result.status is CIStatus.FAILING
    assert result.counts() == {"failing": 1, "pending": 1, "passing": 2}


@respx.mock
async def test_ref_checks_with_nothing_run_is_unknown_not_passing(
    provider: GitHubProvider,
) -> None:
    respx.get(f"{API}/commits/regin/check-runs").mock(
        return_value=httpx.Response(200, json={"check_runs": []})
    )
    respx.get(f"{API}/commits/regin/status").mock(
        return_value=httpx.Response(200, json=_status_body())
    )

    result = await provider.get_ref_checks(REPO, "regin")

    assert result.checks == ()
    assert result.status is CIStatus.UNKNOWN


@respx.mock
async def test_ref_checks_without_a_sha_is_fatal(provider: GitHubProvider) -> None:
    respx.get(f"{API}/commits/regin/check-runs").mock(
        return_value=httpx.Response(200, json={"check_runs": []})
    )
    respx.get(f"{API}/commits/regin/status").mock(
        return_value=httpx.Response(200, json={"statuses": []})
    )

    with pytest.raises(GitProviderResponseError, match="omitted the commit SHA"):
        await provider.get_ref_checks(REPO, "regin")


@pytest.mark.parametrize("failing", ["check-runs", "status"])
@respx.mock
async def test_ref_checks_unknown_ref_is_not_found(provider: GitHubProvider, failing: str) -> None:
    respx.get(f"{API}/commits/ghost/check-runs").mock(
        return_value=(
            httpx.Response(404)
            if failing == "check-runs"
            else httpx.Response(200, json={"check_runs": []})
        )
    )
    respx.get(f"{API}/commits/ghost/status").mock(return_value=httpx.Response(404))

    with pytest.raises(GitRepoNotFoundError, match="ghost"):
        await provider.get_ref_checks(REPO, "ghost")


@respx.mock
async def test_ref_checks_rate_limit_is_a_provider_error(provider: GitHubProvider) -> None:
    respx.get(f"{API}/commits/regin/check-runs").mock(
        return_value=httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
    )

    with pytest.raises(httpx.HTTPStatusError, match="rate limit exhausted"):
        await provider.get_ref_checks(REPO, "regin")
