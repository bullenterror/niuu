# NIU-300 implementation investigation

## Verdict: blocked on a missing ODIN realm-detail contract

The requested wiring cannot be implemented without creating the event schema
that the ticket expressly declares out of scope.

Evidence from `regin`:

- `git grep -n -i -E 'realm[_ .-]detail|realm\.detail'` finds no runtime
  realm-detail event type, payload model, catalog factory, producer, or
  consumer. The only hits are delivery documentation from the previous NIU-300
  attempt.
- `src/sleipnir/domain/registry.py` and `src/sleipnir/domain/catalog.py`
  define the ODIN/Sleipnir event taxonomy and typed payload factories. Neither
  defines a realm-detail event or payload schema.
- `src/niuu/adapters/inbound/rest_realms.py` exposes request/response realm
  governance routes only. It has no event publisher, subscriber, or SSE route.
- Existing SSE implementations stream already-defined contracts: Forge uses
  `volundr.domain.services.session_events.SessionEventStream`; Observatory
  streams its topology and event contracts. Neither can carry an undefined
  realm-detail payload without inventing its type, fields, channel, and
  authorization scope.

The prerequisite is an authoritative ODIN realm-detail contract: event type,
payload schema, producer, consumer scope/filtering requirements, and the SSE
endpoint/channel to expose it. Once supplied, this ticket can add the
Sleipnir-to-SSE subscription and a published-event delivery test without
inventing product behavior.

## Verification performed

- Queried tracker ticket `NIU-300`, then moved it to `In Progress`.
- Searched current source, tests, all fetched remote refs, and history for the
  realm-detail event/schema and existing realm SSE subscription wiring.
- Verified the current branch is based on `regin`, not `dev` or `main`.
