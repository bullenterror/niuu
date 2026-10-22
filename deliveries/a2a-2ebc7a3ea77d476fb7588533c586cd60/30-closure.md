# Closure — NIU-1141

- **Tracker:** NIU-1141
- **Merged branch:** `regin`
- **Target branch:** `regin`
- **Merge commit SHA:** `6ef7b724` (direct integration on `regin`; no separate merge commit was required)
- **Final tracker status:** Done

## Landed summary

Tracker Delivery Flow now accepts `code.blocked` from `delivery-implement` and
routes it to the commissioner-visible `delivery-blocked` help-needed gate. The
gate preserves the implementing agent's rationale or reason, so impossible
requests end blocked with an actionable explanation instead of
`outcome_rejected`.
