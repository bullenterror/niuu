# NIU-1110 closure record

- **Tracker identifier:** NIU-1110
- **Merged branch:** `feat/niu-1110-a2a-workflow-task-endpoint`
- **Target branch:** `regin`
- **Merge commit:** `dbb0ccf2a30b7aa69b4c2a2c8a040a5ff5c00b16`
- **Hosted review:** PR [#1150](https://github.com/niuulabs/niuu/pull/1150), merged into `regin` at 2026-10-18T20:54:50Z
- **Final tracker status:** `Done` (confirmed with the generic `tracker_issue` shim)

## Landed summary

The delivery exposes the Ting workflow-launch A2A task endpoint for
`SendMessage`, `GetTask`, and `CancelTask`, and adds a real lifecycle proof
that drives one task through Ting's JSON-RPC route, PostgreSQL workflow and
campaign repositories, the loopback `VolundrHTTPAdapter`, and Volundr's
PostgreSQL-backed session router.  The proof verifies the persisted
`a2a_canceled` marker and stops the exact session created by `SendMessage`.
The related endpoint telemetry proof captures the A2A trace, metrics, and
correlated completion log.

## Verification evidence

- Focused endpoint suite: `uv run --extra otel pytest -q -s
  tests/test_ting/test_a2a_tasks.py` — **63 passed** (one existing
  FastAPI/TestClient deprecation warning).
- Format/lint and whitespace checks recorded in the reviewed delivery passed.
- GitHub Actions Forge PostgreSQL boundaries run
  [39164904228](https://github.com/niuulabs/niuu/actions/runs/39164904228)
  passed the production-adapter integration suite: **84 passed, 42
  deselected**.
- PR #1150 is merged and `origin/regin` points at the merge commit above.

## Post-merge CI exception

The pull-request CI run [39165451494](https://github.com/niuulabs/niuu/actions/runs/39165451494)
reported a failed **Python / Python: Test Ravn** check after the merge. It has
four failures in Ravn resident-learning tests, including
`ResidentLearningDecision` lacking `status`. This delivery changed no Ravn
learning code or Ravn tests: the only Ravn diff is the one-line inherited
format correction in `src/ravn/adapters/tool_build/a2a.py`; the complete
feature diff otherwise contains Ting tests and delivery records. The failure
is outside NIU-1110's A2A endpoint blast radius, but this means the required
all-green post-merge CI condition cannot be claimed from this run. No
unrelated Ravn change was made to mask it.
