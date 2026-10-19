# NIU-1110 closure record

- **Tracker identifier:** `NIU-1110`
- **Merged branch:** `feat/niu-1110-a2a-workflow-task-endpoint`
- **Target branch:** `regin`
- **Merge commit:** `dbb0ccf2a30b7aa69b4c2a2c8a040a5ff5c00b16`
- **Hosted review:** PR [#1150](https://github.com/niuulabs/niuu/pull/1150), merged into `regin`
- **Final tracker status:** `Done` (reconfirmed through `./.skuld-tools/bin/tracker_issue update-status "NIU-1110" "Done"`)

## Landed summary

NIU-1110 delivers Ting's A2A workflow-launch task lifecycle: `SendMessage`,
`GetTask`, and `CancelTask`. The real task proof drives one JSON-RPC task through
Ting's route, PostgreSQL workflow/campaign repositories, the loopback
`VolundrHTTPAdapter`, and Volundr's PostgreSQL-backed session router; it verifies
the persisted `a2a_canceled` marker and stops the created session. The bundled,
operator-authorized one-line Ruff correction makes
`src/ravn/adapters/tool_build/a2a.py` format-clean. The merge target was `regin`
only; no `dev` or `main` action occurred.

## Verified evidence

- Merge `dbb0ccf2` is present on and was already pushed to `origin/regin`; PR #1150
  targeted `regin`.
- Post-review local gate: `uv run ruff check src/ravn/adapters/tool_build/a2a.py
  tests/test_ting/test_a2a_tasks.py tests/integration/volundr/test_a2a_workflow_task_lifecycle.py`
  — **All checks passed**.
- Post-review local format gate: `uv run ruff format --check` on those three files
  — **3 files already formatted**.
- Focused task proof: `uv run --extra otel pytest -q -s tests/test_ting/test_a2a_tasks.py`
  — **63 passed**. It includes the `SendMessage`/`GetTask`/`CancelTask` lifecycle
  and emits the correlated A2A trace, metrics, and completion log.
- The committed Forge PostgreSQL boundaries CI receipt, run
  [39164904228](https://github.com/niuulabs/niuu/actions/runs/39164904228), passed
  the non-fixture lifecycle boundary: **84 passed, 42 deselected**.
- `git diff --check dbb0ccf2..HEAD` passed. No coverage or lint gate was lowered.

## Explicitly ruled-out pre-existing failures

The known approximately 265 repository-wide `regin` test-environment failures
are not part of NIU-1110 and were not altered: missing `kubernetes_asyncio` and
persona exchange-mock failures (documented at
`technical/niuu/delivery/regin-preexisting-test-env-breakage.md`). The local
PostgreSQL integration invocation is additionally unavailable without the
`volundr_test` role (`InvalidAuthorizationSpecificationError`); the successful
CI PostgreSQL receipt above supplies that role. These environment failures do
not change the focused/lint evidence and are not represented as full-repository
CI success.
