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

## Revision submitted for gate re-check (2026-10-22)

The CLI-backed record now retains the existing full `CliTurnRunner` duration in
`provider_duration_ms` and marks only the unavailable provider-versus-tool
breakdown. This leaves the shared CLI transport contract unchanged. Terminal
error and cancellation records remain emitted through `ravn.harness.step` with
the existing error classification. Re-review is requested.

## Gate re-check (2026-10-22)

### Verdict

**needs_changes**

### Prior review follow-up verification

The previously requested streamed-terminal-TTFT follow-up remains satisfied on
`regin`: terminal records retain observed TTFT after streamed text and omit the
contradictory unavailable reason (`src/ravn/agent.py:1370-1375`,
`src/ravn/adapters/executors/cli.py:562-565`; regression at
`tests/test_ravn/test_harness_telemetry.py:461-479`). This is a re-check, not
a first review pass.

### Findings

1. **Major — CLI provider duration is still the full external turn.**
   `src/ravn/adapters/executors/cli.py:451-456` measures the whole
   `CliTurnRunner.run_prompt` interval, and `:533-536` exports it as
   `provider_duration_ms` despite documenting that it can contain remote tool
   work. The unavailable marker does not normalize the value, so a five-second
   tool followed by a two-second provider response reports about seven seconds
   as provider time. Measure provider-only segments (or subtract the observed
   tool intervals) before assigning this field, and add the required 5s-tool /
   2s-provider regression assertion.

2. **Major — terminal error records do not carry the required error taxonomy,
   and CLI uses the wrong stop reason.** `src/ravn/adapters/executors/cli.py:364`
   emits `stop_reason="error"`, not the required `"provider_error"`; neither
   this path nor the native terminal path at `src/ravn/agent.py:577-586` sets an
   `llm_error_category`. Consequently timeout and provider failures are
   indistinguishable in canonical telemetry. Populate the canonical error
   category from the caught exception/transport failure, preserve it in the
   record, and assert native non-null taxonomy plus CLI `provider_error` and
   category in terminal-failure tests.

### Verification notes

- Reviewed the live repository-root `regin` branch at `a312a932`; committed
  re-check diff: `git diff --check a7e39a09..HEAD` passed.
- `uv run --extra otel ruff check src/ravn/adapters/executors/cli.py
  tests/test_ravn/test_harness_telemetry.py` passed.
- `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py
  tests/test_ravn/test_executor_cli.py` passed (46 tests).

### Recommendation

Do not approve. Correct both telemetry contract violations and add the
specified regression coverage, then request another gate re-check.
