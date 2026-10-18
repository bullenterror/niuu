# Review — NIU-1119

## Verdict

needs_changes

## Findings

### Major

- `scripts/setups/configs/eitri-local-valkyrie.yaml:208` and `scripts/setups/configs/ivaldi-local-workshop.yaml:209` enable observability but still omit the required `observability.log_endpoint`. `ObservabilityConfig` now requires trace, metric, and log endpoints whenever observability is enabled, so both checked-in resident setup configurations fail validation before their runtime can start. Add each setup's OTLP/HTTP Loki collector `/v1/logs` endpoint and add a regression test that parses every checked-in enabled Ravn setup configuration.

## Re-check verification

- This is a re-check of the prior review request. The prior request to remove duplicate public `ravn_tool_build_*` emissions remains satisfied: `src/ravn/adapters/tool_build/a2a.py` emits only backend-local diagnostics and `src/ravn/adapters/tools/build_tool.py` owns the public lifecycle count/duration pair.
- The prior requested configuration follow-up is **not** satisfied. At `regin` commit `b693eaa2`, neither setup file changed from the delivery base, and `RAVN_CONFIG=<each setup file> uv run python -c 'from ravn.config import Settings; Settings()'` reproducibly raises `Value error, observability requires trace_endpoint, metric_endpoint, and log_endpoint when enabled` for both files.
- Reviewed the committed delivery diff `git diff 4ca7dfab^..b693eaa2` on `regin`; `origin/regin` matched the pre-review HEAD. The direct integration does not target `dev` or `main`.
- Focused verification passed: `PATH="$PWD/.local/bin:$PATH" uv run pytest -q -s tests/test_ting/test_a2a_tasks.py::TestSendMessage::test_a2a_otlp_export_reaches_tempo_and_loki_receivers tests/test_ravn/test_config.py::TestObservabilityConfig tests/test_ting/test_config.py::TestSettings::test_observability_requires_trace_metric_and_log_endpoints tests/test_skuld/test_config.py::TestSkuldSettings::test_observability_partial_env_keeps_skuld_service_name` — 6 passed. The OTLP proof observed `ting.a2a.SendMessage` at the local Tempo receiver and correlated `a2a_requests_total`, `a2a_request_duration_seconds`, and log data at the local Loki receiver.
- Targeted `uv run ruff check` over the changed observability source passed, as did `git diff --check 4ca7dfab^..b693eaa2`.
- Tracker NIU-1119 remains `In Review`.

## Recommendation

Add the two missing endpoint values and a parse regression test, rerun the focused observability suite, then re-request review.
