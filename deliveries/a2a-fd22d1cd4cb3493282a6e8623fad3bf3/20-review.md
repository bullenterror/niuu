# NIU-1113 review — A2A: Ravn client backend for tool builds

## Verdict

**needs_changes** — The prior review's request for a committed regin-native
handoff and concrete loopback A2A exercise is now present in `0ad42791`, and
focused unit/lint checks pass. However, the required end-to-end proof is still
not achieved: the new test deliberately expects the backend to fail before a
`learned_tool.json` is returned, and it cannot run here because the required
PostgreSQL test role is absent.

## Findings

- **Major — acceptance proof stops before the required built-tool result:**
  `tests/integration/volundr/test_a2a_workflow_task_lifecycle.py:262` asserts
  `ToolBuildError` after one poll, so this test proves task commissioning but
  not the required end-to-end path returning the canonical `learned_tool.json`.
  The ticket's acceptance check requires the Ravn backend to commission the
  task *and* receive that result. Run a real tool-builder workflow (with the
  required PostgreSQL fixture/deployment), drive it to terminal completion,
  and assert the returned `ToolBuildResult`/canonical artifact. Commit the
  successful focused integration output or CI proof.

- **Minor — verification count is inaccurate:**
  `deliveries/a2a-fd22d1cd4cb3493282a6e8623fad3bf3/10-implementation.md:26`
  records 120 passing tests for a command that currently collects 57. Update
  the closure record to state the exact command's current result (57) or name
  the additional test paths that produced 120.

## Scope and branch

- Reviewed repository root: `/workspace`.
- Reviewed branch/ref: `regin` at `0ad427918a18ef05fe849b4f36ebe006327df5c4`
  before this review-record commit; its direct parent is `8b1a1207`.
- Reviewed committed range: `8b1a1207..0ad42791`; changes are the delivery
  handoff and the production-adapter integration test. No PR is recorded.
- The prior review's concrete follow-up is partially satisfied: the committed
  handoff and loopback commission test are present. Its required successful
  real A2A end-to-end proof is not yet satisfied.
- Tracker ticket `NIU-1113` was moved to **In Review** at the start of this
  re-check. No branch, merge, push, or PR action involving `dev` or `main`
  was taken.

## Verification

- Passed: `uv run pytest -q --no-cov tests/test_ravn/test_tool_build_backends.py`
  — 57 passed.
- Passed: `uv run ruff check tests/integration/volundr/test_a2a_workflow_task_lifecycle.py src/ravn/adapters/tool_build/a2a.py`.
- Passed: `uv run ruff format --check tests/integration/volundr/test_a2a_workflow_task_lifecycle.py src/ravn/adapters/tool_build/a2a.py`.
- Passed: `git diff --check HEAD^..HEAD` for the implementation commit.
- Failed before test execution: `uv run pytest -q -s --no-cov -m integration tests/integration/volundr/test_a2a_workflow_task_lifecycle.py::test_ravn_a2a_tool_build_backend_commissions_real_workflow_task` — fixture setup raises `asyncpg.exceptions.InvalidAuthorizationSpecificationError: role "volundr_test" does not exist`.

## Recommendation

Do not approve or close NIU-1113. Supply a successful, real terminal A2A
builder task that returns `learned_tool.json` and its captured focused-test
proof; correct the closure-record test count; then request re-review.
