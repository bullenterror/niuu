# NIU-298 re-review

## Verdict

`needs_changes`

## Findings

### Major — startup polls every adapter twice without waiting for the configured interval

**`src/yggdrasil/main.py:46-47`** performs an immediate startup poll and then
starts the background task. **`src/yggdrasil/sse/poller.py:67-69`** makes that
task call `poll_once()` before its first `sleep()`, so every adapter is called
twice back-to-back at startup rather than once per `poll_interval`. This can
violate the configured polling rate and unnecessarily hit health adapters.
Since the lifespan already obtains the snapshot needed for an immediate first
SSE event, make the recurring loop sleep for `poll_interval` before its next
poll (or otherwise avoid one of the two startup polls) and add a regression
test proving no second call occurs before the interval elapses.

## Verification notes

- Re-checked the merged PR [#1162](https://github.com/niuulabs/niuu/pull/1162)
  against `regin` at merge commit `bad34ddb`; it correctly targets `regin`.
- The prior requests are satisfied: `routes_sse.py:24-25` captures the summary
  before registration, `stream.py:31` emits that captured value, and
  `test_routes_sse.py:108-127` covers exactly one queued update after it.
- The focused gate passes: `uv run --extra dev pytest -q
  --cov=src/yggdrasil --cov-branch --cov-fail-under=85 tests/api/test_routes_sse.py
  tests/sse` — 12 passed, 97.58%.
- `uv run ruff check src/yggdrasil tests/api/test_routes_sse.py tests/sse`
  passes. The full suite remains blocked during collection by the pre-existing
  missing `kubernetes_asyncio` dependency imported by
  `tests/test_adapters/test_user_home_files.py`.

## Recommendation

Follow up on the merged change: remove the duplicate startup poll, add the
cadence regression test, and re-run the focused gate plus the full suite when
the environment dependency is available.
