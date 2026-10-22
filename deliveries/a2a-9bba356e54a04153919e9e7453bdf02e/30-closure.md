# NIU-1132 closure

- **Tracker identifier:** `NIU-1132` (`298eeb4e-ab60-4afe-8828-ccb529970bcf`)
- **Merged branch:** `regin`
- **Target branch:** `regin`
- **Merge commit SHA:** `1f5d51bd` (direct-to-target delivery; no separate merge commit was needed)
- **Final tracker status:** `Done`

## Landed summary

The reviewed Ravn telemetry revision is pushed on `regin`. CLI provider duration
excludes tool execution intervals, and native and CLI provider failures emit
canonical terminal step records with normalized error categories.

## Verification

The reviewed `regin` revision passed its focused telemetry suite: 73 tests
passed (`test_harness_telemetry`, `test_executor_cli`, the simple-turn agent
tests, and `test_prompt_budget`). No hosted PR was created because this was a
direct-to-`regin` delivery.
