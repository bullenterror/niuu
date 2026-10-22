# NIU-305 implementation and verification

## Change

Added an in-memory, lock-protected token bucket limiter to Yggdrasil and
wrapped only `GET /health`. Each bucket is keyed by endpoint and client IP,
holds 60 tokens, and refills at one token per second. A depleted bucket returns
HTTP 429 with `Retry-After` set to the time until the next token is available.

Added health endpoint contract tests for ordinary requests, exhaustion with the
response header, IP isolation, and deterministic one-token-per-second refill.

## Verification

- Passed: `uv run ruff check src/yggdrasil/main.py src/yggdrasil/rate_limit.py tests/api/test_health.py`.
- Passed: `uv run pytest tests/api/test_health.py tests/api/test_routes_sse.py -q` — 10 passed.
- Note: the focused pytest run emitted the repository's existing FastAPI/Starlette `TestClient` deprecation warning.

## Delivery

The implementation is committed directly on `regin`, as required. A hosted PR
will be created if the repository host supports it; otherwise this handoff will
record the local-only result.
