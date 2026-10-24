# NIU-1141 — Tracker Delivery Flow blocks are rejected

- Tracker: [NIU-1141](https://linear.app/niuu/issue/NIU-1141/platform-defect-tracker-delivery-flow-delivery-implement-node-rejects)
- Status at implementation start: In Progress
- Delivery slug: `a2a-2ebc7a3ea77d476fb7588533c586cd60`

## Acceptance criteria

- The `delivery-implement` node accepts `code.blocked`.
- A blocked implementation reaches the commissioner with the coder's stated reason.
- A nonexistent-endpoint delivery is blocked rather than rejected with `outcome_rejected`.
