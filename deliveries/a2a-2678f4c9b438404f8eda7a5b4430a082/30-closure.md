# Closure — NIU-1146

- **Tracker identifier:** NIU-1146
- **Merged branch:** `regin` (direct integration; no hosted PR/MR)
- **Target branch:** `regin`
- **Merge commit SHA:** `1f56e84d7024d7afc83cfc6d9757c8597a7087cb`
- **Final tracker status:** Done

## Operator summary

The Tool & Skill Builder now publishes `learned_tool.json` through the JSON-capable durable artifact publisher with exact read-back verification, avoiding the prior `mimir_write` rejection-and-retry path. The Markdown-only `mimir_write` `.md` contract remains unchanged and its rejection coverage passed review.
