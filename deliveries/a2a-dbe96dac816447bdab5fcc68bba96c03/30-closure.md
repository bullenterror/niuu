# NIU-298 closure

- Tracker: `NIU-298`
- Merged branch: `fix/niu-298-poller-cadence`
- Target branch: `regin`
- Merge commit: `525f7b4352fa5bf261ef55de3b8f267a8b746851` (PR #1163)
- Final tracker status: `Done`

## Operator summary

The Yggdrasil RealmSummary SSE stream and background polling delivery landed in
`regin`. The final cadence fix makes the recurring poller wait one configured
interval after the startup snapshot, avoiding an immediate duplicate adapter
poll; its regression coverage passed the focused lint and Yggdrasil coverage
gate.
