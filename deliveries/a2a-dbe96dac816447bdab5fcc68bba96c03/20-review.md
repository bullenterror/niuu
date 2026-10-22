# NIU-298 review

## Verdict

`needs_changes`

## Findings

### Major — initial snapshot can be duplicated as a change event

**`src/yggdrasil/stream.py:34`** reads the initial snapshot only after the route
has already registered the queue (`routes_sse.py:29`). If a poll completes in
that window, it queues the new summary; the generator then reads and emits that
same new summary as its initial frame and immediately emits the queued copy.
This violates the requirement that subsequent events are emitted only when the
summary changes from the client's previous event. Capture the snapshot before
registering the queue, pass that captured snapshot into the generator, and add
a regression test that polls an update between connection registration and the
first generator iteration; it must receive the old initial snapshot followed
by the changed update exactly once.

### Major — the required Yggdrasil coverage gate fails

**`src/yggdrasil/main.py:35`** and the rest of the new package are added to
coverage in `pyproject.toml`, but the required package gate currently reports
**75.47%**, below the mandated 85%. The focused tests pass only with coverage
disabled. Add tests for the uncovered lifespan/start-stop and stream/manager
branches, then run and record `uv run --extra dev pytest -q --cov=src/yggdrasil
--cov-branch --cov-fail-under=85 tests/api/test_routes_sse.py tests/sse` (or the
project's equivalent Yggdrasil gate) until it passes.

## Verification notes

- Reviewed the committed `regin..HEAD` diff on
  `feat/niu-298-sse-stream` (`bad2b30d`), which is the source branch of PR
  #1162 targeting `regin`.
- Reproduced the snapshot race with a connected queue and a poll before the
  generator's first iteration: it emitted the identical `degraded` summary
  twice.
- `uv run --extra dev pytest -q --cov=src/yggdrasil --cov-branch
  --cov-fail-under=85 tests/api/test_routes_sse.py tests/sse`: 5 tests passed,
  but coverage failed at 75.47% (required 85%).
- `uv run --extra dev pytest -q` could not complete collection because this
  checkout lacks `kubernetes_asyncio`, needed by the pre-existing
  `tests/test_adapters/test_user_home_files.py`.

## Recommendation

Do not merge PR #1162 yet. Fix both major findings, add the targeted regression
coverage, and request re-review.
