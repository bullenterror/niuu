# NIU-1132 review (re-check)

## Verdict

**pass**

## Prior review follow-up verification

The prior request to retain observed partial usage on terminal records is satisfied
on the live repository-root `regin` branch at `216f2dca`:

- Native streaming stores the latest `MESSAGE_DONE` usage and terminal emission
  uses that observed value even when the provider later raises
  (`src/ravn/agent.py:1381-1428,1540-1600`).
- CLI transport event handling retains an observed `modelUsage` payload; the
  turn `finally` preserves it when a later `last_result` omits usage, and the
  terminal record maps it to normalized usage
  (`src/ravn/adapters/executors/cli.py:492-507,590-640,735-738`).
- The re-check regression verifies both native and CLI usage reported before a
  provider failure is present in the emitted terminal records
  (`tests/test_ravn/test_harness_telemetry.py:667-694`).

The earlier duration and error-record requests remain satisfied: CLI provider
duration excludes the merged union of tool intervals (`src/ravn/adapters/executors/cli.py:642-656`), and failure records carry a content-safe error category
(`src/ravn/agent.py:589-603`, `src/ravn/adapters/executors/cli.py:388-413,590-640`).

## Findings

No blocking findings.

## Verification notes

- Reviewed `regin` at `216f2dca` and the committed diff
  `git diff a7e39a0974d400187c6d39f723dcc9afd3dce9d0..HEAD`; `git diff --check`
  passed.
- Passed: `uv run --extra otel ruff check src/ravn/agent.py
  src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py
  tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run --extra otel ruff format --check src/ravn/agent.py
  src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py
  tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py
  tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn
  tests/test_ravn/test_prompt_budget.py` — 74 passed.

## Recommendation

Approve NIU-1132 on the required `regin` branch.
