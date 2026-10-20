# NIU-1108 implementation and verification

## Change

Added `/.well-known/agent-card.json` to Ting's `envoy.jwtBypassPrefixes` in
both `charts/ting/values.yaml` and `charts/ting/values-cedar.yaml`. Helm list
values are replaced rather than merged, so both entries are needed for the
Cedar deployment profile that served the failing instance.

Added a rendered-Envoy regression test that requires the Cedar profile to emit
the Agent Card JWT bypass rule. Existing route tests establish that only GET
and HEAD are admitted for the card, and the Ting card tests establish that the
endpoint returns parseable A2A JSON.

## Verification

- Passed: `PATH="/tmp/niuu-helm-v3.17.3/linux-amd64:$PATH" uv run pytest -q --no-cov tests/test_charts/test_cedar_authz.py -k 'ting_gateway_admits_its_a2a_card_and_endpoint or ting_agent_card_bypasses_jwt_validation'` — 5 passed.
- Passed: `uv run pytest -q --no-cov tests/test_ting/test_a2a_card.py` — 9 passed; one existing Starlette/httpx deprecation warning was emitted.
- Passed: `PATH="/tmp/niuu-helm-v3.17.3/linux-amd64:$PATH" helm lint charts/ting` — 0 failures.
- Passed: `uv run ruff check tests/test_charts/test_cedar_authz.py` and `git diff --check HEAD^ HEAD`.

## Delivery

The chart fix is committed directly on `regin`, as required. An existing PR
for the equivalent chart patch targets `regin`:
https://github.com/niuulabs/niuu/pull/1158. No separate hosted PR was created
for this direct-regin delivery. The tracker stays `In Progress` until rollout
and the live `capability_list` acceptance check complete.
