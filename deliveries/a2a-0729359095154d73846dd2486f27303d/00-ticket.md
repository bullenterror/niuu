# NIU-300 — Subscribe ODIN realm detail to SSE stream

- Delivery slug: `a2a-0729359095154d73846dd2486f27303d`
- Required base and target: `regin`
- Working branch: `feat/niu-300-realm-detail-sse`, cut from `regin` (`f88bd733`)

## Tracker

The tracker was resolved with the required shim from the repository root:

```sh
./.skuld-tools/bin/tracker_issue search "NIU-300"
./.skuld-tools/bin/tracker_issue get "a8939934-dc0d-4d0e-b89e-6ca5d3089055"
./.skuld-tools/bin/tracker_issue update-status "a8939934-dc0d-4d0e-b89e-6ca5d3089055" "In Progress"
```

NIU-300 is `Subscribe ODIN realm detail to SSE stream`; status is `Done` after merge `24b65ddc` into `regin`.

## Review follow-up

The review recorded at `a66d56e1` requested a hook-level stream lifecycle
regression test and configuration-owned stream timing. Both follow-ups are
implemented directly on `regin`; the tracker remains `Done`.

## Operator-directed scope

The realm-detail SSE surface is the delivery. The implementation defines the
server contract and client adapter rather than treating the surface as a
prerequisite.
