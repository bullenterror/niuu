# Implementation — NIU-1146

## Change

Added `mimir_publish_artifact`, a JSON-only publisher for `capabilities/*.json` that writes to the durable capabilities store and verifies an exact read-back in the same call. The Tool & Skill Builder's `capability-publisher` persona now has that tool instead of `mimir_write`; its pinned workflow dependency and version were advanced. CLI sessions receive an equivalent `mimir_publish_artifact` shim.

The gbrain Mímir adapter now preserves a requested JSON path on direct artifact reads, so A2A's configured `learned_tool.json` artifact keeps its JSON identity after publication.

## Verification

- `uv run pytest -q tests/ravn/unit/test_mimir.py tests/test_ravn/test_gbrain_mimir_adapter.py tests/test_ravn/test_persona_contracts.py tests/test_skuld/test_tool_shims.py tests/test_ting/test_system_workflows.py`
- Direct CLI proof: `ravn.cli.mimir_bridge publish-artifact capabilities/build-widget/learned_tool.json --content-file learned_tool.json`, followed by `read`, published and returned the exact JSON.

The pre-existing `test_mimir_write_tool_non_md_extension` was retained unchanged and passed.

## Handoff

No hosted PR is applicable: the required source and target branch is `regin`, and the fix is committed directly on that integration branch.
