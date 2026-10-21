# NIU-1108 — A2A: serve agent card for Ting workflows

- Delivery slug: `a2a-20df51666da74d59beda5a3b8d2b9247`
- Required base and target: `regin`
- Working branch: `feat/niu-1108-ting-agent-card`, cut from `regin` (`036895b8`)

## Tracker

The ticket was resolved with the repository tracker shim:

```sh
./.skuld-tools/bin/tracker_issue search "NIU-1108"
./.skuld-tools/bin/tracker_issue get "dcd07451-571b-4c20-876d-e6902c5292d1"
./.skuld-tools/bin/tracker_issue update-status "dcd07451-571b-4c20-876d-e6902c5292d1" "In Progress"
```

NIU-1108 is `A2A: serve agent card for Ting workflows` and was already `In
Progress`. No existing NIU-1108 pull request was found before implementation.

## Scope and failure evidence

The Ting A2A card endpoint and Cedar authorization route already existed on
`regin`, but the production security-values overlay replaced Ting's default JWT
bypass list. Consequently, the deployed `https://yggdrasil.niuu.world/.well-known/agent-card.json`
returned HTTP 401 with `Jwt is missing` on 2026-10-20, preventing the agent
directory from resolving the Ting workflows card for instance
`f59dda91-e8c7-4c67-8751-3ee56d5f3834`.

This delivery makes the discovery document public at the JWT layer while
retaining Cedar's GET/HEAD-only authorization route for the card. It does not
change the authenticated A2A task endpoint or directory UI.
