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
