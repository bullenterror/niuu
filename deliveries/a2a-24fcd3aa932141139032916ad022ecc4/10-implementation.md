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
