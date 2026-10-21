"""Shared repos REST endpoint — /api/v1/niuu/repos.

Serves repository listings, branches and pull requests for all services
(Volundr, Ting, Ravn residents, etc.). The Git host is the source of truth,
so nothing here depends on which Forge instance a caller happens to reach.
The RepoService is injected by the hosting application.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Literal

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field

from niuu.adapters.inbound.auth import extract_principal
from niuu.domain.models import Principal, PullRequest
from niuu.ports.git import GitAuthError, GitRepoNotFoundError

if TYPE_CHECKING:
    from niuu.domain.services.repo import RepoService


class RepoResponse(BaseModel):
    provider: str
    org: str
    name: str
    url: str
    clone_url: str
    default_branch: str
    branches: list[str] = []


class PullRequestResponse(BaseModel):
    """Response model for a pull request."""

    number: int = Field(description="PR number")
    title: str = Field(description="PR title")
    url: str = Field(description="Web URL for the pull request")
    repo_url: str = Field(description="Repository URL")
    provider: str = Field(description="Git provider (github, gitlab)")
    source_branch: str = Field(description="Source branch name")
    target_branch: str = Field(description="Target branch name")
    status: str = Field(description="PR status (open, merged, closed)")
    description: str | None = Field(
        default=None,
        description="PR body/description",
    )
    ci_status: str | None = Field(
        default=None,
        description="CI pipeline status (passing, failing, pending)",
    )
    review_status: str | None = Field(
        default=None,
        description="Review status (approved, changes_requested, pending)",
    )
    created_at: str | None = Field(
        default=None,
        description="ISO 8601 creation timestamp",
    )
    updated_at: str | None = Field(
        default=None,
        description="ISO 8601 last update timestamp",
    )

    @classmethod
    def from_pull_request(cls, pr: PullRequest) -> PullRequestResponse:
        """Create response from domain model."""
        return cls(
            number=pr.number,
            title=pr.title,
            url=pr.url,
            repo_url=pr.repo_url,
            provider=pr.provider.value,
            source_branch=pr.source_branch,
            target_branch=pr.target_branch,
            status=pr.status.value,
            description=pr.description,
            ci_status=pr.ci_status.value if pr.ci_status else None,
            review_status=pr.review_status.value if pr.review_status else None,
            created_at=pr.created_at.isoformat() if pr.created_at else None,
            updated_at=pr.updated_at.isoformat() if pr.updated_at else None,
        )


class PRMergeRequest(BaseModel):
    """Request to merge a PR."""

    merge_method: Literal["merge", "squash", "rebase"] = Field(
        default="squash",
        description="Merge method: merge, squash, or rebase",
    )


class CIStatusResponse(BaseModel):
    """Response model for CI status."""

    status: str = Field(
        description="CI status (passing, failing, pending, unknown)",
    )


class MergeResultResponse(BaseModel):
    """Response model for merge result."""

    merged: bool = Field(description="Whether the PR was successfully merged")


@contextmanager
def _git_host_errors(repo_url: str) -> Iterator[None]:
    """Translate Git-host failures on pull-request routes into typed HTTP errors.

    Every outcome names its cause so a caller (often an agent) can tell a
    wrong address from missing credentials from a host outage, instead of
    reading a bare 404 as "this platform has no such feature".
    """
    try:
        yield
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No connected Git host serves {repo_url!r}: {exc}. Connect the "
                "account that owns this repository, or pass its full https URL."
            ),
        ) from exc
    except GitRepoNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitAuthError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the Git provider for pull requests; try again shortly.",
        ) from exc


def create_repos_router(repo_service: RepoService) -> APIRouter:
    """Create the shared repos router at /api/v1/niuu."""
    router = APIRouter(prefix="/api/v1/niuu", tags=["Shared"])

    def _repo_service() -> RepoService:
        if repo_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Repo service not available",
            )
        return repo_service

    @router.get("/repos", response_model=dict[str, list[RepoResponse]])
    async def list_repos(
        request: Request,
        principal: Principal = Depends(extract_principal),
    ) -> dict[str, list[RepoResponse]]:
        """List repositories from all providers visible to the current user.

        The caller is whoever the platform authenticated, the same way every
        other route sees them; without sign-in that is the development user,
        whose own Git accounts must still be consulted.
        """
        del request
        if repo_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Repo service not available",
            )
        repos_by_provider = await repo_service.list_repos(user_id=principal.user_id)
        return {
            provider_name: [
                RepoResponse(
                    provider=repo.provider,
                    org=repo.org,
                    name=repo.name,
                    url=repo.url,
                    clone_url=repo.clone_url,
                    default_branch=repo.default_branch,
                    branches=list(repo.branches),
                )
                for repo in repos
            ]
            for provider_name, repos in repos_by_provider.items()
        }

    @router.get("/repos/branches", response_model=list[str])
    async def list_branches(
        request: Request,
        repo_url: str,
        principal: Principal = Depends(extract_principal),
    ) -> list[str]:
        """List branches for a repository visible to the current user."""
        del request
        if repo_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Repo service not available",
            )
        try:
            return await repo_service.list_branches(repo_url, user_id=principal.user_id)
        except (ValueError, GitRepoNotFoundError) as exc:
            # The launcher asks while the address is still being typed.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No connected Git host serves {repo_url!r}: {exc}",
            ) from exc
        except GitAuthError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not fetch branches from the Git provider; try again shortly.",
            ) from exc

    @router.get("/repos/prs", response_model=list[PullRequestResponse])
    async def list_pull_requests(
        repo_url: str = Query(..., description="Repository URL"),
        status_filter: Literal["open", "closed", "merged", "all"] = Query(
            default="open",
            alias="status",
            description="Filter by status (open, closed, merged, all)",
        ),
        principal: Principal = Depends(extract_principal),
    ) -> list[PullRequestResponse]:
        """List pull requests for a repository visible to the current user."""
        with _git_host_errors(repo_url):
            prs = await _repo_service().list_pull_requests(
                repo_url, status_filter, user_id=principal.user_id
            )
        return [PullRequestResponse.from_pull_request(pr) for pr in prs]

    @router.get("/repos/prs/{pr_number}", response_model=PullRequestResponse)
    async def get_pull_request(
        pr_number: int = Path(description="Pull request number"),
        repo_url: str = Query(..., description="Repository URL"),
        principal: Principal = Depends(extract_principal),
    ) -> PullRequestResponse:
        """Get a pull request by number."""
        with _git_host_errors(repo_url):
            pr = await _repo_service().get_pull_request(
                repo_url, pr_number, user_id=principal.user_id
            )
        if pr is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PR #{pr_number} not found in {repo_url}",
            )
        return PullRequestResponse.from_pull_request(pr)

    @router.post("/repos/prs/{pr_number}/merge", response_model=MergeResultResponse)
    async def merge_pull_request(
        pr_number: int = Path(description="Pull request number"),
        repo_url: str = Query(..., description="Repository URL"),
        request: PRMergeRequest = Body(default_factory=PRMergeRequest),
        principal: Principal = Depends(extract_principal),
    ) -> MergeResultResponse:
        """Merge a pull request."""
        with _git_host_errors(repo_url):
            merged = await _repo_service().merge_pull_request(
                repo_url, pr_number, request.merge_method, user_id=principal.user_id
            )
        if not merged:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Failed to merge PR #{pr_number} — check CI status and reviews",
            )
        return MergeResultResponse(merged=True)

    @router.get("/repos/prs/{pr_number}/ci", response_model=CIStatusResponse)
    async def get_ci_status(
        pr_number: int = Path(description="Pull request number"),
        repo_url: str = Query(..., description="Repository URL"),
        branch: str = Query(..., description="Branch name"),
        principal: Principal = Depends(extract_principal),
    ) -> CIStatusResponse:
        """Get CI status for a pull request's branch."""
        del pr_number
        with _git_host_errors(repo_url):
            ci_status = await _repo_service().get_ci_status(
                repo_url, branch, user_id=principal.user_id
            )
        return CIStatusResponse(status=ci_status.value)

    return router
