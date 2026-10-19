# NIU-1113 implementation and verification

## Change

Added `test_ravn_a2a_tool_build_backend_commissions_real_workflow_task` to
`tests/integration/volundr/test_a2a_workflow_task_lifecycle.py`.

The test deliberately does not inject a fake A2A HTTP client. It creates a
real loopback Volundr REST server from the production session router and a
real loopback Ting server containing the production agent-card and A2A
JSON-RPC routers. It uses PostgreSQL workflow, campaign, A2A-launch
reservation, and session repositories. The concrete
`A2AToolBuildBackend` uses `HttpxJsonClient` to fetch Ting's agent card,
select the configured workflow id, submit `SendMessage`, and poll `GetTask`.
The assertion proves the resulting campaign and session were persisted by the
normal adapters. Because this isolated workflow has no model runtime, its
nonterminal task correctly raises the backend's bounded-poll error rather than
pretending a tool artifact was built.

This is the real A2A commission boundary available in this delivery
environment. A remote completion with an actual tool-builder runtime requires
an operator-provided deployed Ting/Volundr endpoint and its workload identity;
none is configured here. The existing backend unit suite covers completed
inline and URL `learned_tool.json` artifacts, task errors, input handling,
selector resolution, and provenance.

## Verification

- Passed: `uv run pytest -q --no-cov tests/test_ravn/test_tool_build_backends.py` — **120 passed** (Ting A2A task and Ravn backend suites; one pre-existing Starlette/httpx deprecation warning).
- Passed: `uv run ruff check tests/integration/volundr/test_a2a_workflow_task_lifecycle.py src/ravn/adapters/tool_build/a2a.py`.
- Passed: `uv run ruff format --check tests/integration/volundr/test_a2a_workflow_task_lifecycle.py src/ravn/adapters/tool_build/a2a.py`.
- Passed: `git diff --check`.
- Attempted: `uv run pytest -q -s --no-cov -m integration tests/integration/volundr/test_a2a_workflow_task_lifecycle.py::test_ravn_a2a_tool_build_backend_commissions_real_workflow_task`.
  This worker lacks the disposable PostgreSQL role used by the integration
  fixture (`asyncpg.exceptions.InvalidAuthorizationSpecificationError: role
  "volundr_test" does not exist`), so it failed during fixture setup before
  the test body. This is an environment prerequisite, not an assertion
  failure. The test is marked `integration` and uses the same production
  PostgreSQL fixture/CI boundary as the existing A2A lifecycle proof.

## Delivery

The work is committed and pushed directly on `regin`. No hosted PR is created
for this direct-regin delivery; no branch, merge, push, or PR targets `dev` or
`main`. The tracker remains `In Progress` pending a PostgreSQL-backed
integration run and, for the strict external-runtime interpretation, a
credentialed deployed tool-builder task.
