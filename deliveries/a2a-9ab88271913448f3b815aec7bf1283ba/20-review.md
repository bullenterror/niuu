# NIU-1132 review

## Verdict

**needs_changes**

## Findings

### Major — native records are emitted after their telemetry span closes

`src/ravn/agent.py:593` and `src/ravn/agent.py:670` call the new emitter only
after `_call_llm_streaming()` has returned. That method's span is scoped to
`src/ravn/agent.py:1407-1479`, while `emit_harness_step()` attaches an event to
the *current* span (`src/ravn/harness_telemetry.py:13`). A native turn without
an ambient parent span therefore drops `ravn.harness.step` instead of exporting
it. The CLI path emits inside its span, so the cross-harness test's recording
fake masks this runtime difference. Keep a step span active through the native
record emission (including tool timing), or otherwise emit using the provider
span context, and add an SDK-backed regression test proving both harnesses
export an event with no ambient parent span.

### Major — the canonical record is hidden behind optional content capture

`src/ravn/harness_telemetry.py:13-16` passes the record as `content`, but
`niuu.observability.Observability.event()` only exports content when
`capture_content` is enabled (`src/niuu/observability.py:243-247`), which is
false by default. The attributes built in
`src/ravn/domain/harness_telemetry.py:63-102` omit prompt-section estimates and
cache/write/thinking usage, so a default production observability surface
cannot show the promised canonical context composition and full usage record.
Export every content-safe canonical field as bounded event attributes (or add a
safe always-exported structured record path through the existing port), while
continuing to exclude prompts, tool inputs, outputs, and model text. Add a
regression test with `capture_content=False`.

## Verification notes

- Reviewed committed implementation `e34c930f` on `regin` against its parent;
  `regin..HEAD` is empty because this is direct-to-`regin` delivery.
- Passed: `uv run pytest -q tests/test_ravn/test_executor_cli.py tests/test_ravn/test_harness_telemetry.py` (40 passed, 1 skipped).
- Passed: `uv run ruff check src/ravn/agent.py src/ravn/adapters/executors/cli.py src/ravn/domain/harness_telemetry.py src/ravn/harness_telemetry.py tests/test_ravn/test_harness_telemetry.py`.
- SDK-backed direct verification could not run because `opentelemetry.sdk` is not installed in this checkout; the span/content behavior is established by the checked-in `Observability.event` implementation.

## Recommendation

Do not merge as-is. Address both major observability-export gaps and provide an
SDK-backed cross-harness regression proof.
