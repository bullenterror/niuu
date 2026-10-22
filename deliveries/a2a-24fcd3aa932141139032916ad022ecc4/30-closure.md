# NIU-305 closure

- **Tracker:** NIU-305
- **Merged branch:** `regin`
- **Target branch:** `regin`
- **Merge commit SHA:** `c9131771420f0e0e8a40783166d01d8fe8a990a4` (direct `regin` integration; no separate merge commit)
- **Final tracker status:** Done

## Landed

`GET /health` now uses a bounded, in-memory, per-client-IP token-bucket rate
limiter with a capacity of 60 and a one-token-per-second refill rate. Requests
within the limit retain the existing 200 response and body; excess requests
receive HTTP 429 with `Retry-After`. No `/status` route was added or modified.

The direct `regin` integration was verified with focused lint, format, diff,
and 20 endpoint and lifecycle tests before the branch was confirmed pushed.
