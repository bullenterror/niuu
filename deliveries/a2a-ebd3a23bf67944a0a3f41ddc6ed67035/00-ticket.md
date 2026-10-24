# NIU-1145 — Supersede blocked A2A publish outcomes

- Tracker: [NIU-1145](https://linear.app/niuu/issue/NIU-1145/platform-defect-build-tool-a2a-task-stuck-input-required-after)
- Status at implementation start: In Progress
- Delivery slug: `a2a-ebd3a23bf67944a0a3f41ddc6ed67035`
- Integration branch: `regin`

## Acceptance criteria

- A Tool & Skill Builder publish that first emits a blocked help-needed event and later emits its configured successful terminal event completes the campaign.
- `GetTask` returns `TASK_STATE_COMPLETED` and exposes `capabilities/{slug}/learned_tool.json`.
- The returned learned-tool artifact installs and its registered tool executes.
