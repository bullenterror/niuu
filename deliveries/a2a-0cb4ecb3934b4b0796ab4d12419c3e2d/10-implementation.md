# NIU-1138 implementation and verification

## Change

A2A `SendMessage` now detects workflows with a single durable subworkflow
parent, reserves the owner-bound `WorkflowExecution`, and launches through the
same trusted runtime-context body used by the research API. After launching
(or recovering) the session, Ting attaches that session to the reserved parent
and records the execution ID on the A2A campaign.

This supplies Forge/Ravn with `ravn_config.workflow_execution` and its
owner-bound credential projection rather than asking the Research Campaign
coordinator to start without its required tools.

## Verification

- Passed: `uv run ruff check src/ting/api/a2a.py tests/test_ting/test_a2a_tasks.py`.
- Passed: `uv run --extra dev --extra otel pytest -q tests/test_ting/test_a2a_tasks.py` — 64 passed.
- Passed: `uv run --extra dev --extra otel pytest -q tests/test_ting/test_a2a_tasks.py tests/test_ting/test_research_durable_execution.py tests/test_ting/test_workflows_api.py -k 'workflow_execution or durable or fan_out or launches_workflow_and_returns_submitted_task'` — 11 passed.
- Added a regression test using the bundled Research Campaign skill, a
  `connectionId`, and `repo`/`branch` metadata. It proves `TASK_STATE_SUBMITTED`,
  the reserved execution's parent-session attachment, and the bound Ravn
  workflow-execution configuration.

## Delivery

The live Yggdrasil endpoint and its external Forge connection are not available
from this workspace, so the external framed-research run cannot be performed
here. The focused launch contract test proves the setup failure path is removed.
The branch must be pushed and a GitHub pull request opened with base `regin`
only; it must not target `dev` or `main`.

Pull request: [#1165](https://github.com/niuulabs/niuu/pull/1165), targeting
`regin` only.

## Review revision

The fan-out parent launch now preserves the active W3C context in its trusted
provenance: it merges `telemetry.inject() or trace_context` without replacing
the owner-bound `workflow_execution` provenance. The Research Campaign A2A
regression test now supplies `traceContext` and asserts the spawned workload
carries it alongside the durable execution context.

- Passed: `uv run ruff check src/ting/api/a2a.py tests/test_ting/test_a2a_tasks.py`.
- Passed: `uv run --extra dev --extra otel pytest -q tests/test_ting/test_a2a_tasks.py` — 64 passed.
