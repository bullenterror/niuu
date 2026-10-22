# NIU-1138 — Bind durable workflow execution for A2A Research Campaign launches

- **Tracker:** [NIU-1138](https://linear.app/niuu/issue/NIU-1138/research-campaign-a2a-workflow-fails-at-setup-owner-bound-workflow)
- **Delivery slug:** `a2a-0cb4ecb3934b4b0796ab4d12419c3e2d`
- **Required base branch:** `regin`
- **Delivery branch:** `fix/niu-1138-a2a-workflow-context`
- **Tracker status:** `In Progress`

## Reported failure

An A2A `SendMessage` for Research Campaign skill
`1bfc01b1-4d01-5d20-86e1-2956dff11464`, including a connection ID and
repository metadata, reached `TASK_STATE_FAILED` before producing artifacts.
Ravn reported that the coordinator required an owner-bound
`workflow_execution` runtime context.

## Root cause

The A2A task-launch path created an ordinary workflow session. The REST
research-launch path already reserved a durable parent execution and projected
its trusted `workflow_execution` provenance into the Ravn runtime; the A2A
path did not. This is a Ting launch-wiring defect, not a connection or
instance provisioning issue.
