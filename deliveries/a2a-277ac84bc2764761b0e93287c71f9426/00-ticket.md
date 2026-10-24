# NIU-305 — Add rate limiting to public endpoints

- **Tracker:** [NIU-305](https://linear.app/niuu/issue/NIU-305/add-rate-limiting-to-public-endpoints)
- **Delivery slug:** `a2a-277ac84bc2764761b0e93287c71f9426`
- **Required base and delivery branch:** `regin`
- **Tracker status:** `In Progress`

## Scope correction

The tracker description names `/health` and `/status`, but Yggdrasil exposes
only `GET /health`. This delivery intentionally applies the limit only to that
existing route and does not create a `/status` route.

## Observable result

A client may make 60 requests per minute to `GET /health` from one IP address.
The next request returns HTTP 429 with a `Retry-After` header. Buckets are
in-memory, isolated by endpoint and client IP, and refill at one token per
second.
