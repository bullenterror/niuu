# NIU-1110 implementation verification

## Endpoint contract

`src/ting/api/a2a.py` exposes `POST /api/v1/ting/a2a` through Ting's normal
composition root. `SendMessage` selects and launches a visible workflow,
persists the campaign that is the A2A task, and returns its task view.
`GetTask` rehydrates that campaign into its current A2A state. `CancelTask`
stops the campaign's persisted session and records the A2A cancellation state.
The implementation remains inside Ting's inbound A2A adapter and uses ports for
workflow, campaign, launch-reservation, and Volundr access.

## Added lifecycle proof

`TestSendMessage.test_task_lifecycle_drives_send_get_and_cancel_over_jsonrpc`
launches one workflow through the actual FastAPI A2A route and A2A SDK JSON-RPC
dispatcher, obtains its returned task id, retrieves that same task through
`GetTask`, and cancels it through `CancelTask`. It verifies both the protocol
result and the persisted cancellation marker/session stop. The controlled
Volundr port is the existing test boundary; the route, workflow launch,
campaign persistence semantics, and A2A request handling are production code.

## Verification

- Passed: `uv run --extra otel pytest -q -s tests/test_ting/test_a2a_tasks.py` — **63 passed**.
- Passed: `uv run ruff check src/ting/api/a2a.py tests/test_ting/test_a2a_tasks.py`.
- Passed: `uv run ruff format --check tests/test_ting/test_a2a_tasks.py`.
- Passed: `git diff --check`.
- The focused suite includes the self-contained OTLP evidence path:
  `TestSendMessage.test_a2a_otlp_export_reaches_tempo_and_loki_receivers`
  drove a real `SendMessage` request through the exporter and decoded the
  output. It observed `ting.a2a.SendMessage` with trace id
  `0123456789abcdef0123456789abcdef`, metrics
  `a2a_requests_total` and `a2a_request_duration_seconds`, and the correlated
  A2A completion log at the in-process OTLP collector.

## External-environment check

The already-running service at `127.0.0.1:8080` answered health checks but
returned `404` for both this repository's A2A card and task route, so it is not
a deployment of this workspace revision and cannot provide honest live-service
evidence. No cluster or hosted Ting deployment credentials are available in
this worker. The committed focused proof is therefore the available evidence;
it does not claim a remote deployment test.

## Review revision: production-adapter lifecycle proof

`tests/integration/volundr/test_a2a_workflow_task_lifecycle.py` adds the
non-fixture lifecycle boundary requested in review. It sends all three JSON-RPC
operations through Ting's real A2A router while its production PostgreSQL
workflow, campaign, and launch-reservation adapters persist the workflow task.
The normal `LocalVolundrAdapterFactory` and `VolundrHTTPAdapter` cross a real
loopback HTTP server into Volundr's production session REST router and
PostgreSQL session repository. The assertion confirms that `CancelTask` marked
the campaign `a2a_canceled` and stopped the exact session created by
`SendMessage`; it also captures the three correlated A2A operation logs.

The focused OTLP test in `tests/test_ting/test_a2a_tasks.py` remains the trace,
metric, and log exporter proof for the same endpoint: it records
`ting.a2a.SendMessage` for trace id
`0123456789abcdef0123456789abcdef`, exports
`a2a_requests_total` and `a2a_request_duration_seconds`, and observes the
correlated completion log. Together the two tests cover real adapter lifecycle
persistence/transport and the endpoint's telemetry exporters.

### Revision verification

- Passed: `uv run ruff check tests/integration/volundr/test_a2a_workflow_task_lifecycle.py`.
- Passed: `uv run ruff format --check tests/integration/volundr/test_a2a_workflow_task_lifecycle.py`.
- Passed: `uv run python -m compileall -q tests/integration/volundr/test_a2a_workflow_task_lifecycle.py`.
- Local integration execution was attempted with `uv run --extra otel pytest -q -s -m integration tests/integration/volundr/test_a2a_workflow_task_lifecycle.py --no-cov`, but this worker has no `volundr_test` PostgreSQL role (`InvalidAuthorizationSpecificationError`). The repository's `Forge PostgreSQL boundaries` CI job supplies that disposable role and executes `tests/integration/volundr/`; its result is required before merge.

## Inherited Ravn formatting gate remediation

The required Python formatting gate also evaluated unchanged
`src/ravn/adapters/tool_build/a2a.py`. Before commit `11bbd386`, it was
byte-identical to `origin/regin`; `git show
origin/regin:src/ravn/adapters/tool_build/a2a.py > /tmp/a2a-regin-NIU1110.py`
followed by `uv run ruff format --check --diff /tmp/a2a-regin-NIU1110.py`
reported exactly one deletion: the additional blank line before
`_skill_capability` at line 1242. `11bbd386` is a dedicated
`style(ravn): format A2A adapter` commit containing only that deletion.
`uv run ruff format --check src/ravn/adapters/tool_build/a2a.py` passes after
the change. No gate configuration changed and no other `regin` formatting debt
was remediated.

### CI production-proof receipt

GitHub Actions [Forge PostgreSQL boundaries run 39164904228](https://github.com/niuulabs/niuu/actions/runs/39164904228) passed on commit `8d7323f4`. Its disposable PostgreSQL 16 service executed the production-adapter integration suite, including this lifecycle proof: **84 passed, 42 deselected**. This is the non-fixture database/HTTP task-lifecycle receipt; it follows the earlier focused OTLP receipt above for trace, metric, and correlated log export.
