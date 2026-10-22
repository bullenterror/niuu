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
