# NIU-300 closure — Subscribe ODIN realm detail to SSE stream

- **Tracker:** `NIU-300` (`a8939934-dc0d-4d0e-b89e-6ca5d3089055`)
- **Merged branch:** `feat/niu-300-realm-detail-sse`
- **Target branch:** `regin`
- **Merge commit:** `24b65ddc71c58a677e28a5ddae0c585fc3a45cb1`
- **Final tracker status:** `Done`

## Landed summary

The ODIN realm-detail surface now receives authenticated `realm.detail` SSE
snapshots, updates its realm and trust-grant caches, and closes the stream on
unmount. The landed follow-up also covers the stream lifecycle in a focused
hook test and makes the stream interval configuration-owned through Volundr
and its chart.
