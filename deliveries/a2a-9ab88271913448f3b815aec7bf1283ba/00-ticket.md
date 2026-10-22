# NIU-1132 — Canonical per-step harness telemetry

- Delivery slug: `a2a-9ab88271913448f3b815aec7bf1283ba`
- Required base and delivery branch: `regin`
- Tracker: [NIU-1132](https://linear.app/niuu/issue/NIU-1132/emit-canonical-per-step-harness-telemetry-for-native-and-external)
- Tracker status: `In Review`

## Scope

Emit one content-safe canonical step record for both the native `RavnAgent`
and CLI-backed transport harnesses. The record exposes harness type, stable
step/session/task identities, model/provider call facts, prompt-composition
estimates when exposed by the harness, compaction, timings, tool wall time,
usage, stop reason, and retry/recovery state. It deliberately excludes prompts,
tool inputs, tool outputs, and model text.

## Revision

The review follow-up keeps a native harness-step span open from the provider
call through tool execution and canonical event emission. It also exports the
content-safe canonical fields as bounded event attributes when observability
content capture is disabled.

## Review revision (2026-10-22)

Tracker status was moved to **In Progress** for the requested review revision. The
remaining acceptance issues are provider-duration comparability and terminal
failure/abort records in both runtime harnesses.

## Review revision: streamed terminal TTFT (2026-10-22)

A terminal native or CLI-backed record now preserves its measured TTFT if text
was streamed before the provider/transport failed or was cancelled. The TTFT
field is marked unavailable only when no text token was observed, preventing a
numeric telemetry value from contradicting its availability metadata.

## Review revision: CLI timing boundary (2026-10-22)

The CLI transport is intentionally unchanged. Its available measurement is the
complete `CliTurnRunner` turn, not a provider-only boundary; the canonical
`provider_duration_ms` field records that observed full-turn duration and
`timing.provider_vs_tool_breakdown` is explicitly unavailable with reason
`cli_transport_exposes_only_full_turn_duration`. Native records continue to
report their provider-only duration. Failure and cancellation paths continue to
emit terminal records through the existing `ravn.harness.step` observability
event before propagating the existing error classification.

## Operator-directed scope resolution (2026-10-22)

Tracker status is **In Progress** while this revision returns to the gate. The
operator confirmed that changing the shared CLI transport contract is outside
NIU-1132. The existing full `CliTurnRunner` duration remains the available
CLI value in `provider_duration_ms`, and
`timing.provider_vs_tool_breakdown` explicitly states that a provider-only
split is unavailable. Native records continue to report provider-only timing.
