# NIU-1108 — A2A: serve agent card for Ting workflows

- **Tracker:** [NIU-1108](https://linear.app/niuu/issue/NIU-1108/a2a-serve-agent-card-for-ting-workflows)
- **Delivery slug:** `a2a-06813409d965492eaaaed00f6f830a0a`
- **Required base and delivery branch:** `regin`
- **Tracker status:** `In Progress`

## Observable result

Ting's public `/.well-known/agent-card.json` is exempt from the Envoy JWT
requirement in both the default Ting chart values and the Cedar values overlay.
The Cedar route table remains responsible for limiting the discovery document
to GET and HEAD. This allows an unauthenticated A2A directory client to resolve
the card before it has a platform credential, while the A2A task endpoint
remains authenticated.

The reported failure was an HTTP 401 (`Jwt is missing`) from the Cedar overlay,
whose complete `jwtBypassPrefixes` list replaced the default list and omitted
the Agent Card path. That made the directory report `agent-card-unavailable`
for instance `f59dda91-e8c7-4c67-8751-3ee56d5f3834`.

## Acceptance check

After the Ting chart is deployed, call `capability_list` with any query and
confirm there is no `agent_directory_warning` error with
`source_instance_id` `f59dda91-e8c7-4c67-8751-3ee56d5f3834`. Deployment access
is not available in this workspace, so this delivery proves the rendered chart
configuration rather than claiming the live directory has already refreshed.
