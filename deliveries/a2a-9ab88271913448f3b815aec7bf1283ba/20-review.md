# NIU-1132 review (re-check)

## Verdict

**needs_changes**

## Prior review follow-up

The two prior major findings are satisfied on the repository-root `regin` branch:

- `src/ravn/agent.py:568-683` now holds a native `ravn harness step` span open
  through the provider call, tool execution, and canonical event emission.
- `src/ravn/domain/harness_telemetry.py:100-107` exports bounded prompt-section
  estimates and the full usage breakdown as attributes, and
  `tests/test_ravn/test_harness_telemetry.py:170-262` verifies both harnesses
  with `capture_content=False`.

## Findings

### Major — CLI provider duration includes tool execution time

`src/ravn/adapters/executors/cli.py:445-447` measures
`CliTurnRunner.run_prompt()` from start to finish and stores it as
`provider_duration_ms`. A CLI-backed run includes remote tool execution inside
that interval, while the native `provider_duration_ms` only encloses the model
stream (native tools are timed separately at `src/ravn/agent.py:637-639`). A
cross-harness query will therefore attribute tool wall time to the CLI provider
as well as to `tool_wall_time_ms`, yielding an incomparable/overstated provider
call duration whenever a CLI turn invokes a tool.

**Fix:** Populate `provider_duration_ms` only from CLI transport events that
bound a provider call. If that boundary is not exposed, emit `None` and add an
explicit `timing.provider_duration_ms` unavailable reason; retain any whole-run
duration under a separate, accurately named field if it is useful.

### Major — failed or aborted calls emit no canonical step record

The native call at `src/ravn/agent.py:569-573` exits its step span on a provider
exception before `_emit_native_harness_step()` is reached. Likewise, the CLI
exception path at `src/ravn/adapters/executors/cli.py:349-361` re-raises before
the emitter at line 412. Consequently the canonical schema has no event for
provider failures/aborted runs and cannot expose their stop/error or unavailable
timing/usage fields, despite the ticket explicitly requiring unavailable-field
behavior for aborted calls.

**Fix:** In each harness, emit a content-safe terminal step record in the
exception/abort path before propagating the original error. Mark unavailable
fields (including usage/TTFT as appropriate) explicitly and use a normalized,
non-content-bearing failure/abort category. Add native and fake-CLI regression
coverage that asserts one emitted record on this path.

## Verification notes

- Reviewed live `regin` / `origin/regin` at `5c41853d`, with the delivery diff
  `e2eec6dc..HEAD`; the branch has no local source modifications.
- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_harness_telemetry.py tests/test_ravn/test_executor_cli.py` (42 passed).
- Passed: `uv run --extra otel pytest -q tests/test_ravn/test_agent.py::TestRavnAgentSimpleTurn tests/test_ravn/test_prompt_budget.py` (24 passed).
- Passed: `uv run --extra otel ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py src/ravn/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py`.
- Passed: `git diff --check e2eec6dc..HEAD`.

## Recommendation

Do not merge until the CLI timing is normalized and failure/abort records are
emitted consistently by both harnesses.

## Revision implementation evidence

The revision makes CLI `provider_duration_ms` unavailable with the explicit
`cli_transport_does_not_expose_provider_boundary` reason, rather than timing the
full `run_prompt()` interval. Native and CLI exception/cancellation paths now
emit normalized terminal step records before propagation. Focused regression
coverage validates both harnesses for errors and aborted calls.
