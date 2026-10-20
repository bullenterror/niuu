# NIU-1108 closure — Serve Ting workflow Agent Card

- **Tracker:** `NIU-1108` (`dcd07451-571b-4c20-876d-e6902c5292d1`)
- **Merged branch:** `feat/niu-1108-ting-agent-card`
- **Target branch:** `regin`
- **Merge commit:** `adca772ee0a2cf4293c9959a72bafbb0c5d5847d`
- **Final tracker status:** `Done`

## Landed summary

Ting's Agent Card discovery path is now exempt from JWT validation in both the
base chart values and the Cedar overlay, while Cedar continues to limit card
access to GET and HEAD. This lets unauthenticated A2A directory clients resolve
the card without making Ting's authenticated task endpoint public.
