# NIU-1110 — A2A task endpoint over workflow launch

- Delivery slug: `a2a-8907b4bac7ab47cc965f34ca169f40e9`
- Tracker: [NIU-1110](https://linear.app/niuu/issue/NIU-1110/a2a-task-endpoint-over-workflow-launch-sendmessagegettaskcanceltask)
- Status at verification start: `In Progress`
- Required base and merge target: `regin`
- Working branch: `feat/niu-1110-a2a-workflow-task-endpoint`, cut from `regin` at `a85cf1d9`

## Tracker and branch checks

The ticket was resolved and retained in `In Progress` using the required tracker
shim. Remote branch and hosted-PR searches found no existing NIU-1110 branch or
PR to complete. This pass targets `regin` only; no instruction to target `dev`
or `main` was found or followed.

## Landed implementation

The requested endpoint was already present on the `regin` base through
`c1253e9d` (`feat(ravn): deliver the resident judgment and evolution loop`),
which explicitly records NIU-1110. It mounts Ting's A2A v1 JSON-RPC endpoint at
`POST /api/v1/ting/a2a` and implements `SendMessage`, `GetTask`, and
`CancelTask` over workflow campaigns. This delivery adds a one-task lifecycle
regression proof rather than duplicating the landed implementation.

## Review revision — production-adapter lifecycle proof

The `review.changes_requested` finding is addressed by
`tests/integration/volundr/test_a2a_workflow_task_lifecycle.py`. It uses
Ting's PostgreSQL workflow, campaign, and A2A-reservation repositories plus
`LocalVolundrAdapterFactory`/`VolundrHTTPAdapter` against a real loopback
Volundr REST server and its PostgreSQL session repository. The test creates an
isolated workflow and drives `SendMessage`, `GetTask`, and `CancelTask` on its
returned task id, then verifies the persisted cancellation marker and stopped
Forge session. The target remains `regin` only.

## Inherited Ravn formatting debt (operator-approved scope hold)

Before the formatting commit, `src/ravn/adapters/tool_build/a2a.py` was
byte-identical to clean `origin/regin` (`git diff --exit-code origin/regin --
src/ravn/adapters/tool_build/a2a.py`); NIU-1110 did not otherwise modify this
file. The exact inherited-debt proof was:

```console
git show origin/regin:src/ravn/adapters/tool_build/a2a.py > /tmp/a2a-regin-NIU1110.py
uv run ruff format --check --diff /tmp/a2a-regin-NIU1110.py
```

Ruff reported only removal of the extra blank line before
`_skill_capability` (line 1242). Commit `11bbd386` (`style(ravn): format A2A
adapter`) contains that exact one-line deletion and no other file. The
post-change verification was:

```console
uv run ruff format --check src/ravn/adapters/tool_build/a2a.py
```

This is the single inherited `regin` format defect blocking PR #1150; no
broader repository formatting was performed. PR #1150 remains targeted only
at `regin`.

The non-fixture proof passed in GitHub Actions Forge PostgreSQL boundaries run
[39164904228](https://github.com/niuulabs/niuu/actions/runs/39164904228) on
commit `8d7323f4` (**84 passed, 42 deselected**). The PR remains
https://github.com/niuulabs/niuu/pull/1150 with base `regin`.
