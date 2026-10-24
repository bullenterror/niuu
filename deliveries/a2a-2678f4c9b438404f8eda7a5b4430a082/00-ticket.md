# NIU-1146 — Publish learned-tool JSON through the artifact publisher

- Tracker: [NIU-1146](https://linear.app/niuu/issue/NIU-1146/platform-defect-tool-and-skill-builder-publishes-learned-tooljson-via)
- Status at implementation start: In Progress
- Delivery slug: `a2a-2678f4c9b438404f8eda7a5b4430a082`
- Integration branch: `regin`

## Acceptance criteria

- The Tool & Skill Builder publisher sends `capabilities/{slug}/learned_tool.json` through a JSON-capable durable artifact publisher on its first attempt, not `mimir_write`.
- Publication verifies the exact durable content, and the artifact remains addressable as `.json` through gbrain-backed Mímir reads.
- `mimir_write` retains its Markdown-only `.md` rejection contract.
