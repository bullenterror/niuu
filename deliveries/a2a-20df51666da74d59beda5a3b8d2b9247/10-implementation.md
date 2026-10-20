# NIU-1108 implementation

## Change

Added `/.well-known/agent-card.json` to Ting's JWT bypass list in both the
default chart values and the `values-cedar.yaml` secure overlay. The latter is
required because Helm replaces lists rather than merging them, and it is the
secure overlay that produced the observed 401. The endpoint remains protected
by Ting's Cedar route table, which admits only GET and HEAD.

Added a rendered-Envoy regression test proving that the secure Cedar profile
emits the agent-card JWT bypass rule. The existing card endpoint test suite
continues to prove the endpoint returns parseable A2A JSON containing skills,
interfaces, and the bearer security scheme.

## Verification

- Passed `PATH="/tmp/linux-amd64:$PATH" uv run pytest -q tests/test_charts/test_cedar_authz.py -k 'ting_gateway_admits_its_a2a_card_and_endpoint or ting_agent_card_bypasses_jwt_validation'` (5 passed).
- Passed `uv run pytest -q tests/test_ting/test_a2a_card.py` (9 passed; it emits one pre-existing Starlette/httpx deprecation warning).
- Passed `PATH="/tmp/linux-amd64:$PATH" /tmp/linux-amd64/helm lint charts/ting`.
- Passed `uv run ruff check tests/test_charts/test_cedar_authz.py` and `git diff --check`.

The live card and the corresponding agent-directory warning require deployment
of this chart change; they cannot be rechecked against the currently deployed
release before the PR is merged and rolled out.

## Handoff

Pull request: https://github.com/niuulabs/niuu/pull/1158 (base: `regin`).
The tracker remains `In Progress`; it must not be marked Done until this PR is
merged, CI is green, the chart rollout completes, and the live directory check
confirms that the `f59dda91-e8c7-4c67-8751-3ee56d5f3834` warning is gone.
