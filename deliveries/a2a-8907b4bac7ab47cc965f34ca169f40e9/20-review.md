# NIU-1110 review

## Verdict

**needs_changes** — the focused JSON-RPC regression is useful, and the
format-only Ravn edit is correct, but the ticket's required non-fixture
end-to-end proof is still absent.

## Findings

### Major

- **`tests/test_ting/test_a2a_tasks.py:742`** — The only new lifecycle proof
  constructs its route with `InMemoryWorkflowRepository`,
  `InMemoryCampaignRepository`, `InMemoryA2ALaunchRepository`, and the
  `RecordingVolundrPort` supplied by `_make_client`. It therefore never
  launches or stops a real A2A-backed runtime task, nor verifies the persisted
  state through the production repository adapters. This does not satisfy the
  ticket's explicit requirement that one *real* A2A task exercise
  `SendMessage`, `GetTask`, and `CancelTask`, rather than a fixture-only path.
  Fix: add and run an integration/deployment proof against the production
  Ting/Volundr adapters (with an isolated real workflow and session), invoke
  all three JSON-RPC methods on the returned task ID, and commit the resulting
  trace/metric/log evidence in the delivery record.

## Verification

- Confirmed the feature branch is based on `origin/regin` (`a85cf1d9`) and PR
  #1150 targets `regin`, not `dev` or `main`.
- Reviewed the complete branch diff: delivery records, the lifecycle regression
  in `tests/test_ting/test_a2a_tasks.py`, and one blank-line format correction
  in `src/ravn/adapters/tool_build/a2a.py`.
- Passed: `uv run --extra otel pytest -q -s tests/test_ting/test_a2a_tasks.py`
  — 63 passed. The run reported one existing Starlette/httpx deprecation
  warning from `fastapi.testclient`, not a failure introduced by this diff.
- Passed: `uv run ruff check src/ting/api/a2a.py tests/test_ting/test_a2a_tasks.py src/ravn/adapters/tool_build/a2a.py`.
- Passed: `uv run ruff format --check tests/test_ting/test_a2a_tasks.py src/ravn/adapters/tool_build/a2a.py`.
- Passed: `git diff --check origin/regin..HEAD`.
- At review time, the new head had no completed PR checks; the earlier CI run
  `39163945454` was associated with the preceding head and was still in
  progress before this review record was pushed.

## Recommendation

Do not merge. Supply the required real end-to-end A2A lifecycle evidence, then
rerun the focused checks and wait for green PR CI. The only permitted merge
target remains `regin`; never merge to `dev` or `main`.
