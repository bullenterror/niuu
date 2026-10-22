# NIU-305 review

## Verdict

**needs_changes**

## Findings

### Major

- `src/yggdrasil/main.py:69` changes the decorated health route from a
  zero-argument callable to one that requires `request`.  The existing
  lifecycle test obtains the route endpoint and invokes it directly, so the
  required request now raises `TypeError` instead of returning the health
  payload.  Update the affected existing test to invoke the endpoint with a
  request (or preserve the callable contract while obtaining the client IP),
  then run the Yggdrasil test group so the regression is covered.

## Verification notes

- Reviewed the committed repo-root diff `1961ab2c..019f46e3` on branch `regin`.
- Confirmed only `GET /health` is rate-limited; no `/status` route was added.
- Passed: `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`.
- Passed: `uv run pytest tests/api/test_health.py tests/api/test_routes_sse.py -q` (10 tests).
- Failed: `uv run pytest tests/sse/test_poller.py -q` —
  `test_application_lifespan_starts_and_stops_the_poller` fails because
  `health.endpoint()` lacks the newly required `request` argument.
- The full backend command completed with unrelated environment/suite failures
  (272 failures, including missing `helm`), so it is not clean verification.

## Recommendation

Request the bounded regression fix above before approval.
