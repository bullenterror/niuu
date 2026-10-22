# NIU-305 review

## Verdict

**needs_changes**

## Findings

### Major

- `src/yggdrasil/rate_limit.py:70` copies and scans every retained bucket on
  every request while holding the limiter lock. At the new 10,000-bucket cap,
  each public `/health` request performs an O(n) allocation and scan, so a
  multi-IP burst can make the endpoint CPU-bound rather than protected by the
  limiter. Expire only the oldest idle buckets (the access-ordered store makes
  that an O(evictions) operation), or use an expiry-indexed structure, and add
  a regression/performance-oriented test proving a non-expiring request does
  not traverse all retained buckets.

## Verification notes

- Re-checked the committed repo-root branch `regin`, diff `1961ab2c..4338e8ad`.
- The prior bounded-retention request is satisfied: `TokenBucketRateLimiter`
  now has an access-ordered capped store and tests cover full idle-bucket
  eviction and retention at capacity.
- Confirmed only `GET /health` is rate-limited; no `/status` route was added or
  modified.
- Passed: `uv run ruff check src/yggdrasil/rate_limit.py src/yggdrasil/main.py tests/api/test_health.py tests/api/test_routes_sse.py tests/sse/test_poller.py`.
- Passed: `uv run ruff format --check src/yggdrasil/rate_limit.py src/yggdrasil/main.py tests/api/test_health.py tests/api/test_routes_sse.py tests/sse/test_poller.py`.
- Passed: `uv run pytest -q --no-cov tests/api/test_health.py tests/api/test_routes_sse.py tests/sse/test_poller.py` (19 passed; one existing TestClient deprecation warning).
- Passed: `git diff --check 1961ab2c..4338e8ad`.

## Recommendation

Replace the per-request full-store expiry scan with an ordered/expiry-indexed
amortized O(1) cleanup path, add its regression coverage, then rerun the focused
tests before approval.
