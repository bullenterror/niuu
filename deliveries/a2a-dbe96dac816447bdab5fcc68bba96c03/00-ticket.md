# NIU-298 — SSE endpoint and background polling loop

- Delivery slug: `a2a-dbe96dac816447bdab5fcc68bba96c03`
- Required base and target: `regin`
- Working branch: `feat/niu-298-sse-stream`, cut from `regin`
- Tracker issue: [NIU-298](https://linear.app/niuu/issue/NIU-298/sse-endpoint-and-background-polling-loop)
- Tracker status: `In Progress`
- Review revision: resolving the snapshot race and coverage findings from
  `20-review.md` before requesting re-review.

## Scope

Add `GET /api/v1/yggdrasil/realms/{realm_id}/stream`, an initial
`RealmSummary` SSE snapshot, changed-summary fan-out, and a configurable
background poller. The service is a new self-contained `src/yggdrasil/`
package; adapter implementations are dynamically configured and tests inject
fakes.

## Guardrail search

The bounded case-insensitive search found no Yggdrasil package or existing
`ConnectionManager`. It found NIU-300's separate, authenticated Niuu realm
*detail* stream at `src/niuu/adapters/inbound/rest_realms.py`,
`GET /api/v1/realms/{slug}/stream`. That route streams governance details
(realm, trust grants, and capabilities), not polled health summaries and has
no configured-adapter/connection-manager polling architecture, so it does not
own NIU-298's declared Yggdrasil endpoint.

The operator explicitly confirmed `src/yggdrasil/` is absent and authorized
this greenfield implementation on a feature branch targeting `regin` only.

## Review revision

- Reviewer feedback from `20-review.md` was addressed in commit `2c997d2b` on
  `feat/niu-298-sse-stream`; the existing draft PR remains targeted at `regin`.
