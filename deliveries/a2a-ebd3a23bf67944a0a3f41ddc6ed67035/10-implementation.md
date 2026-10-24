# Implementation — NIU-1145

## Change

Workflow campaign projection now treats an authoritative configured workflow-terminal outcome as completion even when it has no optional review-attested `delivery` envelope. The envelope remains required before Ting persists a trusted delivery result; if an envelope is present but invalid it still fails closed. This permits a successful Tool & Skill Builder publish to supersede an earlier help-needed `BLOCKED` campaign and therefore maps the A2A task to `COMPLETED`.

## Verification

- `uv run --extra dev ruff check src/ting/domain/services/workflow_campaign_projector.py tests/test_ting/test_workflow_campaign_projector.py tests/test_ting/test_a2a_tasks.py`
- `uv run --extra dev --extra otel pytest -q tests/test_ting/test_workflow_campaign_projector.py tests/test_ting/test_a2a_tasks.py`

The regression test records the blocked publisher gate, applies the later authoritative `capability.ready` outcome, fetches the completed A2A task and artifact, then installs and invokes the returned learned tool.

## Handoff

No hosted PR is applicable: the required source and target branch is `regin`, and the fix is committed directly on that integration branch.
