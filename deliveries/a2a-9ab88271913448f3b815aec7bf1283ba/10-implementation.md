# NIU-1132 implementation and verification

## Change

`HarnessStepTelemetryRecord` is the shared, JSON-safe schema emitted as the
existing `ravn.harness.step` observability event. It has an explicit
`unavailable` map and matching availability attributes, so unavailable values
(such as TTFT when no text token is streamed) are not replaced with zero.

The native harness reuses NIU-1118's existing prompt-section estimates and
compaction result, measures provider duration/TTFT/tool wall time, and records
per-iteration retry state. The CLI-backed harness maps its transport result,
streamed output, tool lifecycle, and model usage into the same schema. Existing
`gen_ai.*` and Ravn telemetry remains unchanged and is emitted alongside the
new event.

## Review revision

Native steps now run in a `ravn harness step` span that stays active through
the nested provider call, any tool execution, and the canonical event. This
ensures a native event is exported even when no ambient parent span exists.

Canonical prompt-section estimates are serialized into a bounded safe event
attribute (at most 32 names of 128 characters), and usage now includes cache
read/write and thinking tokens. These attributes are emitted regardless of
`capture_content`; raw prompts, tool inputs/results, and model text remain
content-only and are not exported by default.

## Cross-harness verification

`tests/test_ravn/test_harness_telemetry.py` runs a native and a CLI-backed
fixture, captures their `ravn.harness.step` events, and asserts the same schema
for both. The fixture also verifies explicit unavailable TTFT for no-text
responses.

## Verification

- Passed: `uv run ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py src/ravn/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run pytest -q tests/test_ravn/test_executor_cli.py tests/test_ravn/test_harness_telemetry.py` — 40 passed, 1 skipped.
- Passed: `uv run pytest -q tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` — 24 passed.
- `tests/test_ravn/test_agent.py` has one pre-existing failing persisted-commission test (`test_build_tool_reuses_persisted_commission_after_restart`); rerunning it alone fails with a regenerated operation ID and is unrelated to harness telemetry.

### Revision verification

- Passed: `uv run --extra otel ruff check src/ravn/agent.py src/ravn/domain/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py` — 42 passed.
- The SDK-backed cross-harness test runs with `capture_content=False`, proves both harnesses export `ravn.harness.step` without an ambient parent span, and checks prompt sections plus cache/write/thinking usage attributes.

## Delivery

Revision committed and pushed directly to the required `regin` branch (`73e6cb6a`). No hosted PR is
created because the required delivery branch and merge target are both `regin`;
a forge PR cannot use the same branch as its head and base.

## Review revision: timing and terminal calls

CLI transports do not expose a provider-call boundary, so their canonical
`provider_duration_ms` is now explicitly unavailable rather than measuring the
full CLI turn (which can include remote tool execution). The existing CLI turn
duration metric remains unchanged.

Both native and CLI-backed provider exceptions and cancellations now emit one
content-safe terminal `ravn.harness.step` record before re-raising. Terminal
records normalize the stop/recovery state to `error` or `aborted` and explicitly
mark unavailable usage and TTFT; CLI terminal records also mark provider and
tool timing unavailable when no reliable boundary exists.

### Revision verification

- Passed: `uv run --extra otel ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` — 68 passed.
- No hosted PR is created: the required delivery branch and merge target are both `regin`, so this is a direct-to-branch delivery.

## Review revision: streamed terminal TTFT

Terminal native and CLI-backed harness records now retain an observed TTFT after
partial streamed text and omit `timing.ttft_ms` from `unavailable`. Calls that
end before any text still retain the explicit
`provider_call_terminated_before_text` reason. The cross-harness regression
uses a streaming native LLM and fake CLI transport that each emit text then
raise.

### Revision verification

- Passed: `uv run --extra otel ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` — 69 passed.
- No hosted PR is created: the required delivery branch and merge target are both `regin`, so this is a direct-to-branch delivery.

## Review revision: CLI provider timing boundary

No shared CLI transport contract or schema was changed. `CliTransportAgent`
measures the existing `CliTurnRunner.run_prompt` operation and places that
complete external-turn duration in `provider_duration_ms`, which is the timing
the current transport path actually exposes. Because that duration can include
remote tool execution, the record explicitly adds
`timing.provider_vs_tool_breakdown=cli_transport_exposes_only_full_turn_duration`
to `unavailable`; it does not claim a fabricated provider-only split. Native
runtime records retain their provider-only measurement.

Terminal CLI exceptions and cancellations use the same measured complete-turn
duration when available and emit one existing `ravn.harness.step` event before
the original error propagates. The regression covers successful, failed, and
aborted fake CLI transports.

### Revision verification

- Passed: `uv run --extra otel ruff check src/ravn/adapters/executors/cli.py tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` — 69 passed.
- No hosted PR is created: the delivery and target branch are both `regin`, so this is a direct-to-branch review revision.

## Operator-directed scope resolution (2026-10-22)

The operator confirmed that a provider-only CLI timing boundary would require a
separate shared transport-contract ticket and is not part of NIU-1132. The
in-scope implementation therefore retains the observable full CLI turn in
`provider_duration_ms` and explicitly marks the finer provider-versus-tool
breakdown unavailable. Existing terminal error and cancellation handling emits
one `ravn.harness.step` record before re-raising, using the established
`error` and `aborted` classifications; terminal telemetry tests cover both
paths.

### Verification

- Passed: `uv run --extra otel ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py src/ravn/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py`.
- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` — 70 passed.

## Review revision: provider-only timing and terminal taxonomy

`CliTransportAgent` now derives `provider_duration_ms` by subtracting the
already-observed remote tool wall time from the full `CliTurnRunner` duration.
The separate `tool_wall_time_ms` remains unchanged, and the prior unavailable
provider/tool-breakdown marker is removed because the canonical provider field
is normalized to exclude completed tool work.

`HarnessStepTelemetryRecord` now carries `llm_error_category`. Native and CLI
terminal paths classify exceptions without recording their messages: timeout
exception types map to `timeout`, cancellations to `aborted`, and other
provider failures to `provider_error`. CLI terminal provider failures use
`stop_reason=provider_error`; when the transport supplied partial usage, that
usage is retained rather than fabricated or discarded.

### Verification

- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` — 71 passed.
- Passed: `uv run --extra otel ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py`.
- The deterministic CLI regression models five seconds of tool work followed by two seconds of provider time and asserts `provider_duration_ms == 2000` while tool wall time remains `5000`.

No hosted PR is created: the required delivery and target branch are both
`regin`, so this review revision is delivered directly to that branch.
