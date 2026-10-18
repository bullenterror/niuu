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
- **Live sink evidence:** Not available from this worker. `kubectl` is not installed and no cluster/Tempo/Loki endpoint or workload credentials are configured, so an actual deployed A2A task and sink query could not be run. This is an acceptance-evidence gap, not a claim of live delivery.
- **CI evidence:** This repository's `.github/workflows/ci.yaml` triggers only for pull requests, while delivery is required to land directly on `regin`; no CI workflow is configured for a `regin` push. Local focused verification is recorded above, but green CI for the merged SHA cannot be asserted.
