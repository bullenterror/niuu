# NIU-1135 implementation

## Documentation

Added `docs/operator/regin-ticket-readiness-and-operator-delivery-handoff.md`.
It defines all five ticket-readiness conditions, the three honest routes for a
ticket that is not ready, and the A2A commissioning, evidence review, branch,
and operator-handoff model for Regin.

The page states that `regin` is cut from `dev`, every commissioned change starts
from and lands on `regin`, and Regin never merges, pushes, or opens a pull
request into `dev` or `main`. It also makes the operator's two handoff choices
explicit: promote `regin` to `dev`, or request changes.

## Verification

- Passed a content assertion that checks every required readiness, routing,
  A2A, branch, and operator-decision statement in the new page.
- Passed `uv run --extra dev python scripts/extract_openapi.py -o docs/site/openapi.json` followed by `uv tool run --from mkdocs-material==9.7.5 mkdocs build --strict --site-dir /tmp/niu-1135-docs-site`.
- Passed whitespace validation with `git diff --check` for the documentation and
  durable-record files.

No automated unit test applies to this documentation-only change.
