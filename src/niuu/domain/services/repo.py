"""Domain service for repository and provider management."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from niuu.domain.models import (
    CIStatus,
    GitProviderType,
    PullRequest,
    RepoInfo,
)
from niuu.ports.git import GitWorkflowProvider

if TYPE_CHECKING:
    from niuu.adapters.outbound.git_registry import GitProviderRegistry
    from niuu.ports.user_integration import UserIntegrationPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderInfo:
    """Summary of a configured git provider."""

    name: str
    type: GitProviderType
    orgs: tuple[str, ...]


class RepoService:
    """Service for listing providers and their repositories.

    When a ``user_integration`` service is available, repo and branch
    listing is user-scoped: shared/org-level providers are combined
    with the user's own integration connections (credentials resolved
    on-the-fly, never cached).  Without it, falls back to shared only.
    """

    def __init__(
        self,
        git_registry: GitProviderRegistry,
        user_integration: UserIntegrationPort | None = None,
    ):
        self._git_registry = git_registry
        self._user_integration = user_integration

    def list_providers(self) -> list[ProviderInfo]:
        """List all configured git providers."""
        return [
            ProviderInfo(
                name=p.name,
                type=p.provider_type,
                orgs=p.orgs,
            )
            for p in self._git_registry.providers
        ]

    async def list_repos(
        self,
        user_id: str | None = None,
    ) -> dict[str, list[RepoInfo]]:
        """List repositories, optionally scoped to a user.

        When *user_id* is provided and a ``UserIntegrationService`` is
        available, includes repos from the user's personal integration
        connections in addition to the shared/org-level providers.
        """
        if user_id and self._user_integration:
            return await self._list_repos_for_user(user_id)
        return await self._git_registry.list_configured_repos()

    async def list_branches(
        self,
        repo_url: str,
        user_id: str | None = None,
    ) -> list[str]:
        """List branches, preferring the user's credentials if available."""
        if user_id and self._user_integration:
            provider = await self._user_integration.find_git_provider_for(
                repo_url,
                user_id,
            )
            if provider:
                return await provider.list_branches(repo_url)

        return await self._git_registry.list_branches(repo_url)

    async def list_pull_requests(
        self,
        repo_url: str,
        status: str = "open",
        user_id: str | None = None,
    ) -> list[PullRequest]:
        """List pull requests straight from the Git host."""
        provider = await self._workflow_provider(repo_url, user_id)
        return await provider.list_pull_requests(repo_url, status)

    async def get_pull_request(
        self,
        repo_url: str,
        pr_number: int,
        user_id: str | None = None,
    ) -> PullRequest | None:
        """Get one pull request; ``None`` when the host has no such number."""
        provider = await self._workflow_provider(repo_url, user_id)
        return await provider.get_pull_request(repo_url, pr_number)

    async def merge_pull_request(
        self,
        repo_url: str,
        pr_number: int,
        merge_method: str,
        user_id: str | None = None,
    ) -> bool:
        """Merge a pull request; ``False`` when the host refused the merge."""
        provider = await self._workflow_provider(repo_url, user_id)
        return await provider.merge_pull_request(repo_url, pr_number, merge_method)

    async def get_ci_status(
        self,
        repo_url: str,
        branch: str,
        user_id: str | None = None,
    ) -> CIStatus:
        """CI status of a branch as the Git host reports it."""
        provider = await self._workflow_provider(repo_url, user_id)
        return await provider.get_ci_status(repo_url, branch)

    async def _workflow_provider(
        self,
        repo_url: str,
        user_id: str | None,
    ) -> GitWorkflowProvider:
        """Resolve the provider for *repo_url* the same way branch listing does.

        Raises:
            ValueError: no connected Git host serves the URL, or the host
                serving it has no pull-request workflow support.
        """
        provider = None
        if user_id and self._user_integration:
            provider = await self._user_integration.find_git_provider_for(repo_url, user_id)
        if provider is None:
            provider = self._git_registry.get_provider(repo_url)
        if provider is None:
            raise ValueError(f"No git provider found for: {repo_url}")
        if not isinstance(provider, GitWorkflowProvider):
            raise ValueError(f"Provider {provider.name} does not support pull requests")
        return provider

    async def _list_repos_for_user(
        self,
        user_id: str,
    ) -> dict[str, list[RepoInfo]]:
        """Query shared + user providers concurrently, group by provider."""
        providers = await self._user_integration.get_git_providers(user_id)

        sem = asyncio.Semaphore(10)

        async def _capped(coro):
            async with sem:
                return await coro

        shared = {id(provider) for provider in self._git_registry.providers}
        tasks = []
        task_labels: list[str] = []
        for provider in providers:
            # A personal account added without organisations still has
            # repositories: everything its token can reach. Shared providers
            # from config keep needing explicit orgs.
            orgs: tuple[str, ...] = tuple(provider.orgs)
            if not orgs and id(provider) not in shared:
                orgs = ("",)
            for org in orgs:
                tasks.append(_capped(provider.list_repos(org)))
                task_labels.append(provider.name)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        by_provider: dict[str, list[RepoInfo]] = {}
        seen_urls: set[str] = set()
        for label, result in zip(task_labels, results):
            if isinstance(result, BaseException):
                logger.warning("Provider %s error: %s", label, result)
                continue
            for repo in result:
                if repo.url in seen_urls:
                    continue
                seen_urls.add(repo.url)
                by_provider.setdefault(label, []).append(repo)

        return by_provider
