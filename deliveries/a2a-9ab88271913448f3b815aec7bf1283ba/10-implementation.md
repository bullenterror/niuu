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

## Delivery

Committed and pushed directly to the required `regin` branch. No hosted PR is
created because the required delivery branch and merge target are both `regin`;
a forge PR cannot use the same branch as its head and base.
