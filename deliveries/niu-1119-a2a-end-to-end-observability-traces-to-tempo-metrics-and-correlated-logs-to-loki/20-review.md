# Review — NIU-1119

## Verdict

needs_changes

## Findings

### Major

- `scripts/setups/configs/eitri-local-valkyrie.yaml:208` and `scripts/setups/configs/ivaldi-local-workshop.yaml:209` enable observability but do not provide the newly required `observability.log_endpoint`. The changed `ObservabilityConfig` now rejects any enabled configuration without it, so both documented local resident setup configurations fail during `ravn.config.Settings()` validation before the runtime can start. Add the appropriate OTLP/HTTP Loki collector `/v1/logs` endpoint to both configurations and add a regression test that parses every checked-in enabled Ravn setup configuration.

## Re-check verification

- This is a re-check of the prior review request, not a first pass. The prior request to remove duplicate public `ravn_tool_build_*` emissions is satisfied: `src/ravn/adapters/tool_build/a2a.py` now emits only the backend-local `ravn.tool_build.operations`, while `src/ravn/adapters/tools/build_tool.py` is the single owner of the public count/duration pair. The lifecycle regression test passes.
- Confirmed the live review ref is `regin` at `052c3b21` and reviewed `git diff 196f7129..HEAD`; `origin/regin` matches HEAD. The delivery contains no target branch or PR to `dev` or `main`.
- Reproduced the configuration failure directly with `RAVN_CONFIG=<each setup file> uv run python -c 'from ravn.config import Settings; Settings()'`; each raises `Value error, observability requires trace_endpoint, metric_endpoint, and log_endpoint when enabled`.
- `PATH="$PWD/.local/bin:$PATH" uv run pytest -q -s tests/test_ting/test_a2a_tasks.py tests/test_niuu/test_observability_no_fallback.py tests/test_ravn/test_observability.py tests/test_ravn/test_tool_build_backends.py tests/test_ravn/test_build_tool_verify.py tests/test_ravn/test_config.py tests/test_ting/test_config.py tests/test_charts/test_ting_chart.py tests/test_adapters/test_contributors/test_ravn_flock.py -k 'observability or a2a_otlp_export or commissioned_build_public_metrics'` passed: 30 passed, 452 deselected. Its real in-process OTLP proof observed the same A2A task trace in Tempo, the two metrics, and a trace-correlated log in the Loki receiver.
- Targeted `uv run ruff check` over all changed source and relevant test files passed, as did `git diff --check`.
- Tracker NIU-1119 remains `In Review`.

## Recommendation

Add the two missing `log_endpoint` values and a configuration-parse regression test, then rerun the focused observability suite and re-request review.
