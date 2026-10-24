# NIU-1138 closure

- **Tracker identifier:** `NIU-1138`
- **Merged branch:** `fix/niu-1138-a2a-workflow-context`
- **Target branch:** `regin`
- **Merge commit:** `e630e004ff53c3b939889c07d0bdc11e951bb98b`
- **Final tracker status:** `Done`

## Landed

Merged PR #1165 into `regin`. A2A Research Campaign launches now reserve the
owner-bound durable `workflow_execution` context, preserve the active trace
carrier, attach the launched session to its durable parent, and record the
execution on the campaign. Regression coverage proves the valid A2A launch
reaches `TASK_STATE_SUBMITTED` rather than failing during setup.
