# NIU-300 review

## Verdict: needs changes

### Major

- `tests/test_niuu/test_rest_realms.py:356` only exercises the initial snapshot
  and the unchanged-state keepalive. It never changes a realm, grant, or
  capability after the first frame and therefore never reaches the changed-state
  branch in `rest_realms.py:239-241`, which is the behavior promised by the
  ticket. Add a deterministic regression test that consumes the initial frame,
  mutates the in-memory realm detail, consumes the next frame, and asserts a
  second `realm.detail` frame contains the mutation (rather than a keepalive).

## Verification

- Reviewed the canonical merged PR #1147 (`feat/niu-300-realm-detail-sse` into
  `regin`, merge `85447e63`) and the landed follow-up `de6622da` from the
  repository root. The current checkout is `regin` at `53047d28`; its direct
  `regin..HEAD` diff is empty because the implementation is already merged.
- Inspected the actual feature diff from the recorded feature base `f88bd733`
  through current `HEAD`, including the server stream, composition wiring,
  browser adapter, hook lifecycle, and tests.
- Passed: focused Ruff, `pytest` (30 passed), realm plugin typecheck, and the
  two focused Vitest suites (23 passed). The initial root-level Vitest command
  could not resolve workspace package exports; rerunning from `web-next/`, the
  package-manager workspace root, passed.
- Confirmed PR #1147 is merged into `regin` and its required `ci-gate` and
  associated check rollup are successful.

## Recommendation

Request the bounded server-side changed-detail regression test above, then
re-review. No security or runtime correctness defect was identified in the
implemented path.
