# NIU-1108 review

## Verdict

**pass** — the Ting chart change correctly makes the A2A Agent Card public in
both the base values and the Cedar overlay, while retaining Cedar's exact
GET/HEAD admission rule and leaving the task endpoint authenticated.

## Findings

No blocking, major, minor, or suggestion findings.

## Verification notes

- Reviewed the canonical PR [#1158](https://github.com/niuulabs/niuu/pull/1158)
  (base `regin`) and the live `regin` commits `1ee3a553` and `20edd1aa`.
- Confirmed `charts/ting/values-cedar.yaml` replaces the base bypass list and
  now includes `/.well-known/agent-card.json`.
- Confirmed Envoy's template bypasses JWT validation and disables ext_authz for
  the exact configured public path; the Cedar route configuration separately
  allows only GET and HEAD for that card.
- Passed with Helm v3.17.3: `uv run pytest -q --no-cov
  tests/test_charts/test_cedar_authz.py -k 'ting_gateway_admits_its_a2a_card_and_endpoint or ting_agent_card_bypasses_jwt_validation'`
  (5 passed).
- Passed: `uv run pytest -q --no-cov tests/test_ting/test_a2a_card.py` (9
  passed; one pre-existing Starlette/httpx deprecation warning).
- Passed: `helm lint charts/ting`, `uv run ruff check
  tests/test_charts/test_cedar_authz.py`, and `git diff --check
  036895b8..HEAD`.
- The live endpoint returned HTTP 401 (`Jwt is missing`) during this review,
  consistent with the documented pre-rollout state; deployment and the
  directory `capability_list` acceptance check remain external to this code
  review.

## Recommendation

Merge/roll out the reviewed `regin` change, then run the ticket's live
`capability_list` acceptance check before moving NIU-1108 to Done.
