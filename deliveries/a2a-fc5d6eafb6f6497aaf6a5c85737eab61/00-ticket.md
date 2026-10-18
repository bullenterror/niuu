# NIU-300 — Subscribe ODIN realm detail to SSE stream

- Delivery slug: `a2a-fc5d6eafb6f6497aaf6a5c85737eab61`
- Required base and target: `regin`
- Verification branch: `feat/niu-300-realm-detail-sse`, cut from current `regin`

## Tracker

The tracker was resolved through the repository shim:

```sh
./.skuld-tools/bin/tracker_issue search "NIU-300"
./.skuld-tools/bin/tracker_issue get "a8939934-dc0d-4d0e-b89e-6ca5d3089055"
./.skuld-tools/bin/tracker_issue update-status "a8939934-dc0d-4d0e-b89e-6ca5d3089055" "In Progress"
```

NIU-300 is `Subscribe ODIN realm detail to SSE stream`.

## Delivery state

The requested implementation was already landed on `regin`: PR [#1145](https://github.com/niuulabs/niuu/pull/1145), merge commit `24b65ddc71c58a677e28a5ddae0c585fc3a45cb1`. Its implementation commit `cbecf1fc598ca91f00c0ff630d6b3b2291a077ec` is an ancestor of the verified `regin` head. This delivery therefore adds no duplicate source implementation.
