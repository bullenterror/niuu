# NIU-300 closure

- Tracker identifier: `NIU-300`
- Merged branch: `regin`
- Target branch: `regin`
- Merge commit SHA: `85447e63085a69ad72b4d5933065cdd74cf5241a`
- Final tracker status: `Done`

## Landed summary

ODIN realm detail is available through the authenticated SSE stream, including
initial and changed detail snapshots. The realm browser subscription consumes
`realm.detail` events and updates its cached view; focused backend and browser
verification passed.
