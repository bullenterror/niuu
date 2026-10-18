# NIU-1135 — Document Regin ticket readiness and operator delivery handoff

- Delivery slug: `task-niu-1135-document-regin-ticket-readiness-and-operator-delivery-handoff-documentation-only-c`
- Required base and target: `regin`
- Working branch: `docs/niu-1135-regin-handoff`, cut from `regin` (`436d45d3`)

## Tracker

The tracker was resolved with the required shim from the repository root:

```sh
./.skuld-tools/bin/tracker_issue search "NIU-1135"
./.skuld-tools/bin/tracker_issue get "1a39d235-604b-43c6-a8cb-30f65177046a"
./.skuld-tools/bin/tracker_issue update-status "1a39d235-604b-43c6-a8cb-30f65177046a" "In Progress"
```

NIU-1135 is `Document Regin ticket readiness and operator delivery handoff` and
was `In Progress` when the delivery began.

## Scope

This is a documentation-only change. It creates one operator documentation page
covering Regin's definition of ready, the routing for tickets that are not ready,
and the operator delivery handoff. No production code, behavior, schema,
migration, CI, or deployment configuration is in scope.

The required target is `regin`. No merge, push, or pull request may target
`dev` or `main`; promotion from `regin` to `dev` remains the operator's explicit
action outside this delivery.
