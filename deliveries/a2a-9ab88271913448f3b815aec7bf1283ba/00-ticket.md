# NIU-1132 — Canonical per-step harness telemetry

- Delivery slug: `a2a-9ab88271913448f3b815aec7bf1283ba`
- Required base and delivery branch: `regin`
- Tracker: [NIU-1132](https://linear.app/niuu/issue/NIU-1132/emit-canonical-per-step-harness-telemetry-for-native-and-external)
- Tracker status: `In Progress`

## Scope

Emit one content-safe canonical step record for both the native `RavnAgent`
and CLI-backed transport harnesses. The record exposes harness type, stable
step/session/task identities, model/provider call facts, prompt-composition
estimates when exposed by the harness, compaction, timings, tool wall time,
usage, stop reason, and retry/recovery state. It deliberately excludes prompts,
tool inputs, tool outputs, and model text.
