# NIU-300 review — Subscribe ODIN realm detail to SSE stream

## Verdict

`needs_changes`

## Findings

### Major

1. **`web-next/packages/plugin-realms/src/application/useRealmView.ts:37`** —
   The delivery's only new frontend test exercises the HTTP adapter and calls
   its unsubscribe function directly; it never mounts `useRealmView`, delivers
   an event through the subscription callback, or unmounts the hook.  The
   acceptance criterion specifically requires a focused regression test proving
   live cache updates and React-effect disposal.  Add a `useRealmView` hook test
   that captures the fake service listener, asserts that a `realm.detail`
   snapshot replaces the realm and trust-grant query entries, then unmounts and
   asserts the returned unsubscribe function is called exactly once.

### Minor

1. **`src/niuu/adapters/inbound/rest_realms.py:26`** — The stream polling and
   keepalive interval is a hard-coded timing value.  Project rules require
   timing values in the package configuration.  Move the interval into Niuu
   settings and thread it to the router/composition root (including deployed
   config rendering) rather than fixing it at 15 seconds in the adapter.

## Verification

- Reviewed the merged `regin` change `cbecf1fc` (`feat(realms): stream realm
  detail updates`) and its merge/closure commits at `24b65ddc` and `cb88f53a`.
- Confirmed `regin` and `origin/regin` both resolve to `cb88f53a`; reviewed the
  declared delivery ticket and implementation handoff.
- Passed: `uv run pytest -q tests/test_niuu/test_rest_realms.py` (24 passed;
  one pre-existing Starlette TestClient deprecation warning).
- Passed: `corepack pnpm --filter @niuulabs/plugin-valkyrie typecheck` and
  `corepack pnpm --filter @niuulabs/plugin-realms typecheck`.
- Passed: `corepack pnpm exec vitest run apps/niuu/src/services.test.ts
  packages/plugin-valkyrie/src/adapters/http.test.ts --coverage.enabled=false`
  (2 files, 101 tests).

## Recommendation

Add the hook-level live-update/unmount regression test before approval.  The
interval configuration cleanup can be included in the same follow-up or a
separate non-blocking change.
