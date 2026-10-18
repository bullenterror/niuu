# NIU-300 implementation

## Realm-detail SSE contract

`GET /api/v1/realms/{slug}/stream` is authenticated by the realm router's
existing principal dependency. It produces `text/event-stream`, emits an
initial state snapshot, then emits a replacement snapshot whenever the stored
realm detail changes. Idle connections receive SSE comments.

Each update is a named `realm.detail` event with this payload:

```json
{
  "realm": { "id": "...", "slug": "...", "name": "..." },
  "trust_grants": [{ "id": "...", "realm_id": "...", "action_class": "..." }],
  "capabilities": [{ "id": "...", "realm_id": "...", "name": "..." }]
}
```

The three objects use the same snake_case fields and JSON timestamp encoding as
the existing realm, trust-grant, and capability REST responses. A complete
snapshot makes reconnect and client cache replacement deterministic.

## Client integration

`IRealmGovernanceService.subscribeRealmDetail` opens the authenticated stream
through `openEventStream`, accepts only `realm.detail` frames, and returns an
unsubscribe function that closes the underlying connection. `useRealmView`
subscribes once its realm is loaded, replaces its realm and trust-grant React
Query cache entries on each event, and returns that unsubscribe function from
its effect cleanup.

## Verification

- `uv run pytest -q tests/test_niuu/test_rest_realms.py`
- `corepack pnpm --filter @niuulabs/plugin-valkyrie typecheck`
- `corepack pnpm --filter @niuulabs/plugin-realms typecheck`
- `corepack pnpm exec vitest run apps/niuu/src/services.test.ts packages/plugin-valkyrie/src/adapters/http.test.ts --coverage.enabled=false`

Hosted PR creation is unavailable because `gh` is not authenticated. The
finished feature branch is merged and pushed directly to `regin` as requested.

## Review follow-up

`useRealmView` now keys its subscription lifecycle on realm presence rather
than the current realm object. A hook regression test delivers a
`realm.detail` snapshot, verifies both cache entries, and verifies exactly one
unsubscribe on unmount. The stream interval is now validated in
`volundr.config.Settings`, passed through both host composition roots, and
rendered by the Volundr chart.

Verification for this revision:

- `uv run --extra dev pytest -q tests/test_niuu/test_rest_realms.py tests/test_volundr/test_resident_runtime_config.py`
- `uv run --extra dev ruff check src/niuu/adapters/inbound/rest_realms.py src/volundr/config.py src/volundr/main.py src/cli/shared_host.py tests/test_niuu/test_rest_realms.py tests/test_volundr/test_resident_runtime_config.py`
- `web-next/node_modules/.bin/vitest run packages/plugin-realms/src/application/useRealmView.test.tsx packages/plugin-valkyrie/src/adapters/http.test.ts --coverage.enabled=false`
- `web-next/node_modules/.bin/tsc -p web-next/packages/plugin-realms/tsconfig.json --noEmit`
