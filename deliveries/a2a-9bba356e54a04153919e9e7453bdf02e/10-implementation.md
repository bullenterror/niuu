# NIU-1132 implementation revision

## Changes

- Restored canonical terminal step records for native and CLI provider failures, with `llm_error_category`; CLI errors use `stop_reason="provider_error"`.
- Track CLI tool start/end intervals and compute provider duration by subtracting their merged union from the observed turn duration.
- Treat a tool that is still active when a turn terminates as an interval ending at the observed turn end, preventing its elapsed time from being misreported as provider time.

## Verification

- `uv run --extra otel ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py`
- `uv run --extra otel ruff format --check src/ravn/agent.py src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py`
- `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` (`73 passed`)

## Delivery

Direct-to-`regin` delivery; no hosted PR was created.
