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

## Operator-directed scope resolution (2026-10-22)

The operator resolved the two findings for the in-scope NIU-1132 revision:

1. The current CLI transport provides only full-turn timing. Its observed value
   remains in `provider_duration_ms`, while
   `timing.provider_vs_tool_breakdown` explicitly records that a provider-only
   split is unavailable. Altering the shared transport contract is a separate
   ticket.
2. Native and CLI-backed exception and cancellation paths already emit a
   `ravn.harness.step` record before propagating the failure, retaining the
   established `error` and `aborted` classification. Focused terminal-record
   tests cover provider failure, cancellation, start failure, and partial-text
   failure without introducing another observability port.

This supersedes the blocking recommendation above for the operator-approved
scope. Gate re-review is requested after the focused verification recorded in
`10-implementation.md`.

## Gate re-check: provider timing and terminal taxonomy (2026-10-22)

### Verdict

**pass**

### Prior review follow-up verification

This re-check verifies the two concrete findings from the prior gate review on
the live `regin` branch at `eba1d1cf`:

- CLI records now retain the complete observed turn duration separately and
  export `provider_duration_ms` as the duration minus observed completed tool
  wall time (`src/ravn/adapters/executors/cli.py:466-470,544,613-617`). The
  regression simulates five seconds of tool time followed by two seconds of
  provider time and asserts a 2,000 ms provider duration
  (`tests/test_ravn/test_harness_telemetry.py:223-239`).
- Native provider failures emit `stop_reason="error"` with a safe error
  category, while CLI provider failures emit `stop_reason="provider_error"`
  and the same taxonomy. Both cancellation paths preserve `aborted`
  (`src/ravn/agent.py:590-601`,
  `src/ravn/adapters/executors/cli.py:363-388,557-611`,
  `tests/test_ravn/test_harness_telemetry.py:438-519`).

### Findings

No blocking findings.

### Verification notes

- Reviewed the committed repository-root diff
  `git diff a7e39a0974d400187c6d39f723dcc9afd3dce9d0..eba1d1cf` and
  `git diff --check a7e39a0974d400187c6d39f723dcc9afd3dce9d0..eba1d1cf`.
- Passed: `uv run --extra otel ruff check src/ravn/agent.py
  src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py
  tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run --extra otel pytest -q
  tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py
  tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn
  tests/test_ravn/test_prompt_budget.py` — 71 passed.

### Recommendation

Approve NIU-1132 on `regin`.
