# Corpus + Workflow/PDF + Law browser + Highlighted claims — Plan

> REQUIRED SUB-SKILL: superpowers:executing-plans. Spec: `docs/superpowers/specs/2026-09-26-corpus-workflow-features-design.md`.

## Global Constraints
- Rule 1 unchanged; ingestion only through the JSONL contract + indexer.
- Suspended/repealed never support; statuses are Python-decided.
- Only reviewers/admins change review state; every change is an append-only version/approval row.
- UI follows the existing tokens/components (card, btn, Chip, StatusBadge, tabs).

## Review Focus
1. A suspended article must never be `supports` and never blocking.
2. Converter must not merge two articles into one unit; footnotes attach to the right article.
3. PDF only for accepted/approved; users only for their own reviews.
4. State transitions: no approve after reject; versions numbered monotonically.
5. Law browser respects collection ACL.

## Tasks
1. Schema + contract + weights: migration 0005 (units.status/notes/position), UnitIn.status/notes, indexer persists them and derives chunk status, new AUTHORITY table, `suspended` context-only in validate/scoring, verifier status label. Tests: legal weights, contract, indexer (integration), validate suspended.
2. Markdown converter `tools/md_to_jsonl.py` + unit tests on a synthetic sample of the real format; run on the real file and inspect stats.
3. Reset + load the real corpus (operational), run rules 1 + 2.
4. Workflow API (versions/approve/reject) + PDF export (WeasyPrint) + Dockerfile/CI deps. Tests (integration; PDF test skipped where Pango is unavailable).
5. Frontend: action bar, editor page with references panel + diff, PDF button. vitest for the diff util.
6. Laws API + law browser pages + "فتح في القانون" links. Integration tests for ACL/order.
7. Claim spans in the pipeline + `نص الرأي` tab. Unit test for span location.
8. Push, CI green, rebuild stack, smoke in browser.
