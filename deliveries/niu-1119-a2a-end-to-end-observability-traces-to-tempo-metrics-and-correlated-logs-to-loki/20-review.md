# Review — NIU-1119

## Verdict

needs_changes

## Findings

### Major

- `src/ting/main.py:349-354` configures Python logging with `force=True`. In the mini-mode composition, `niuu.app.create_app` configures the shared OTLP pipeline (and attaches its `LoggingHandler`) before it creates Ting's sub-app. This call removes that handler even when Ting itself has no explicit observability block, so A2A trace and metrics still export but the correlated A2A logs never reach the configured Loki OTLP endpoint. Preserve externally installed handlers when reconfiguring Ting's console logging (or reattach the active OTLP handler afterward), and add a regression test that builds the mini host with observability enabled and verifies that the active OTLP log handler remains attached after Ting is composed.

## Re-check verification

- This is a re-check after the prior configuration request. The two enabled Ravn setup files now provide `observability.log_endpoint`, and `test_enabled_ravn_setup_config_parses` covers parsing every checked-in enabled setup; the prior follow-up is satisfied.
- Reviewed the committed direct-regin delivery range `git diff 4ca7dfab^..a0ce0584`; it targets `regin` only, with no hosted PR and no `dev` or `main` target.
- Reproduced the logging defect with the production helpers: after `configure_observability(...)`, the active OTLP handler is present on the root logger; after `ting.main._configure_logging(Settings())`, it is absent (`before True`, `after False`).
- Focused verification passed: `uv run pytest -q tests/test_ting/test_a2a_tasks.py::TestSendMessage::test_a2a_otlp_export_reaches_tempo_and_loki_receivers tests/test_ravn/test_config.py::test_enabled_ravn_setup_config_parses tests/test_niuu/test_observability_no_fallback.py` — 14 passed. `uv run ruff check src/niuu/observability.py src/ting/main.py src/ravn/cli/runtime_config.py` and `git diff --check 4ca7dfab^..a0ce0584` also passed.

## Recommendation

Retain the OTLP logging handler across Ting console logging setup and cover the mini-mode composition path, then rerun the same-task Tempo/Loki proof and re-request review.
