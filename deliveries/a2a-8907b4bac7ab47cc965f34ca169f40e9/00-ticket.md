# NIU-1110 — A2A task endpoint over workflow launch

- Delivery slug: `a2a-8907b4bac7ab47cc965f34ca169f40e9`
- Tracker: [NIU-1110](https://linear.app/niuu/issue/NIU-1110/a2a-task-endpoint-over-workflow-launch-sendmessagegettaskcanceltask)
- Status at verification start: `In Progress`
- Required base and merge target: `regin`
- Working branch: `feat/niu-1110-a2a-workflow-task-endpoint`, cut from `regin` at `a85cf1d9`

## Tracker and branch checks

The ticket was resolved and retained in `In Progress` using the required tracker
shim. Remote branch and hosted-PR searches found no existing NIU-1110 branch or
PR to complete. This pass targets `regin` only; no instruction to target `dev`
or `main` was found or followed.

## Landed implementation

The requested endpoint was already present on the `regin` base through
`c1253e9d` (`feat(ravn): deliver the resident judgment and evolution loop`),
which explicitly records NIU-1110. It mounts Ting's A2A v1 JSON-RPC endpoint at
`POST /api/v1/ting/a2a` and implements `SendMessage`, `GetTask`, and
`CancelTask` over workflow campaigns. This delivery adds a one-task lifecycle
regression proof rather than duplicating the landed implementation.

## Review revision — production-adapter lifecycle proof

The `review.changes_requested` finding is addressed by
`tests/integration/volundr/test_a2a_workflow_task_lifecycle.py`. It uses
Ting's PostgreSQL workflow, campaign, and A2A-reservation repositories plus
`LocalVolundrAdapterFactory`/`VolundrHTTPAdapter` against a real loopback
Volundr REST server and its PostgreSQL session repository. The test creates an
isolated workflow and drives `SendMessage`, `GetTask`, and `CancelTask` on its
returned task id, then verifies the persisted cancellation marker and stopped
Forge session. The target remains `regin` only.
