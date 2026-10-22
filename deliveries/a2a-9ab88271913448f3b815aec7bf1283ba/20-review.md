# NIU-1132 review (re-check)

## Verdict

**pass**

## Prior review follow-up

The prior requested terminal-TTFT follow-up is satisfied on the repository-root
`regin` branch at `f7352c9a`:

- Native terminal emission now reports `timing.ttft_ms` unavailable only when
  `_last_ttft_ms` is absent (`src/ravn/agent.py:1366-1375`).
- CLI-backed terminal emission preserves `_turn_ttft_ms` and similarly omits
  the unavailable entry once text has been observed
  (`src/ravn/adapters/executors/cli.py:537-578`).
- The cross-harness regression streams text, then fails, and verifies a
  populated TTFT with no contradictory unavailable reason
  (`tests/test_ravn/test_harness_telemetry.py:288-294,326-331,431-449`).

## Findings

No blocking findings. The current revision correctly retains measured TTFT for
terminal native and CLI-backed calls after streamed text, while calls without
text retain explicit unavailable metadata.

## Verification notes

- Reviewed the live `regin` branch at `f7352c9a`; the re-check diff is
  `git diff 5431e59f..HEAD` and `git diff --check 5431e59f..HEAD` passed.
- Ran `uv run --extra otel ruff check src/ravn/agent.py
  src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py
  src/ravn/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py`:
  passed.
- Ran `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py
  tests/test_ravn/test_executor_cli.py
  tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn
  tests/test_ravn/test_prompt_budget.py`: 69 passed.

## Recommendation

Approve NIU-1132 for merge/delivery on the required `regin` branch.
