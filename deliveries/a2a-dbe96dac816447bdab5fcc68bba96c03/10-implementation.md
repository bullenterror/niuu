# NIU-298 implementation

## Delivered behavior

- `src/yggdrasil/` provides a standalone FastAPI service with
  `GET /api/v1/yggdrasil/realms/{realm_id}/stream`.
- `ConnectionManager` enforces the configured global client limit, returns a
  503 before accepting an over-limit client, and removes each subscription in
  the stream generator's `finally` path.
- Every accepted stream starts with a named `realm.summary` SSE frame for the
  current `RealmSummary`; the poller broadcasts only changed health status or
  metrics.
- `RealmPoller` polls each configured adapter at `poll_interval` seconds
  (default 15, configurable with `YGGDRASIL_POLL_INTERVAL`) and logs a
  warning while continuing when one adapter fails.
- Adapter classes are dynamically loaded from `YGGDRASIL_ADAPTERS`; test
  adapters are explicit fakes and no external integration was added.

## Guardrail search result

**Findings, not a clean repository:** NIU-300 serves the existing Niuu
realm-detail stream from `src/niuu/adapters/inbound/rest_realms.py` at
`GET /api/v1/realms/{slug}/stream`. It is not an SSE hub for health-summary
adapters and does not own the separately declared Yggdrasil API. No
case-insensitive repository hit identified an existing Yggdrasil package or
`ConnectionManager`.

## Verification

- Passed: `uv run ruff check src/yggdrasil tests/api/test_routes_sse.py tests/sse`
- Passed: `uv run pytest -q --no-cov tests/api/test_routes_sse.py tests/sse` —
  `5 passed in 0.08s`

The focused tests prove SSE framing and the immediate snapshot, the 503 client
limit path, cleanup after a stream closes, changed-summary-only fan-out,
`YGGDRASIL_POLL_INTERVAL`, and warning-level adapter-failure isolation.

## Hosted delivery

Draft PR [#1162](https://github.com/niuulabs/niuu/pull/1162) targets `regin`
from `feat/niu-298-sse-stream`.

## Review revision

- Captured the initial `RealmSummary` before registering the SSE subscription,
  then pass that immutable snapshot to the stream generator. A poll occurring
  after registration and before the first generator iteration is now delivered
  once as the subsequent changed event rather than duplicating the initial
  frame.
- Added focused lifecycle, adapter-loading, connection-limit/cleanup, idle
  disconnect, and race-regression coverage. The configured idle disconnect
  check interval now also flows through `YggdrasilSettings` instead of being a
  hard-coded runtime timing value.

## Review revision verification

- Passed: `uv run ruff check src/yggdrasil tests/api/test_routes_sse.py tests/sse`
- Passed: `uv run --extra dev pytest -q --cov=src/yggdrasil --cov-branch --cov-fail-under=85 tests/api/test_routes_sse.py tests/sse` — `12 passed`, `97.58%` coverage.
- Full suite attempted: `uv run --extra dev pytest -q` is blocked at collection
  by the pre-existing missing `kubernetes_asyncio` dependency required by
  `tests/test_adapters/test_user_home_files.py`.
