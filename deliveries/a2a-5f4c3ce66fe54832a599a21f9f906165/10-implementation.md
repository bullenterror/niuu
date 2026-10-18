# NIU-300 implementation verification

## Landed implementation

`GET /api/v1/realms/{slug}/stream` is an authenticated `text/event-stream`
route. It emits an initial complete `realm.detail` snapshot containing the
realm, trust grants, and capabilities; emits replacement snapshots after a
persisted detail change; and emits keepalive comments while unchanged.

The router is composed in both Volundr and the shared host using the validated,
chart-configured `realm_detail_stream_interval_seconds` setting. The browser
adapter consumes named `realm.detail` frames via authenticated
`openEventStream`, and the realm view updates its React Query caches and closes
the stream during cleanup.

## Verification

- Passed: `uv run ruff check tests/test_niuu/test_rest_realms.py src/niuu/adapters/inbound/rest_realms.py src/volundr/config.py src/volundr/main.py src/cli/shared_host.py`.
- Passed: `uv run pytest -q tests/test_niuu/test_rest_realms.py tests/test_volundr/test_resident_runtime_config.py` — 30 passed.
- Passed: `corepack pnpm --filter @niuulabs/plugin-realms typecheck`.
- Passed: `corepack pnpm exec vitest run packages/plugin-realms/src/application/useRealmView.test.tsx packages/plugin-valkyrie/src/adapters/http.test.ts --coverage.enabled=false` — 23 passed.
- Passed: the [PR #1147 check rollup](https://github.com/niuulabs/niuu/pull/1147) is complete and successful, including `ci-gate`.

## Hosted delivery

The implementation was merged through [PR #1147](https://github.com/niuulabs/niuu/pull/1147). This pass records fresh verification only; no additional PR is
needed because the target branch already contains the implementation.

## Review revision

`test_realm_detail_stream_emits_changed_snapshot` now consumes the initial
`realm.detail` frame, records a capability in the same in-memory realm, then
asserts the next frame is a second named `realm.detail` snapshot containing the
new capability. This exercises the changed-state branch without timing sleeps.

Focused verification passed:

- `uv run ruff check tests/test_niuu/test_rest_realms.py src/niuu/adapters/inbound/rest_realms.py`
- `uv run pytest -q tests/test_niuu/test_rest_realms.py` — 25 passed.

The canonical implementation PR remains [PR #1147](https://github.com/niuulabs/niuu/pull/1147), which is merged into `regin`. This review-only regression-test commit is being delivered directly on the configured `regin` branch; no separate hosted PR is created.
