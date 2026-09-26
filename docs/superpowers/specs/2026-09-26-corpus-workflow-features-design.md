# Real corpus, approval workflow + PDF, law browser, highlighted claims — Design

Approved by the user in chat on 2026-09-26 ("everything is approved please just start").

## 1. Corpus: مجموعة التشريعات الكويتية (Jazaa Al-Otaibi, amendments to 1/4/2026)

Source: `C:\Users\ziadg\ms-opinion\JEZAALOTAIBI-15.md` (52k lines, 73 laws, 7,260 article headings, 554 footnotes).

- Converter `backend/tools/md_to_jsonl.py` → ingestion-contract JSONL (existing pipeline; Rule 1 untouched).
  - `# Title` = one document. Formal title/number/year from the following blockquote (`القانون رقم 14 لسنة 1973 …`). Skip `# فهرس القوانين`.
  - doc_type from title: دستور → constitution; مرسوم بقانون → decree_law; لائحة/اللائحة → regulation; قرار → ministerial_decision; مرسوم (not بقانون) → decree; otherwise law.
  - `##`–`######` headings = path (الباب/الفصل/الفرع…), reset below their level.
  - `**مادة N**` / `**المادة N**` / `مكرر` variants / ordinals (الأولى…) = article units; `[^pX-Y]` markers resolved to footnote text → unit `notes`.
  - Text before the first article of a document (preamble) and non-article sections (e.g. المذكرة التفسيرية) = `section` units.
  - Unit status: body only "ملغاة" (any brackets) → `repealed`, text replaced by "ملغاة" + the repeal note; footnote "وقف العمل" → `suspended`; otherwise `in_force` (`amended` notes kept as notes only — the text is the current version).
  - Duplicate article numbers inside one document get suffixed unit ids.
- Schema (migration 0005): `units.status`, `units.notes` (JSON list), `units.position` (document order).
- Status semantics: `suspended` is returned by search (only `repealed` is filtered) but is **context only**: `validate.in_force` treats it like repealed, so it can never support a claim and never blocks.
- Authority weights (user-specified): constitution 0.99; law 0.70; decree_law 0.70; decree 0.65; regulation 0.60; ministerial_decision 0.50; circular 0.30; legal_opinion 0.15; fatwa 0.15; court_ruling 0.10 (cassation 0.12); commentary 0.05. Mechanism unchanged (bounded tie-breaker; blocking = contradicting in-force source with authority ≥ strongest supporting source). v1's negation/cosine resolver is not reintroduced (quote validator + LLM verifier cover it).
- Reset: truncate corpus, reviews (+claims, evidence, versions, approvals), llm_calls, ingestion jobs, collections; delete users except `admin`; clear the uploads bucket. Create collection `التشريعات الكويتية` (id 1); load via ingestion job; run production rules 1 + 2.

## 2. Approval workflow + PDF (P4 slice)

- Roles: reviewer/admin act; the submitting user reads and downloads.
- `POST /reviews/{id}/versions {text}` → `human_edit` version (next version number).
- `POST /reviews/{id}/approve {version?}` → `approvals(decision=approve, approver)`, status `approved`. Allowed from `needs_review`, `no_information`, `accepted`.
- `POST /reviews/{id}/reject {reason}` → `approvals(decision=reject, comment)`, status `rejected`.
- `GET /reviews/{id}/versions`.
- `GET /reviews/{id}/export.pdf` — only `accepted`/`approved`; owner or staff. WeasyPrint (HarfBuzz shaping) HTML template, Noto Sans/Naskh Arabic font, brief palette. Content: header, question, final opinion (latest `human_edit`, else original text), status/score/approval stamp (approver, date, version), claims table (claim, type, verdict, evidence quotes with citations), supporting + contradicting references with notes.
- Frontend: action bar enabled for staff (اعتماد, تعديل واعتماد, رفض with reason); editor page `/reviews/:id/edit`: plain-text RTL textarea preloaded with the suggested opinion (or original), references side panel with "إدراج استشهاد" (inserts `[P#]`), word diff vs the AI text, save draft, approve (confirm). "تنزيل PDF" button when accepted/approved.

## 3. Smart features (current design language)

- Law browser: `GET /laws` (documents in the caller's ACL: id, title, type, number, year, article count), `GET /laws/{doc_id}` (units in order with path, label, status, notes, text). Page `التشريعات`: searchable list; law page with table of contents grouped by path, article cards with status badges (معدلة/مضافة/ملغاة/موقوفة) and notes; deep link `/laws/:docId#unit` used by "فتح في القانون" on reference cards and the source drawer.
- Claims highlighted in the opinion: pipeline stores `claims[i].span = [start, end]` (character offsets in the opinion) when a claim aligns with a sentence of the opinion (fuzzy, word-snapped); new first tab `نص الرأي` renders the opinion with verdict-coloured highlights; click → claims tab at that claim.

## Out of scope
Email delivery, citation checker, legislation search page, OCR, remaining P5.
