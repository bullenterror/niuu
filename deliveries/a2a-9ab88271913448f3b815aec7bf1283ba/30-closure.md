# NIU-1132 closure

- **Tracker identifier:** `NIU-1132`
- **Merged branch:** `regin`
- **Target branch:** `regin`
- **Merge commit SHA:** `a7e39a0974d400187c6d39f723dcc9afd3dce9d0` (direct-to-target delivery; no separate PR merge commit)
- **Final tracker status:** `Done`

## Landed

The Ravn observability surface now emits the additive, content-safe canonical
`ravn.harness.step` record for native and CLI-backed execution. The shared
record reports step context, model/provider facts, prompt-section estimates,
compaction, timing, tool duration, usage, stop/recovery state, harness type,
and explicit unavailable fields; existing telemetry remains intact. The
cross-harness regression verifies unified records, including terminal calls
that retain observed TTFT after streamed text.
