# Implementation — NIU-1141

## Change

Added a `Delivery blocked` human-approval gate to Tracker Delivery Flow. The new
`code.blocked -> code.blocked` edge expands the implementation node's allowed
outcomes, preventing the Ravn outcome-rejection path from treating a valid
blocked coder result as an error. The gate uses `help_needed`, which marks the
workflow campaign blocked and sends the commissioner the outcome summary.

Skuld now appends a structured outcome `rationale` or `reason` to a gate summary
when it is not already present, preserving the coder's stated reason in the
commissioner-visible help request.

## Verification

- `uv run --extra dev pytest -q tests/test_ting/test_system_workflows.py tests/test_skuld/test_broker.py -k 'routing_only_peer_outcome_can_activate_native_workflow_gate or load_system_workflows_only_keeps_supported_catalog'`
- `uv run --extra dev ruff check src/skuld/broker.py tests/test_skuld/test_broker.py tests/test_ting/test_system_workflows.py`

## Handoff

No hosted PR was created: the required source and target branch is `regin`, so this checkout lands directly on `regin` rather than opening an invalid self-targeted PR.
