# Review — NIU-1146

## Verdict

**pass**

## Findings

No blocking findings.

## Verification notes

- Reviewed committed `regin` change `0b77561a..1f56e84d` from the repository root; `HEAD` and `origin/regin` both resolve to `1f56e84d`.
- Confirmed the capability-publisher persona no longer permits `mimir_write`; it publishes `capabilities/{slug}/learned_tool.json` through `mimir_publish_artifact` and retains a durable read-back check.
- Confirmed the new publisher validates a JSON object, restricts output to `capabilities/*.json`, writes through the configured Mimir port, and verifies exact read-back. The GBrain adapter preserves the requested `.json` artifact path for this verification.
- Confirmed `MimirWriteTool` still rejects non-Markdown paths (`path must end with .md`); its existing rejection test remains unchanged.
- Passed: `uv run --extra dev ruff check src/ravn/adapters/mimir/gbrain.py src/ravn/adapters/tools/mimir_tools.py src/ravn/cli/mimir_bridge.py src/skuld/transports/tool_shims.py tests/ravn/unit/test_mimir.py tests/test_ravn/test_gbrain_mimir_adapter.py tests/test_ravn/test_persona_contracts.py tests/test_skuld/test_tool_shims.py`.
- Passed: `uv run --extra dev pytest -q tests/ravn/unit/test_mimir.py tests/test_ravn/test_gbrain_mimir_adapter.py tests/test_ravn/test_persona_contracts.py tests/test_skuld/test_tool_shims.py tests/test_ting/test_system_workflows.py` (237 passed).

## Recommendation

Approve the change. Learned-tool JSON now takes the JSON-capable artifact path in one publish step while Markdown-only `mimir_write` behavior is preserved.
