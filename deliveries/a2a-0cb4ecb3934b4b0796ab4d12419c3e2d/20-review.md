# NIU-1138 review

## Verdict

**needs_changes**

## Finding

### Major — A2A parent launch drops distributed trace propagation

`src/ting/api/a2a.py:416-426` replaces the ordinary A2A launch body with
`parent_launch_body()` for fan-out workflows. Unlike the ordinary branch at
`src/ting/api/a2a.py:443-451`, that parent body has no
`provenance.trace_context`. Thus a `traceparent` supplied on an A2A
Research Campaign request is not propagated into the spawned Ravn session.
This regresses the required W3C context continuity across A2A tasks precisely
for the workflow this patch changes, and makes its fan-out launch untraceable
as part of the caller's request.

**Fix:** Merge `telemetry.inject() or trace_context` into the trusted parent
launch provenance (without replacing its `workflow_execution` provenance), and
extend `test_fan_out_skill_binds_durable_execution_context` to assert that the
spawned workload carries the propagated `trace_context`.

## Verification

- Reviewed committed `origin/regin..HEAD` on
  `fix/niu-1138-a2a-workflow-context` (`b385ec40`).
- Confirmed PR #1165 is open with base `regin` and the expected feature head.
- `uv run ruff check src/ting/api/a2a.py tests/test_ting/test_a2a_tasks.py` — passed.
- `uv run --extra dev --extra otel pytest -q tests/test_ting/test_a2a_tasks.py` — 64 passed.
- Focused durable-workflow suite — 11 passed.

## Recommendation

Do not merge until the parent A2A launch preserves its W3C trace context and a
regression assertion covers that path.
