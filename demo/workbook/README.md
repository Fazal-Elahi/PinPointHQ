# Migration workbook

Source `legacy_ats_small.csv` (14 rows) → Pinpoint account `acme`.
Approved by fazal at 2026-09-09T21:26:50.

## Import in this order
1. `tier1_applications.csv` (4 rows) — one application each, with stage.
2. `tier2_job_seekers.csv` (4 rows) — talent pipeline; source job title carried as a tag.

**Respect `import_order`.** Rows sharing a person must be imported in that order, or the
same human is created twice — a candidate exists only as a side effect of a create.

## Needs a person
- `exceptions.csv` (5 rows) — 2 failed validation, 3 unresolved identities.
- `excluded.csv` (1 rows) — outside the retention decision recorded in `decisions.json`.

## Read before importing
`not_preserved.md` states what this migration cannot carry. `manifest.json` carries the
counts and the five invariants, all of which must pass.
