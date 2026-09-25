# CONTEXT.md

> Ubiquitous language and load-bearing invariants for the Legal-RAG project.
> Read this before writing code, prompts, docs, or UI copy. Term names here
> are canonical — do not rename them elsewhere.

## Repos

- `legal-rag/` — v1/v2 demo. FastAPI + ChromaDB + SQLite + vanilla JS.
  Multi-agent `/query-v2` route lives here. **Deprecated once v3 ships.**
- `legal-rag-v3/` — production platform (in build). Kuwaiti legal opinion
  verification. New stack (Section "Stack"). Clean rewrite, not a patch.

## What the product does

A lawyer or reviewer submits a **legal opinion** (with optional question/facts).
The system verifies each **claim** in that opinion against the Kuwaiti legal
corpus and returns:

1. A per-claim table with a verdict and validated evidence.
2. A deterministic **score (0–100)** and **status**.
3. **References** split into مؤيدة (supporting) and معارضة (contradicting).
4. **Similar prior opinions** from the corpus.
5. For `needs_review`: a **الرأي المقترح** (suggested corrected opinion).

Users are Arabic-speaking. UI is Arabic and RTL. Code is English.

## Roles

- **admin** — users, collections, ingestion, eval, thresholds.
- **reviewer** — approve / reject / edit reviews.
- **user** — submit opinions for verification.

## Entities

### Source side (the corpus)

- **Document** — one legal source. Types: `constitution`, `law`,
  `decree_law`, `decree`, `regulation`, `ministerial_decision`, `circular`,
  `court_ruling`, `legal_opinion`, `fatwa`, `commentary`.
- **Unit** — one citable legal unit inside a document. Legislation → article.
  Rulings/opinions → section (`الوقائع`, `الأسباب`, `المنطوق`, …) or
  paragraph. Has a validity window `[valid_from, valid_to]`.
- **Chunk** — one embeddable/searchable text block. **One chunk = one
  citation.** Default: one chunk per unit. Long units split into
  `clause_split` / `semantic` chunks under the same `unit_id`
  (parent-child).
- **Context header** — prepended to every chunk before embedding and BM25:
  `{doc_type_ar}: {title_ar} — {path} — {article_label}`.
- **Collection** — an ACL-scoped grouping of documents.

### Review side (the app data)

- **Opinion** — the input document to verify (text or uploaded file).
- **Claim** — one atomic assertion inside an opinion. Fields:
  `{id, text_ar, type, materiality, cited_refs}`.
  - `type ∈ {legal_conclusion, legal_premise, factual_premise, procedural}`
  - `materiality ∈ {core, supporting}`
  - `factual_premise` claims are recorded but **not scored** (corpus can't
    verify client facts).
- **Passage** — one retrieved chunk shown to the verifier for a claim.
  Gets a review-scoped stable ID like `P1`, `P2`.
- **Evidence** — one passage attached to a claim by the LLM verifier.
  Fields: `{passage_id, stance, quote_ar}`.
  - `stance ∈ {supports, contradicts, context}`
  - `quote_ar` ≤ 40 words, verbatim.
- **Review** — one complete verification run for one opinion.
- **Version** — an immutable snapshot of a review.
  `kind ∈ {ai_report, ai_suggested_opinion, human_edit}`.
- **Approval** — an immutable decision on a version.
  `decision ∈ {approve, reject, system_accept}`.

## Statuses and verdicts

### Per-claim verdict

- `supported` — passages establish the claim.
- `partially_supported` — core rule supported, but a condition, exception,
  number, or deadline differs. Difference is named in `reasoning_ar`.
- `contradicted` — passages contradict the claim.
- `insufficient` — passages neither support nor contradict.

### Review status

- `processing` — pipeline running.
- `accepted` (مقبول) — `score ≥ ACCEPT_THRESHOLD` **and** zero blocking
  contradictions. Approved by the system.
- `needs_review` (يحتاج مراجعة) — otherwise. UI shows **اعتماد**,
  **تعديل واعتماد**, رفض.
- `no_information` (لا تتوفر معلومات) — no valid evidence for any claim.
  UI shows the fixed message below.
- `approved` — a human approved a version.
- `rejected` — a human rejected the review.
- `failed` — pipeline error.

### Fixed messages (never rewritten by the LLM)

- No-information message (exact string):
  `لا تتوفر معلومات في المصادر المتاحة للتحقق من هذا الرأي.`
- Resolved-conflict badge:
  `تعارض محسوم لصالح المصدر الأعلى`

### Source status (per document / per unit)

- `in_force` — valid at the review's as-of date.
- `amended` — replaced by a newer version; kept with a validity window.
- `repealed` — invalidated. **Never counts as `supports` evidence.**
  May appear as `context` only, labeled.

## Scoring (deterministic — Python, no LLM)

- Weights: `core = 2`, `supporting = 1`. `factual_premise` excluded.
- Claim value: `supported = 1.0`, `partially_supported = 0.5`,
  `contradicted = 0.0`, `insufficient = 0.0`.
- `score = round(100 × Σ(weight × value) / Σ weight)`.

**Rule:** the LLM never emits `score`, `status`, `verdict-truth`, or
`accept/reject`. Those are computed from validated structured output.

## Blocking contradiction

A `contradicts` evidence item is **blocking** when:

- Its source is **in force at the as-of date**, AND
- Its authority ≥ the highest-authority supporting source for that claim, OR
- Same authority + later effective date (`lex posterior`).

Otherwise the contradiction is shown but not blocking (marked with the
`resolved-conflict badge` above).

Suspected `lex specialis` (special law vs general law at same level) →
flag `requires_human_judgment = true` and treat as blocking.

## Kuwaiti legal hierarchy (authority weights)

Config values — see `authority.py`:

| doc_type              | authority |
|-----------------------|-----------|
| constitution          | 1.00      |
| law                   | 0.90      |
| decree_law            | 0.90      |
| decree                | 0.80      |
| regulation            | 0.70      |
| ministerial_decision  | 0.60      |
| circular              | 0.50      |
| court_ruling (cassation) | 0.75   |
| court_ruling (other)  | 0.60      |
| legal_opinion / fatwa | 0.50      |
| commentary            | 0.40      |

Authority is a **tie-breaker inside relevance**, not an override.
`final = p × (0.85 + 0.15 × authority)`, where `p = sigmoid(rerank_logit)`.

## Retrieval vocabulary

Filters (always inside the SQL query, never after scoring):
- `collection_id IN (user's collections)`
- `embedding_model = current`
- `valid_from ≤ as_of AND (valid_to IS NULL OR valid_to > as_of)`
- unless `include_repealed`: `status ≠ 'repealed'`
- optional: `doc_type`, `legal_domain`

Pipeline:
- **Vector search** — pgvector cosine over normalized `vector(1024)`, top
  `VECTOR_K = 50`. Cosine similarity `sim = 1 − distance`. Normalized
  display `sim01 = 1 − distance/2`.
- **BM25** — ParadeDB `pg_search` on `text_norm`, top `BM25_K = 50`.
- **RRF (Reciprocal Rank Fusion)** —
  `RRF(d) = Σ w_list / (K + rank_list(d))`, `K = 60`,
  `w_vector = w_bm25 = 1.0`, keep top `FUSED_K = 30`. Ranks are 1-based.
  Raw similarities never enter the fusion formula.
- **Rerank** — `BAAI/bge-reranker-v2-m3` via TEI `/rerank`. Convert logit:
  `p = sigmoid(logit)`. Never use raw logit downstream.
- **Authority weighting** — bounded, above.
- **Noise cut** — drop `p < MIN_RERANK_PROB` (default 0.15).
- **Per-claim keep** — top `PER_CLAIM_K = 6` **plus pinned exact references**.
- **Exact-reference pinning** — if the claim cites `المادة N من القانون
  رقم X لسنة Y`, that unit is **pinned** into the evidence set regardless
  of rank.
- **Parent expansion** — a kept `clause_split` chunk carries its parent
  article text (≤ 1,200 tokens) as context.
- **Context budget** — ≤ 6,000 tokens of evidence per claim, ≤ 40,000
  tokens per verification call. Claim batches ≤ 6 claims per call.

## Text pipeline

Module: `text/arabic.py`, versioned by `NORMALIZER_VERSION`.

- `normalize_for_search(text)` — used by **both** BM25 index and BM25 query.
  Strip tashkeel + tatweel + zero-width chars, unify
  `أ إ آ ٱ → ا`, `ى → ي`, `ة → ه`, `ؤ → و`, `ئ → ي`,
  Eastern Arabic digits `٠-٩` → `0-9`, collapse whitespace.
  Invariant: `المادة ٤١` MUST match `المادة 41`.
- `normalize_for_embedding(text)` — lighter. Strip tashkeel, tatweel,
  zero-width, convert digits, collapse whitespace. Keep letter forms.

## LLM policy

- **Provider: Anthropic Claude only.** Model `claude-sonnet-4-5`.
- **No fallback provider.** No Groq, Gemini, Cohere, OpenRouter, LangGraph,
  or multi-agent orchestration in v3.
- **Temperature 0** on every call.
- **Structured output** on every call (tool use with forced `tool_choice`
  and a JSON schema, or the model's native structured-outputs feature).
- **Prompt caching** on the static system prompt.
- **Retry** with exponential backoff on transient failures. Then fail
  with a clean Arabic error string. Never silently degrade.

## Model serving (self-hosted)

Text Embeddings Inference (TEI), two containers:
- `tei-embed` — `BAAI/bge-m3`. Dense, 1024-d, normalized, 8192-token
  input. GPU in prod, CPU for local dev.
- `tei-rerank` — `BAAI/bge-reranker-v2-m3` via `/rerank`. 512-token
  truncation on pairs.

Embedding model is a P1 choice: default is `bge-m3`, alternative is
`intfloat/multilingual-e5-large`. Eval harness picks the winner on
Recall@10 and nDCG@10, then it is locked.

## Embedding invariant (Rule 1)

The **entire system runs on one embedding model at a time.** On startup,
API and workers read `system_meta`. If `embedding_model`, `embedding_dim`,
or `normalizer_version` differ from config, they **refuse to start**.

Every `chunks` row stores `embedding_model`. Queries filter on it.

Model swap = new migration job that re-embeds into a shadow column,
validates with the eval harness, then swaps atomically. **Never mix.**

## Production rules (mandatory)

Supplied checks in `production_rules/`. Copy unchanged. Never edit
thresholds inside `production_rules/` to make a build pass — fix the
pipeline or the data.

1. **Rule 1 — same embedding model everywhere.**
   Runs after every ingestion job, every deploy, in CI.
2. **Rule 2 — quality > quantity.**
   Chunk = one citable unit. No boilerplate. No dupes.
   Runs after every ingestion job.
3. **Rule 3 — test retrieval separately from generation.**
   Recall@k / MRR / nDCG / exact-article hit / repealed-leak = 0 /
   ACL-leak = 0. Runs on every retrieval change, every release, nightly.

**P1 acceptance gate:** all three checks exit 0 on the real gold set.

Public contract that the app MUST expose for the checks to run:
- Table `system_meta(key, value)` with `embedding_model`,
  `embedding_dim`, `normalizer_version`.
- Table columns as listed in Section 5.2 of the brief (see
  `INGESTION_CONTRACT.md` once written).
- Module `app/retrieval/embedder.py` exposing `build_passage_input`,
  `build_query_input`, `embed_texts`. Only code path used for embeddings
  in both ingestion and query.
- `POST /api/retrieval/search` (admin/eval) with
  `mode ∈ {vector, bm25, hybrid, hybrid_rerank, full}` and the response
  shape in the brief. `collections=null` scopes to caller's ACL.

## Stack (v3)

- **Backend:** Python 3.12, FastAPI (async), Pydantic v2, SQLAlchemy 2.0
  async + Alembic. `anthropic` SDK. `arq` on Redis 7 for workers.
  PyMuPDF, python-docx, pdf2image + Tesseract `ara` (worker OCR only).
- **Data:** PostgreSQL 16 via **ParadeDB** (BM25 + pgvector 1024-d,
  HNSW `m=16, ef_construction=128`, tune `hnsw.ef_search` at query
  time). PgBouncer in front. S3-compatible object store (MinIO local).
- **Model serving:** TEI containers, above.
- **Frontend:** React 18 + TypeScript + Vite, Tailwind, shadcn/ui,
  TanStack Query, React Router, TipTap (RTL rich text), react-pdf.
- **DevOps:** Docker Compose for dev. K8s-ready. Prometheus + Grafana.
  MLflow used **only** for offline retrieval/verification eval runs —
  never in the request path.

## Endpoints (naming, not full contract)

Base: `/api/v1`.

- Auth: `/auth/{login,refresh,logout,me}`.
- Reviews: `POST /reviews` (multipart), `GET /reviews/{id}`,
  `GET /reviews/{id}/events` (SSE), `GET /reviews`, versions/diff/approve/
  reject/export.
- Sources: `GET /sources/chunks/{id}`, `GET /sources/documents/{id}`.
- Retrieval (admin/eval): `POST /retrieval/search`.
- Admin: users, collections, ingestion jobs, corpus stats, eval runs,
  usage, settings, publish-to-corpus.
- Health: `/health/live`, `/health/ready` (checks DB, Redis, TEI,
  embedding-model guard).

## Config values that are tuning targets (not truths)

Every threshold below is a starting value. It gets tuned by the eval
harness, not decided here.

| Constant             | Starting value |
|----------------------|----------------|
| `ACCEPT_THRESHOLD`   | 90             |
| `MIN_RERANK_PROB`    | 0.15           |
| `VECTOR_K`           | 50             |
| `BM25_K`             | 50             |
| `FUSED_K`            | 30             |
| `PER_CLAIM_K`        | 6              |
| `MAX_CHUNK_TOKENS`   | 450            |
| `MAX_CLAIMS`         | 40             |
| RRF `K`              | 60             |
| `w_vector`, `w_bm25` | 1.0, 1.0       |

## Language rules

- **All user-facing strings: Arabic.**
- **Code, identifiers, docstrings, logs, comments: English.**
- Numerals in UI: Western digits for article numbers (locked in
  `docs/DECISIONS.md`).

## What v3 is NOT

- No multi-agent orchestration. No LangGraph. No agent trace UI.
- No provider other than Anthropic Claude.
- No free-form legal chat (retrieval layer will support it later).
- No auto-corpus-crawling. The client preprocesses to JSONL.
- No model fine-tuning.
- No multi-language UI.

## Cross-reference

- `docs/ARCHITECTURE.md` — system diagram, request lifecycle, SSE stages.
- `docs/DECISIONS.md` — every non-obvious call (threshold defaults,
  digit form, fallback DB, embedding model pick, etc.).
- `docs/INGESTION_CONTRACT.md` — the JSONL schema and row-level error
  contract for uploads.
- `docs/RUNBOOK.md` — deploy, ingest, re-embed swap, eval, rollback.
- `production_rules/README.md` — the three checks and how they fail.
