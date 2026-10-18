# Implementation — NIU-1119

## Change

Added config-gated OpenTelemetry support for Ting and completed the A2A observability path:

- Ravn A2A tool-build commissions now use a `tool_build` root span with Valkyrie/environment/workflow/connection/tool attributes, explicit SendMessage span coverage, W3C propagation, and exact `ravn_tool_build_*` metrics.
- Ting A2A JSON-RPC requests now extract W3C trace headers, create per-method spans, attach task/workflow ids, and emit A2A request/state/terminal-duration metrics.
- Shared observability now injects active `trace_id`/`span_id` fields into Python log records when OTel is enabled, and Ravn/Ting log formats render them.
- Ting Settings, Helm values/configmap, and example YAML now expose top-level OTel settings; Ravn examples document the existing settings path.
- Learned-tool install paths and the drive-loop queue now emit the requested exact metrics.

## Verification

- `python -m compileall -q` over modified source and tests.
- `ruff check` over modified source and tests using a temporary local test venv.
- `pytest -q tests/test_ravn/test_observability.py tests/test_ravn/test_tool_build_backends.py tests/test_ting/test_a2a_tasks.py tests/test_ting/test_config.py tests/test_charts/test_ting_chart.py` passed: 134 passed, 1 pre-existing Starlette/httpx deprecation warning.

## Delivery

- **Branch:** `feat/niu-1119-a2a-observability`
- **Base:** `origin/dev`
- **Hosted PR:** Not created; the GitHub connector returned 403 `Resource not accessible by integration`. The branch is pushed and GitHub advertised https://github.com/niuulabs/niuu/pull/new/feat/niu-1119-a2a-observability for a human or authorized bot to open the PR.

## Revision — duplicate public tool-build metrics

- Removed public `ravn_tool_build_total` and `ravn_tool_build_duration_seconds` emission from the A2A backend so the lifecycle `BuildTool` wrapper is the single public metric owner for commissioned builds.
- Kept backend-local `ravn.tool_build.operations` diagnostic counts, including the pending outcome.
- Classified pending build-tool results explicitly so lifecycle metrics record `outcome=pending` instead of defaulting to completed.

## Revision verification

- `python -m compileall -q src/ravn/adapters/tool_build/a2a.py src/ravn/adapters/tools/build_tool.py tests/test_ravn/test_observability.py tests/test_ravn/test_tool_build_backends.py tests/test_ravn/test_build_tool_verify.py` passed.
- `git diff --check` passed.
- Focused pytest and ruff were attempted but unavailable in this runtime (`No module named pytest`, `No module named ruff`; `uv` is not installed).

## Regin delivery pass

- **Integration:** The pre-existing feature branch was based on `origin/dev`, which violates the delivery branch rule. Its implementation and review fix were cherry-picked onto `regin` only (`4ca7dfab`, `c48d939c`, `41010b70`); no PR was created because the resulting work is directly integrated into `regin`.
- **Conflict resolution:** Preserved current `regin` launch-reservation, campaign cleanup, shared-pipeline observability, and chart configuration changes while adding the A2A JSON-RPC span/metrics, campaign state metrics, trace-correlated Ting logs, and the reviewed single-owner public tool-build metrics.
- **Focused verification (local):** `uv run pytest -q tests/test_ravn/test_observability.py tests/test_ravn/test_tool_build_backends.py tests/test_ravn/test_build_tool_verify.py tests/test_ting/test_a2a_tasks.py tests/test_ting/test_config.py tests/test_charts/test_ting_chart.py` passed: **193 passed, 32 skipped** (one pre-existing Starlette/httpx deprecation warning). `uv run ruff check` over all changed source/tests and `git diff --check` passed.
- **Trace/metric/log path evidence:** The focused A2A test runs a `SendMessage` task with one `traceparent` and proves Ting creates the corresponding `ting.a2a.SendMessage` span plus `a2a_requests_total` and `a2a_request_duration_seconds`; `test_commissioned_build_public_metrics_are_recorded_by_lifecycle_once` proves the same A2A build produces exactly one public `ravn_tool_build_*` count/duration pair, owned by the lifecycle wrapper. Trace-log correlation is covered by `tests/test_ravn/test_observability.py`.
- **Live sink evidence:** Superseded by the operator-authorized, self-contained OTLP exporter proof below; no `kubectl`, cluster, external sink endpoint, or sink credential is required.
- **CI evidence:** This repository's `.github/workflows/ci.yaml` triggers only for pull requests, while delivery is required to land directly on `regin`; no CI workflow is configured for a `regin` push. Local focused verification is recorded above, but green CI for the merged SHA cannot be asserted.
- **Published branch:** `origin/regin` contains the integration through `9d13c26b` (the delivery record commit). GitHub reports no workflow runs for `regin`, consistent with the PR-only CI trigger. The tracker remains `In Progress` pending the unavailable live sink/CI evidence; it has not been marked Done.
- **Mímir publication:** attempted through the configured Mímir query capability, but its backend returned an internal error and no Mímir write capability is available in this worker. The repository delivery record is the durable handoff available here.

## Equivalent local OTLP exporter proof

- Added required `observability.log_endpoint` configuration and a real OTLP/HTTP log exporter. Python log records are emitted through the configured collector and retain the active OTel trace/span context. The Ravn-flock session contributor propagates this endpoint to both Ravn and Skuld runtime configuration.
- `TestSendMessage.test_a2a_otlp_export_reaches_tempo_and_loki_receivers` starts an in-process OTLP/gRPC Tempo receiver and an in-process queryable OTLP/HTTP Loki-collector receiver, then drives a real Ting `SendMessage` A2A request with a W3C `traceparent`.
- The test asserts decoded protobuf payloads from the real exporters: Tempo receives `ting.a2a.SendMessage` on trace `0123456789abcdef0123456789abcdef`; the receiver query finds `a2a_requests_total` and `a2a_request_duration_seconds`; and the A2A completion log reaches the log endpoint with that trace id and a non-empty span id.
- Reproducible evidence command: `uv run pytest -q -s tests/test_ting/test_a2a_tasks.py::TestSendMessage::test_a2a_otlp_export_reaches_tempo_and_loki_receivers`. Its output is: `OTLP exporter proof: Tempo query span=ting.a2a.SendMessage trace_id=0123456789abcdef0123456789abcdef; Loki receiver query metrics=a2a_requests_total,a2a_request_duration_seconds; logs=A2A JSON-RPC SendMessage finished with correlated trace_id.`
- Focused verification passed: `PATH="$PWD/.local/bin:$PATH" uv run pytest -q -s ... -k 'observability or a2a_otlp_export'` reported **30 passed, 138 deselected**. `uv run ruff check src/ tests/` and changed-file formatting checks passed.
- Full-suite attempt: `PATH="$PWD/.local/bin:$PATH" uv run pytest -q` completed in 23m33s with **26,796 passed, 88 failed, 46 skipped, 230 deselected, 1 xfailed**. The failures are outside the changed observability path (for example, missing testserver workload-token exchange endpoints, unavailable Docker, a chart namespace assertion, and existing resident-learning/persona failures); this delivery does not claim the full suite is green.
- The equivalent-proof implementation is committed and pushed directly to `origin/regin` as `596255cf` (`feat(niuu): export correlated logs over otlp`). There is no hosted PR because the required delivery path is direct integration to `regin`; tracker status remains `In Progress` until an operator decides how to resolve the unrelated full-suite failures.

## Operator disposition

- The operator approved the focused OTLP exporter proof and authorized moving NIU-1119 to `In Review`; the tracker status is now `In Review`.
- The full-suite result remains **26,796 passed, 88 failed, 46 skipped, 230 deselected, 1 xfailed**. Per operator direction, the 88 failures are outside this change's blast radius and must be tracked as pre-existing issues separately rather than blocking this ticket.
- **Branch target confirmation:** the approved delivery is direct integration on `regin`, and `origin/regin` was confirmed at `f2f94756` before this handoff update. There is no hosted PR for this direct-regin delivery; no PR targets `dev` or `main`. If a hosted review artifact is required later, its target must be `regin`.

## Review revision — enabled setup configuration

- Added the OTLP/HTTP Loki `/v1/logs` endpoint to both enabled resident setup configurations: Eitri uses `https://loki.proxy.glitnir.alfheim.niuu.world/eitri/otlp/v1/logs`, and Ivaldi uses the same tenant collector endpoint.
- Added `test_enabled_ravn_setup_config_parses`, which discovers every checked-in `scripts/setups/configs/*.yaml` file with `observability.enabled: true` and validates it through the production `Settings` YAML source.
- Verification: the regression test and `TestObservabilityConfig` passed (5 passed); direct `RAVN_CONFIG=<setup> uv run python -c 'from ravn.config import Settings; Settings()'` validation passed for both setups; the focused observability suite passed (**30 passed, 454 deselected**) and again emitted the same-task Tempo trace, Loki metrics, and correlated Loki log evidence.
- This direct-regin revision is committed and pushed to `origin/regin` as
  `00f3d92c` (`fix(ravn): configure Loki logs for local residents`). There is
  no hosted PR, and no `dev` or `main` branch is targeted.
