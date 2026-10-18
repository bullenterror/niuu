# NIU-1119 — A2A end-to-end observability

- **Tracker:** [NIU-1119](https://linear.app/niuu/issue/NIU-1119/a2a-end-to-end-observability-traces-to-tempo-metrics-and-correlated)
- **Scope:** Instrument the Valkyrie/Ravn tool-build path and Ting A2A JSON-RPC surface so one OTel trace can follow a learned-tool commission through A2A launch and flock session handoff.
- **Acceptance criteria:** Propagate trace context across A2A, link the flock session trace through launch provenance/workload config, expose Ravn and Ting OTel metrics, correlate stdout logs with trace/span ids, and keep observability disabled by default.

## Implementation pass

Resolved the Linear task through the repository tracker shim and confirmed it is `In Progress` before starting code changes.

## Revision pass

Resolved the review-blocking duplicate public metric emission by keeping `ravn_tool_build_*` ownership in the Ravn `BuildTool` lifecycle wrapper and removing the same public metric emissions from the A2A backend.

## Regin delivery pass

The pre-existing `feat/niu-1119-a2a-observability` branch was based on `origin/dev`, contrary to the mandatory branch rule. Its implementation was therefore reviewed and cherry-picked onto `regin`; no `dev` or `main` branch was targeted or modified by this delivery pass.

## Equivalent local observability proof

The operator authorized an equivalent self-contained proof in place of live-cluster access. The proof must exercise the actual A2A export path without `kubectl`, external sink credentials, or a deployed Tempo/Loki environment, and it must be committed directly to `regin`.

## Operator approval

The operator approved moving NIU-1119 to `In Review` based on the passing focused proof. The 88 full-suite failures are accepted as outside this change's blast radius and are to be tracked separately, not treated as blockers for this ticket. The tracker was moved to `In Review`.

The delivery is directly integrated on `regin` (`origin/regin` at `f2f94756` when approved). No hosted PR exists; the prior feature branch based on `dev` is not the delivery branch and no PR targets `dev` or `main`. The applicable integration target is `regin`.

## Review revision — enabled setup configuration

The review found that the enabled Eitri and Ivaldi local Ravn configurations were missing the now-required OTLP/HTTP Loki `observability.log_endpoint`. This revision adds each setup's `/v1/logs` endpoint and a regression test that loads every checked-in enabled Ravn setup configuration through `Settings`. The tracker was returned to `In Progress` while this review correction is verified on `regin`.

The correction is integrated on `origin/regin` through `04630211`; NIU-1119 was
then set to `Done`. There is no hosted PR for this direct-regin delivery.


## Review revision — enabled resident configurations

The review finding was reproduced against the pre-revision `regin` revision: both enabled Ravn setup files lacked `observability.log_endpoint`, which is required whenever observability is enabled. Both now configure their Eitri OTLP/HTTP Loki collector endpoint at `/eitri/otlp/v1/logs`. The regression test discovers and parses every checked-in Ravn setup config that enables observability, so a missing required endpoint fails before a resident startup attempt.

The tracker was returned to `In Progress` while this revision is prepared for re-review.
