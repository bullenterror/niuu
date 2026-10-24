# NIU-1132 closure

- **Tracker identifier:** `NIU-1132` (`298eeb4e-ab60-4afe-8828-ccb529970bcf`)
- **Merged branch:** `regin`
- **Target branch:** `regin`
- **Merge commit SHA:** `216f2dca4439749abd136bab84c6bda90e8d4947` (direct-to-target delivery; no separate merge commit was needed)
- **Final tracker status:** `Done`

## Landed summary

The reviewed Ravn telemetry revision is pushed on `regin`. CLI provider duration
excludes tool execution intervals, and native and CLI provider failures emit
canonical terminal step records with normalized error categories while retaining
observed partial usage.

## Verification

No hosted PR was created because this was a direct-to-`regin` delivery. The
review re-check passed focused Ruff/diff validation and 74 relevant tests; the
final review record is committed at `87c70752` and pushed to `origin/regin`.
