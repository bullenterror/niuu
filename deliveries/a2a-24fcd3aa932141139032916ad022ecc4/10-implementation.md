# NIU-305 implementation and verification

## Change

The existing `regin` implementation provides a lock-protected, in-memory
token bucket for Yggdrasil's public `GET /health` endpoint. It keeps the
successful health response unchanged and responds to a depleted bucket with
HTTP 429 plus `Retry-After`.

This delivery repairs the direct route-call regression introduced by adding
the FastAPI request parameter: the lifecycle test now supplies a real request
when invoking the route endpoint directly. This preserves the test's health
payload assertion while exercising the route's client-IP input.

## Verification

- Passed: `uv run pytest -q --no-cov tests/sse/test_poller.py`.
- Passed: `uv run pytest -q --no-cov tests/api/test_health.py tests/api/test_routes_sse.py`.
- Passed: `uv run ruff check src/yggdrasil tests/api/test_health.py tests/api/test_routes_sse.py tests/sse/test_poller.py`.
- Passed: `uv run ruff format --check src/yggdrasil tests/api/test_health.py tests/api/test_routes_sse.py tests/sse/test_poller.py`.
- Passed: `git diff --check`.

## Delivery

The correction is committed and pushed directly to `regin`, as required. This
direct-regin delivery has no hosted PR because GitHub does not allow a pull
request with the same head and base branch.

## Review revision: bounded bucket retention

`TokenBucketRateLimiter` now uses an access-ordered bounded store. Each request
removes buckets that have been idle for the configured TTL and have fully
refilled. When storage is still at capacity, the least-recently-used bucket is
removed before a new client bucket is admitted. This keeps the public endpoint's
in-memory state bounded while retaining the existing 60-token, one-token-per-
second behavior.

Added regression coverage for inactive/full bucket eviction and for maximum
bucket retention.

### Verification

- Passed: `uv run ruff check src/yggdrasil/rate_limit.py tests/api/test_health.py`.
- Passed: `uv run pytest -q --no-cov tests/api/test_health.py tests/api/test_routes_sse.py tests/sse/test_poller.py` (19 passed; one existing TestClient deprecation warning).
- Passed: `git diff --check`.
