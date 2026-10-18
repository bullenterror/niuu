# NIU-300 implementation investigation

## Verdict: blocked on a missing server contract

`@niuulabs/query` does provide `openEventStream` at
`web-next/packages/query/src/event-stream.ts`, and existing consumers use explicit
stream ports with effect cleanup (for example
`web-next/packages/plugin-observatory/src/application/useTopology.ts`).

The checked-out `regin` source has no realm-detail SSE endpoint or event payload
contract to connect that foundation to:

- `src/niuu/adapters/inbound/rest_realms.py` declares only list/create/get/delete
  realm routes plus trust-grant and capability routes. Its authoritative route
  decorators are at lines 230–342; none produces `text/event-stream`.
- `web-next/packages/plugin-valkyrie/src/ports.ts` defines
  `IRealmGovernanceService` as request/response operations only. It has no realm
  detail stream port, event type, or unsubscribe contract.
- `web-next/packages/plugin-valkyrie/src/adapters/http.ts` maps that service to
  the same REST endpoints and declares no stream URL or event decoding.
- `web-next/packages/plugin-realms/src/application/useRealmView.ts` obtains realm
  detail through `useRealms()` and related queries; it has no subscribed realm
  event source.

The only SSE endpoints found on `regin` are for Observatory topology/events,
Volundr session streams, Ravn signal/warden streams, and Ting events. None is a
realm-detail stream and none documents events that can safely update the Realm
page's joined `RealmView` model.

Adding a client URL, event name, or decoder would invent the absent contract,
which is explicitly prohibited. The specific required server contract is an
authenticated realm-detail SSE route (including its URL, event names, payload
schema, and filtering/authorization semantics) that emits updates sufficient to
refresh the `RealmPage` state. Once it exists, this ticket can add the frontend
stream port, `openEventStream` adapter, a `useEffect` returning unsubscribe, and
the requested live-update/unmount regression test without guessing.

## Delivery status

Evidence was committed as `c1ad6b95` and pushed to
`origin/feat/niu-300-realm-detail-sse`. A hosted PR could not be created because
`gh pr create --base regin` reports that GitHub CLI authentication is unavailable
in this workspace. The intended base remains `regin`; no action targeted `dev` or
`main`.
