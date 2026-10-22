# NIU-298 — SSE endpoint and background polling loop

- Delivery slug: `a2a-dbe96dac816447bdab5fcc68bba96c03`
- Required base and target: `regin`
- Working branch: `feat/niu-298-sse-stream`, cut from `regin`

## Tracker

The ticket was resolved through the repository tracker shim:

```sh
./.skuld-tools/bin/tracker_issue search "NIU-298"
./.skuld-tools/bin/tracker_issue get "e24f8682-787d-449f-ba91-7483d2e0756d"
```

NIU-298 is `SSE endpoint and background polling loop` and is already `In Progress`.

## Blocking mismatch

The ticket's declared implementation package does not exist on `regin` or in
any local or remote branch: there is no `src/yggdrasil/`, `tests/api/`, or
`tests/sse/` tree, and `git log --all -- src/yggdrasil tests/api/test_routes_sse.py
tests/sse` has no commits. The requested route
`/api/v1/yggdrasil/realms/{realm_id}/stream` therefore has no package,
composition root, domain models, ports, or adapters into which it can be
implemented without inventing an unscoped service.
