# NIU-1132 review (re-check)

## Verdict

**needs_changes**

## Prior review follow-up

The prior requested follow-up is satisfied on the repository-root `regin` branch:

- CLI `provider_duration_ms` is now explicitly unavailable when the transport
  cannot expose a provider boundary (`src/ravn/adapters/executors/cli.py:494-535`).
- Native and CLI provider failures/cancellations now emit terminal canonical
  records before propagating (`src/ravn/agent.py:569-587`,
  `src/ravn/adapters/executors/cli.py:348-373`), with regression coverage in
  `tests/test_ravn/test_harness_telemetry.py:351-410`.

## Finding

### Major — terminal records misreport TTFT after partial streamed output

The native terminal path always declares TTFT unavailable as
`provider_call_terminated_before_text` when `response is None`
(`src/ravn/agent.py:1366-1368`), even though a prior text delta has already
recorded a real `_last_ttft_ms` (`src/ravn/agent.py:1543-1547`). The record
therefore contains a numeric TTFT and an unavailable reason saying no text was
received. The CLI path loses the same fact outright: it unconditionally emits
`ttft_ms=None` with that reason (`src/ravn/adapters/executors/cli.py:537-575`)
after `_record_first_output()` has captured it (`src/ravn/adapters/executors/cli.py:863-866`).

This occurs when a provider/CLI transport fails or is cancelled after streaming
at least one text token. It violates the canonical schema's explicit
availability contract and makes failure telemetry contradict the observable
execution.

**Fix:** In both terminal emitters, preserve the recorded TTFT and omit the
unavailable reason when a first text token was observed; only mark TTFT
unavailable when it is actually `None`. Add native and fake-CLI regression
cases that stream a text delta and then raise, asserting a populated TTFT with
no `timing.ttft_ms` unavailable entry.

## Verification notes

- Reviewed the live `regin` branch at `d520d3f9`, using
  `git diff e2eec6dc..HEAD`; `git diff --check e2eec6dc..HEAD` passed.
- Passed: `uv run --extra otel ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py src/ravn/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` (68 passed).
- Direct failure-after-text probes reproduced the contradiction for both native
  and CLI-backed harnesses: native emitted a numeric TTFT plus the unavailable
  reason; CLI emitted no TTFT plus that reason.

## Recommendation

Do not merge until terminal TTFT availability reflects whether text was already
streamed, with regression coverage for both harnesses.
