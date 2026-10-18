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
