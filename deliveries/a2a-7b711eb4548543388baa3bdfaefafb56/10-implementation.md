# Implementation handoff — NIU-295

## Delivered

Expanded `tests/test_adapters/test_harvester.py` with contract coverage for a failed credential refresh, unresolved create conflicts, unknown profiles, and inventory objects that omit an allocation label. The tests use the existing HTTP API fake and authentication-port doubles; production code is unchanged.

## Verification

Passed:

```text
uv run --extra dev ruff check tests/test_adapters/test_harvester.py
uv run --extra dev pytest -q tests/test_adapters/test_harvester.py --cov=volundr.adapters.outbound.harvester --cov-report=term-missing
```

The focused suite passes `42 passed` with `97%` coverage for `src/volundr/adapters/outbound/harvester.py`.

## Pre-existing environment failures on clean `regin`

The required persona-adapter command was run in a detached clean `regin` worktree both without the workload-token-file variable and with `NIUU_WORKLOAD_IDENTITY_TOKEN_FILE=/tmp/niu-295-workload-token` containing a proof value:

```text
env -u NIUU_WORKLOAD_IDENTITY_TOKEN_FILE uv run --extra dev pytest -q tests/test_ravn/test_personas tests/test_adapters/test_session_personas.py tests/test_adapters/test_local_persona_materialization.py
NIUU_WORKLOAD_IDENTITY_TOKEN_FILE=/tmp/niu-295-workload-token uv run --extra dev pytest -q tests/test_ravn/test_personas tests/test_adapters/test_session_personas.py tests/test_adapters/test_local_persona_materialization.py
```

Raw result for both commands: `17 failed, 86 passed`. Every failure is in `tests/test_ravn/test_personas/test_http.py` and its raw error contains `RESPX: <Request('POST', 'http://volundr.test/api/v1/tokens/workload/exchange')> not mocked!`. The exact failing ids are:

```text
TestLoad::test_load_returns_persona_config
TestLoad::test_load_parses_llm_fields
TestLoad::test_load_parses_consumes_and_fan_in
TestLoad::test_load_parses_produces
TestLoad::test_load_returns_stale_cache_on_500
TestLoad::test_load_returns_stale_cache_on_network_error
TestLoad::test_load_logs_warning_on_5xx
TestPortableSource::test_load_current_portable_returns_raw_document
TestPortableSource::test_load_exact_portable_revision_uses_revision_endpoint
TestPortableSource::test_load_current_portable_does_not_use_stale_fallback_on_server_error
TestCache::test_cache_hit_single_http_request
TestCache::test_cache_expiry_triggers_new_request
TestCache::test_list_names_cache_hit
TestCache::test_list_names_cache_expiry
TestListNames::test_list_names_returns_sorted_names
TestListNames::test_list_names_returns_stale_cache_on_500
TestListNames::test_list_names_returns_stale_cache_on_network_error
```

`src/ravn/adapters/personas/http.py` and `src/niuu/adapters/outbound/http_auth.py` on clean `regin` show the workload-token exchange implementation is present. The failure is pre-existing and environment-specific: this runtime exposes a projected default service-account token, so otherwise unauthenticated HTTP persona tests attempt an exchange endpoint that their `respx` setup does not mock.

The wider affected package also has a clean-`regin` dependency failure:

```text
uv run --extra dev pytest -q tests/test_adapters
ERROR tests/test_adapters/test_user_home_files.py
ModuleNotFoundError: No module named 'kubernetes_asyncio'
```

The same error occurs on the implementation branch; it is not caused by this change.

## Pull request

Pending branch push and PR creation.
