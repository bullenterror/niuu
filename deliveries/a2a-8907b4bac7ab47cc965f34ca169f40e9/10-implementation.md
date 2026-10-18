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
