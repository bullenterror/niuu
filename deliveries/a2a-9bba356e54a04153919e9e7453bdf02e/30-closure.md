# NIU-1132 closure

- **Tracker identifier:** `NIU-1132`
- **Merged branch:** `regin`
- **Target branch:** `regin`
- **Merge commit SHA:** `eba1d1cf0e632b9841a17e90a96a8f0c3a1938e1` (direct-to-target delivery; no separate PR merge commit)
- **Final tracker status:** `Done`

## Landed

Ravn's CLI-backed canonical step telemetry now reports provider duration excluding observed tool wall time. Native and CLI provider failures emit content-safe terminal step records with normalized error taxonomy and the required stop reasons; focused lint and telemetry tests pass.
