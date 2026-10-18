# NIU-300 implementation verification

## Landed contract

`GET /api/v1/realms/{slug}/stream` is an authenticated SSE route in `src/niuu/adapters/inbound/rest_realms.py`. It emits full `realm.detail` snapshots containing `realm`, `trust_grants`, and `capabilities`, and sends SSE keepalive comments while unchanged. The router is composed in both `src/volundr/main.py` and `src/cli/shared_host.py` with a validated, chart-configured polling interval.

`web-next/packages/plugin-valkyrie/src/adapters/http.ts` uses `@niuulabs/query`'s authenticated `openEventStream` for the route and closes its handle in the returned unsubscribe function. `web-next/packages/plugin-realms/src/application/useRealmView.ts` follows the topology lifecycle pattern: its effect subscribes after the realm is available, updates the React Query realm and trust-grant caches for every snapshot, and returns the unsubscribe function for unmount cleanup.

## Focused verification

- Passed: `uv run ruff check tests/test_niuu/test_rest_realms.py src/niuu/adapters/inbound/rest_realms.py src/volundr/config.py src/volundr/main.py src/cli/shared_host.py`
- Passed: `uv run pytest -q tests/test_niuu/test_rest_realms.py tests/test_volundr/test_resident_runtime_config.py` — 30 passed.
- Passed: `corepack pnpm --filter @niuulabs/plugin-realms typecheck`.
- Passed: `corepack pnpm exec vitest run packages/plugin-realms/src/application/useRealmView.test.tsx --coverage.enabled=false` — live snapshot delivery and exactly-once unmount disposal.
- Passed: `corepack pnpm exec vitest run packages/plugin-valkyrie/src/adapters/http.test.ts --coverage.enabled=false` — 22 passed, including authenticated event forwarding and unsubscribe closure.

## Hosted delivery

The implementation was merged into `regin` through [PR #1145](https://github.com/niuulabs/niuu/pull/1145). No new PR is required because this signal was received after that landing, and the current verification branch has no source delta from `regin`.
