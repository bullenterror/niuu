# NIU-305 — Add rate limiting to public endpoints

- **Tracker:** [NIU-305](https://linear.app/niuu/issue/NIU-305/add-rate-limiting-to-public-endpoints)
- **Delivery slug:** `a2a-24fcd3aa932141139032916ad022ecc4`
- **Required base and delivery branch:** `regin`
- **Tracker status:** `In Progress`

## Scope correction

Yggdrasil has `GET /health` but no `/status` route. The in-memory token bucket
therefore applies only to `GET /health`; this delivery neither creates nor
changes a `/status` endpoint.

## Observable result

Each client IP has a 60-token bucket for `GET /health`, refilled at one token
per second. Requests with a token continue returning the existing 200 body;
requests without one return 429 and a `Retry-After` header.

## Review revisions

The first reviewer follow-up found unbounded per-IP bucket retention on the
public endpoint. That revision bounds retained buckets and removes inactive,
fully refilled buckets.

The current reviewer follow-up found that cleanup scanned every retained bucket
on each request. Cleanup now examines only the least-recently-used bucket and
stops at the first bucket that is not idle and fully refilled, so a normal
unexpired request does not traverse the entire store.
