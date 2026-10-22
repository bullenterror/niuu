# NIU-1132 ticket

- **Identifier:** `NIU-1132`
- **Title:** Emit canonical per-step harness telemetry for native and external runtimes
- **Tracker:** https://linear.app/niuu/issue/NIU-1132/emit-canonical-per-step-harness-telemetry-for-native-and-external
- **Branch:** `regin`
- **Current tracker status:** `In Progress`

## Revision acceptance

Address the review finding that terminal telemetry must retain usage reported
before a native or CLI provider failure. Native terminal records must retain the
last streamed `MESSAGE_DONE` usage, and CLI terminal records must retain the
latest transport payload containing `modelUsage` even if `run_prompt()` raises.
