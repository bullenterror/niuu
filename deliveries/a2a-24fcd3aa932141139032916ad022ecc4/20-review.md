# NIU-305 review

## Verdict

**needs_changes**

## Findings

### Major

- `src/yggdrasil/rate_limit.py:36` stores a token bucket for every endpoint/IP
  tuple indefinitely, including buckets that have refilled completely.  Because
  this is a public route and client IPs can be made arbitrarily numerous, an
  attacker can grow `_buckets` without bound and exhaust process memory.  Add a
  bounded/expiring bucket store (for example, evict fully refilled buckets after
  a configured idle TTL and cap retained entries) and a regression test that
  verifies inactive buckets are removed or retention is bounded.

## Verification notes

- Reviewed the committed repo-root branch `regin`, diff `1961ab2c..b4c902cc`.
- Confirmed the prior direct-route invocation finding is satisfied in
  `tests/sse/test_poller.py`: it supplies a request to `health.endpoint`.
- Confirmed the implementation modifies only `GET /health`; it does not add or
  change `/status` or other routes.
- Passed: `uv run pytest -q --no-cov tests/api/test_health.py tests/api/test_routes_sse.py tests/sse/test_poller.py` (17 passed; one existing TestClient deprecation warning).
- Passed: Ruff check and format check for the changed Yggdrasil source and
  focused test files; `git diff --check 1961ab2c..HEAD` passed.

## Recommendation

Address the unbounded bucket-retention issue before approval, then re-run the
focused tests.
