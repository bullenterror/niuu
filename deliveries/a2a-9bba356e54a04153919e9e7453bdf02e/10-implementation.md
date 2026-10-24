# NIU-1132 implementation revision

## Changes

- Retained the last observed native streamed usage and used it in terminal
  harness-step records after a provider failure.
- Captured CLI `modelUsage` payloads as transport events arrive and refreshed
  the payload in the turn `finally` block, so terminal records retain observed
  usage when `run_prompt()` raises.
- Added native and CLI regressions covering usage reported before provider
  failure.

## Verification

- `uv run --extra otel ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py tests/test_ravn/test_harness_telemetry.py`
- `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py` (`10 passed`)
- `uv run --extra otel pytest -q tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_harness_telemetry.py` (`55 passed`)

## Delivery

Direct-to-`regin` delivery; no hosted PR was created.
