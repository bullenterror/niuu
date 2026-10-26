"""volundr_git reads: commits, comparisons and branch CI through the platform."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from ravn.adapters.tools.platform_tools import VolundrGitTool

BASE_URL = "http://localhost:8080"
NIUU_REPOS_URL = f"{BASE_URL}/api/v1/niuu/repos"
REPO = "https://github.com/niuulabs/niuu"


@pytest.fixture
def tool() -> VolundrGitTool:
    return VolundrGitTool(base_url=BASE_URL)


def test_schema_offers_the_reads_with_shaping_arguments(tool: VolundrGitTool) -> None:
    properties = tool.input_schema["properties"]

    assert {"get_commit", "compare", "ref_checks"} <= set(properties["action"]["enum"])
    assert properties["path"]["type"] == "array"
    assert properties["include_patch"]["type"] == "boolean"
    for name in ("ref", "base", "head"):
        assert name in properties


def test_description_steers_the_model_off_anonymous_provider_calls(tool: VolundrGitTool) -> None:
    description = tool.description

    assert "api.github.com" in description
    assert "rate limited" in description
    for action in ("get_commit", "compare", "ref_checks"):
        assert action in description
    assert "include_patch" in description


@pytest.mark.asyncio
@respx.mock
async def test_get_commit_asks_for_the_file_list_by_default(tool: VolundrGitTool) -> None:
    route = respx.get(f"{NIUU_REPOS_URL}/commit").mock(
        return_value=httpx.Response(200, json={"sha": "a" * 40, "files": []})
    )

    result = await tool.execute({"action": "get_commit", "repo_url": REPO, "ref": "regin"})

    assert not result.is_error
    assert json.loads(result.content)["sha"] == "a" * 40
    params = route.calls.last.request.url.params
    assert params["repo_url"] == REPO
    assert params["ref"] == "regin"
    assert "include_patch" not in params
    assert "path" not in params


@pytest.mark.asyncio
@respx.mock
async def test_get_commit_passes_path_filters_and_patch_flag(tool: VolundrGitTool) -> None:
    route = respx.get(f"{NIUU_REPOS_URL}/commit").mock(
        return_value=httpx.Response(200, json={"sha": "a" * 40, "files": []})
    )

    await tool.execute(
        {
            "action": "get_commit",
            "repo_url": REPO,
            "ref": "regin",
            "path": ["src/a.py", "docs/"],
            "include_patch": True,
        }
    )

    params = route.calls.last.request.url.params
    assert params.get_list("path") == ["src/a.py", "docs/"]
    assert params["include_patch"] == "true"


@pytest.mark.asyncio
@respx.mock
async def test_a_single_path_string_is_accepted(tool: VolundrGitTool) -> None:
    route = respx.get(f"{NIUU_REPOS_URL}/compare").mock(
        return_value=httpx.Response(200, json={"files": []})
    )

    await tool.execute(
        {
            "action": "compare",
            "repo_url": REPO,
            "base": "main",
            "head": "regin",
            "path": "src/a.py",
        }
    )

    params = route.calls.last.request.url.params
    assert params.get_list("path") == ["src/a.py"]
    assert params["base"] == "main"
    assert params["head"] == "regin"


@pytest.mark.asyncio
@respx.mock
async def test_ref_checks_reads_the_checks_route(tool: VolundrGitTool) -> None:
    route = respx.get(f"{NIUU_REPOS_URL}/checks").mock(
        return_value=httpx.Response(200, json={"status": "failing", "checks": []})
    )

    result = await tool.execute({"action": "ref_checks", "repo_url": REPO, "ref": "regin"})

    assert json.loads(result.content)["status"] == "failing"
    params = route.calls.last.request.url.params
    assert params["repo_url"] == REPO
    assert params["ref"] == "regin"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("input", "needle"),
    [
        ({"action": "get_commit", "repo_url": REPO}, "repo_url and ref are required"),
        ({"action": "get_commit", "ref": "x"}, "repo_url and ref are required"),
        ({"action": "compare", "repo_url": REPO, "base": "a"}, "repo_url, base and head"),
        ({"action": "ref_checks", "ref": "x"}, "repo_url and ref are required"),
    ],
)
async def test_missing_arguments_are_reported(
    tool: VolundrGitTool, input: dict, needle: str
) -> None:
    result = await tool.execute(input)

    assert result.is_error
    assert needle in result.content


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("input", "route", "label"),
    [
        ({"action": "get_commit", "repo_url": REPO, "ref": "ghost"}, "commit", "read commit"),
        (
            {"action": "compare", "repo_url": REPO, "base": "a", "head": "ghost"},
            "compare",
            "compare",
        ),
        ({"action": "ref_checks", "repo_url": REPO, "ref": "ghost"}, "checks", "read checks"),
    ],
)
async def test_failures_carry_the_platforms_explanation(
    tool: VolundrGitTool, input: dict, route: str, label: str
) -> None:
    respx.get(f"{NIUU_REPOS_URL}/{route}").mock(
        return_value=httpx.Response(404, json={"detail": "Not found: ref 'ghost'"})
    )

    result = await tool.execute(input)

    assert result.is_error
    assert label in result.content
    assert "Not found: ref 'ghost'" in result.content
