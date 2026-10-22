# NIU-1132 review

## Verdict

**needs_changes**

## Findings

1. **Major — CLI provider duration is incorrect whenever remote tool intervals overlap or a tool is still running when the turn fails.** `src/ravn/adapters/executors/cli.py:613-617` subtracts the sum of completed-tool durations from the whole CLI turn. Parallel five-second tools in a seven-second turn therefore report zero provider time rather than two seconds; an error after a tool starts but before its result arrives subtracts none of that tool time and reports it as provider time. Track tool start/end intervals and subtract their union; for an unfinished interval, either account for its elapsed overlap or mark provider duration unavailable. Add success and terminal-failure regressions covering these cases.

## Verification notes

- Reviewed live `regin` at `6f192616`; inspected `git diff a7e39a0974d400187c6d39f723dcc9afd3dce9d0..HEAD` and `git diff --check`.
- `uv run --extra otel ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py` passed.
- `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` passed: 71 tests.

## Recommendation

Do not approve until provider timing excludes all tool execution without undercounting parallel calls or misclassifying unfinished work.
