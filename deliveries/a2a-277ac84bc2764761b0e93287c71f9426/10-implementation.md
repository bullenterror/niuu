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

The implementation is committed and pushed directly on `regin`, as required.
GitHub hosts the repository, but no separate PR can be created because the
required delivery and merge-target branch are both `regin`; GitHub does not
permit a pull request whose head and base are the same branch.
