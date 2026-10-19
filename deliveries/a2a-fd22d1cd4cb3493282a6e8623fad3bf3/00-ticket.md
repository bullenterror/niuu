# NIU-1113 — A2A: Ravn client backend for tool builds

- **Tracker:** [NIU-1113](https://linear.app/niuu/issue/NIU-1113/a2a-ravn-client-backend-for-tool-builds)
- **Delivery branch and target:** `regin` only (direct integration; no `dev` or `main` action)
- **Tracker status at revision start:** `In Progress`

## Observable result and acceptance check

A configured Ravn can commission a learned-tool build through a remote A2A
agent: it reads that agent's card, resolves the explicit workflow id or a
name/tag selector, sends the tool brief through `SendMessage`, follows the
same task with `GetTask`, and returns the canonical `learned_tool.json` from
an inline or URL artifact. It uses the existing workload-identity HTTP client,
not a second credential scheme; failures, pending tasks, and input requests
remain explicit.

The acceptance check is a concrete `A2AToolBuildBackend` talking to Ting's
actual card and JSON-RPC adapters over loopback HTTP, with Ting's PostgreSQL
workflow/campaign/reservation adapters and its normal Volundr HTTP launch
adapter persisting the task and its session. Unit coverage separately verifies
the terminal canonical-artifact contract.

## Existing implementation and revision scope

The implementation was already present on the `regin` ancestry in
`c1253e9d` (`feat(ravn): deliver the resident judgment and evolution loop`),
whose commit body explicitly records NIU-1113. It introduced
`ravn.adapters.tool_build.a2a.A2AToolBuildBackend` and the corresponding
port/configuration/test coverage. This revision does not duplicate that
implementation. It adds a regin-native production-adapter proof that the
concrete Ravn client actually commissions a persisted A2A workflow task,
addressing the review finding that no NIU-1113 evidence was committed in the
review range.

## Branch and environment checks

No existing NIU-1113 feature branch or PR was found after fetching remotes and
searching all branch names/logs. The repository has no hosted service for this
workspace revision: no local Ting or Volundr A2A deployment is running, and
no cluster credential was supplied. The proof is therefore a self-contained
production-adapter integration test, not a claim about an external deployment.
