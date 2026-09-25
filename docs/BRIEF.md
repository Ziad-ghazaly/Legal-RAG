# Coding Brief: Kuwaiti Legal Opinion Verification Platform (Legal-RAG v3)

You are a senior backend + frontend engineer. Build a **production-grade** system that verifies Arabic legal opinions against a large corpus of Kuwaiti legal sources. This replaces an existing demo (`legal-rag/`, FastAPI + ChromaDB + SQLite + vanilla JS). Read this brief fully before writing code. Where this brief sets a number (threshold, k, token budget), put it in config — it is a starting value to be tuned by the evaluation harness, not a fact.

---

## 0. Ground rules for you (the coding agent)

1. Build a **new repo layout** (`legal-rag-v3/`). Do not patch the old demo in place. Reuse only what Section 11 lists.
2. **One LLM provider only:** Anthropic Claude, model `claude-sonnet-4-5`. No Groq, Gemini, Cohere, OpenRouter, LangGraph, or multi-agent orchestration. No fallback provider. Use retry with exponential backoff, then fail with a clean Arabic error.
3. **Deterministic code decides, the LLM classifies.** The confidence score, acceptance status, citation validity, and source validity are computed in Python. The LLM never outputs the final score or status.
4. **Retrieval is built and evaluated before generation.** Phase 1 (Section 12) must pass its retrieval eval gate before Phase 2 starts.
5. Every Claude call uses **structured output** (tool use with a forced `tool_choice` and a JSON schema, or the Anthropic structured-outputs feature if available for this model), temperature 0, and prompt caching on the static system prompt.
6. Arabic-first, RTL UI. All user-facing strings in Arabic. Code, identifiers, logs in English.
7. Write tests for: Arabic normalization, chunker, RRF, scoring, citation validation, ACL filtering. No PR is done without them.
8. When the brief is ambiguous, pick the simplest option that satisfies the stated requirement, write the decision in `docs/DECISIONS.md`, and continue.

---

## 1. What the product does

A lawyer or legal reviewer submits a **legal opinion** (typed, pasted, or uploaded PDF/DOCX/TXT), optionally with the **question/facts** it answers. The system:

1. Breaks the opinion into atomic legal claims.
2. For each claim, searches the Kuwaiti legal corpus (legislation + prior opinions/rulings) with hybrid retrieval.
3. Classifies each piece of evidence as **supporting** or **contradicting** the claim, with a short verbatim quote.
4. Computes a **verification score (0–100)** deterministically.
5. Decides status:
   - **مقبول (Accepted)** — score ≥ 90 **and** no blocking contradiction. Shown as approved by the system.
   - **يحتاج مراجعة (Needs review)** — score < 90 **or** any blocking contradiction. User gets two actions: **اعتماد (Approve)** or **تعديل واعتماد (Edit & approve)**. Edit opens a dedicated editor page, then approve.
   - **لا تتوفر معلومات (No information)** — no claim has any valid evidence. The system says exactly: `لا تتوفر معلومات في المصادر المتاحة للتحقق من هذا الرأي.` and invents nothing.
6. Lists **references** in two groups — **مؤيدة (supporting)** and **معارضة (contradicting)** — each with: document title, number/year, article number, source status (in force / amended / repealed), and a short verbatim quote (≤ 40 words).
7. Shows **similar prior opinions** found in the corpus.
8. Stores every AI output, edit, and approval with full audit history. Approved opinions can be exported (PDF/DOCX) with references.

Scale target: tens of thousands of legal documents, low millions of chunks, dozens of concurrent users. Design so it scales horizontally (stateless API, background workers, separate model-serving).

---

## 2. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Input: opinion as text or file (PDF, DOCX, TXT; ≤ 20 MB, configurable). Optional: question/facts text, reference date ("as-of" date, default today), collection scope. |
| FR-2 | Uploaded files are parsed in a background worker. Scanned PDFs go through OCR (Tesseract `ara`), reusing the old `ocr_pipeline.py` logic. |
| FR-3 | Claim extraction: Claude splits the opinion into claims `{id, text_ar, type: legal_conclusion \| legal_premise \| factual_premise \| procedural, materiality: core \| supporting, cited_refs: [{law_number, year, article, raw}]}`. Factual premises about the client's case are recorded but **not scored** (the corpus cannot verify client facts). |
| FR-4 | Per-claim hybrid retrieval (Section 6), including **exact reference lookup** when the opinion cites a specific law/article. |
| FR-5 | Per-claim verification: Claude returns `{verdict: supported \| partially_supported \| contradicted \| insufficient, evidence: [{passage_id, stance: supports \| contradicts \| context, quote_ar}], reasoning_ar}`. |
| FR-6 | Deterministic validation of every evidence item (Section 7.3). Invalid evidence is dropped, never shown. |
| FR-7 | Deterministic score + status (Section 7.4). |
| FR-8 | Report: executive summary (Arabic, short), per-claim table, references split into supporting/contradicting, similar opinions. For Needs review, Claude also drafts a **suggested corrected opinion** (`الرأي المقترح`) that fixes only contradicted/unsupported claims, citing passage IDs. |
| FR-9 | Review workflow: Approve, Edit & approve (editor page), Reject (with reason). Every action creates an immutable version/approval record. Accepted-by-system reviews are also recorded as an approval event with `approver = system`. An admin setting `REQUIRE_HUMAN_SIGNOFF` (default false) forces Accepted reviews into a one-click human confirm. |
| FR-10 | Editor page: rich-text RTL editor preloaded with the AI response; side panel with the review's references (click to insert a citation); save draft; view diff vs the AI version; approve. |
| FR-11 | Similar opinions: top 5 prior opinions (ingested historical opinions + human-approved opinions from this system) by hybrid similarity to the whole opinion. |
| FR-12 | History: list/filter/search reviews by status, score, date, user, reviewer. |
| FR-13 | Export approved opinion + references as PDF and DOCX. |
| FR-14 | Admin: users and roles, collections and ACL, ingestion jobs (upload preprocessed JSONL, see status/errors), corpus stats, evaluation reports, usage/cost per user. |
| FR-15 | Human-approved opinions are indexed into the `opinions` corpus **only** when an admin marks them "publish to corpus". Never auto-index AI output. |
| FR-16 | Progress streaming: the result page shows live stages (parsing → extracting claims → retrieving → verifying → scoring) via Server-Sent Events. |

## 3. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | Latency targets (with GPU model serving): retrieval per claim p95 ≤ 1.5 s. Full review of a 2-page opinion (~10 claims) p95 ≤ 60 s, with first progress event < 1 s. |
| NFR-2 | ACL leak rate = 0. ACL filtering happens **inside** the SQL query (pre-filter), never after scoring. |
| NFR-3 | Repealed-source leak: a repealed article can never count as supporting evidence (it can appear as context, labeled). |
| NFR-4 | Embedding consistency guard (Section 5.4). The app refuses to start on mismatch. |
| NFR-5 | Full audit trail: every LLM call (model, tokens, cost, latency, request_id), every version, every approval. Append-only. |
| NFR-6 | Security: JWT access (15 min) + refresh (7 days, rotating), bcrypt/argon2 passwords, RBAC, CORS restricted by config, secrets from env only, no default admin password in code. Uploaded files in object storage with server-side encryption. |
| NFR-7 | Stateless API containers. Heavy work (parsing, OCR, embedding, verification jobs) runs in workers. |
| NFR-8 | Observability: structured JSON logs with `request_id`, OpenTelemetry traces across API → worker → DB → model server → Claude, Prometheus metrics (latency per stage, tokens, cost, queue depth, error rate). |
| NFR-9 | Reproducibility: every review stores the config snapshot (retrieval params, model names, prompt versions, embedding model). |

---

## 4. Tech stack (use this, do not substitute without writing a DECISIONS.md entry)

**Backend**
- Python 3.12, FastAPI (async), Pydantic v2, SQLAlchemy 2.0 (async) + Alembic migrations.
- Anthropic Python SDK (`anthropic`), model `claude-sonnet-4-5`.
- Worker: `arq` (Redis-based, async) for ingestion and review jobs. Redis 7.
- File parsing: PyMuPDF, python-docx; OCR: pdf2image + Tesseract `ara` (worker only).

**Data**
- PostgreSQL 16 using the **ParadeDB** image (includes `pg_search` for true BM25 and `pgvector`). ParadeDB's stemmer supports Arabic; check the current ParadeDB docs for exact `CREATE INDEX ... USING bm25` syntax and tokenizer options, and use a tokenizer that splits Arabic correctly.
- pgvector `vector(1024)` with an HNSW index (`vector_cosine_ops`, `m=16`, `ef_construction=128`; tune `hnsw.ef_search` at query time).
- PgBouncer in front of Postgres.
- Object storage: S3-compatible (MinIO locally).
- If the deployment target forbids ParadeDB, the fallback is plain Postgres `tsvector` with the built-in `arabic` configuration — record it in DECISIONS.md and note that `ts_rank` is not BM25.

**Model serving**
- Hugging Face **Text Embeddings Inference (TEI)**, two containers:
  - embeddings: `BAAI/bge-m3` (dense, 1024-d, normalized; up to 8192 tokens input)
  - reranker: `BAAI/bge-reranker-v2-m3` via TEI `/rerank`
- Both are XLM-RoBERTa based, which TEI serves. GPU image in production (a single T4/L4-class GPU is enough); CPU image for local dev.
- The embedding model is chosen by the eval harness. The candidates are `BAAI/bge-m3` (default) and `intfloat/multilingual-e5-large` (the old model: 512-token limit, needs `query: ` / `passage: ` prefixes). Pick the winner on Recall@10 / nDCG@10 on the gold set, then lock it.

**Frontend**
- React 18 + TypeScript + Vite, Tailwind CSS, shadcn/ui (Radix), TanStack Query, React Router, TipTap (RTL rich-text editor), react-pdf for the source viewer.
- Font: IBM Plex Sans Arabic (Google Fonts). `dir="rtl"`, `lang="ar"`.

**Ops**
- Docker Compose for dev (api, worker, postgres(paradedb), pgbouncer, redis, minio, tei-embed, tei-rerank, frontend via nginx, prometheus, grafana). Kubernetes-ready (health/readiness endpoints, env config, no local disk state).
- MLflow is kept **only** for offline retrieval/verification eval runs, not in the request path.

---

## 5. Data model and ingestion

### 5.1 Ingestion contract (preprocessed input)

The client preprocesses raw documents separately and delivers **JSONL**, one document per line. Ingestion validates this contract with Pydantic and rejects bad lines with row-level errors (the job continues).

```json
{
  "doc_id": "kw-law-6-2010",
  "doc_type": "constitution | law | decree_law | decree | regulation | ministerial_decision | circular | court_ruling | legal_opinion | fatwa | commentary",
  "title_ar": "قانون رقم 6 لسنة 2010 في شأن العمل في القطاع الأهلي",
  "number": "6",
  "year": 2010,
  "issuing_authority": "مجلس الأمة",
  "issue_date": "2010-02-21",
  "effective_date": "2010-02-21",
  "status": "in_force | amended | repealed",
  "repealed_by": null,
  "gazette_ref": "الكويت اليوم العدد ...",
  "legal_domain": ["labor"],
  "collection": "kuwait-legislation",
  "source_uri": "s3://.../original.pdf",
  "units": [
    {
      "unit_id": "kw-law-6-2010/a41",
      "level": "article | clause | section | paragraph",
      "path": ["الباب الخامس", "الفصل الثاني"],
      "article_number": 41,
      "article_label": "المادة 41",
      "text": "…",
      "valid_from": "2010-02-21",
      "valid_to": null,
      "amended_by": ["kw-law-xx-2016"]
    }
  ]
}
```

- Legislation: `units` are articles (or sub-articles).
- Rulings/opinions: `units` are sections (`الوقائع`, `الأسباب`, `المنطوق`, …) or paragraphs.
- Amended articles appear as **multiple units with the same article_number and non-overlapping validity ranges**. Retrieval filters by the review's as-of date.

### 5.2 Tables (Alembic migrations)

- `users`, `roles` (`admin`, `reviewer`, `user`), `collections`, `user_collections`
- `documents` — one row per doc; all metadata above; `authority_level` int (derived from `doc_type`, Section 6.6)
- `units` — one row per unit, FK document, hierarchy path, article number, validity range
- `chunks` — `id`, `unit_id`, `document_id`, `collection_id`, `chunk_kind` (`article | clause_split | semantic | table`), `context_header`, `text` (original), `text_norm` (normalized, Section 5.3), `token_count`, `embedding vector(1024)`, `embedding_model`, `doc_type`, `authority_level`, `status`, `valid_from`, `valid_to`, `legal_domain text[]`, `content_hash`
- BM25 index on `chunks (context_header || ' ' || text_norm)`; HNSW index on `embedding`; B-tree indexes on `collection_id`, `status`, `doc_type`, `(valid_from, valid_to)`; plus `(document number, year, article_number)` on units for exact lookup
- `opinions` corpus uses the same `documents/units/chunks` tables with `doc_type in ('legal_opinion','court_ruling','fatwa')`
- `reviews` — `id`, `user_id`, `question`, `opinion_text`, `file_key`, `as_of_date`, `collection_scope`, `status` (`processing | accepted | needs_review | no_information | approved | rejected | failed`), `score`, `config_snapshot jsonb`, timestamps
- `review_claims` — claim fields + `verdict`, `weight`, `reasoning_ar`
- `claim_evidence` — `claim_id`, `chunk_id`, `stance`, `quote_ar`, `quote_verified bool`, `authority_level`, `source_status`, `blocking bool`
- `review_versions` — `review_id`, `version`, `kind` (`ai_report | ai_suggested_opinion | human_edit`), `content` (TipTap JSON + plain text), `author_id`, `created_at` (append-only)
- `approvals` — `review_id`, `version`, `decision` (`approve | reject | system_accept`), `approver_id` (null = system), `comment`, `created_at` (append-only)
- `llm_calls`, `audit_log`, `ingestion_jobs`, `eval_runs`, `system_meta` (holds the locked `embedding_model`, `embedding_dim`, `normalizer_version`)

### 5.3 Arabic normalization (one module, used everywhere)

`app/text/arabic.py`, versioned (`NORMALIZER_VERSION`). Two functions:

- `normalize_for_search(text)` (BM25 index **and** BM25 query): strip tashkeel, strip tatweel `ـ`, unify alef `أ إ آ ٱ → ا`, `ى → ي`, `ة → ه`, `ؤ → و`, `ئ → ي`, Eastern Arabic digits `٠-٩` → `0-9`, collapse whitespace, remove zero-width chars.
- `normalize_for_embedding(text)` (embedding index **and** query): lighter — strip tashkeel, tatweel, zero-width chars, convert digits, collapse whitespace. Keep letter forms.

Digit conversion matters: `المادة ٤١` must match `المادة 41`. Unit-test both functions with real legal text.

### 5.4 Production rule 1: same embedding model everywhere

- `EMBEDDING_MODEL`, `EMBEDDING_DIM`, and the query/passage prefix scheme live in one config object. Ingestion and query both call the same `Embedder` class, which calls the same TEI endpoint.
- On startup the API and workers read `system_meta`. If `embedding_model`, `embedding_dim`, or `normalizer_version` differ from config, **refuse to start** with a clear error.
- Every chunk row stores `embedding_model`. Queries filter `embedding_model = current`.
- Changing the model = a new migration job that re-embeds into a shadow column, validates with the eval harness, then swaps atomically. Never mix.

### 5.5 Chunking (legal-aware hybrid; the most important quality lever)

The goal is **one citable legal unit per chunk** (bad chunking is failure #1).

1. **Structural first (legislation).** Chunk unit = one article. Never merge two articles into one chunk: each chunk must map to exactly one citation.
2. **Long articles (> `MAX_CHUNK_TOKENS`, default 450):** split at clause boundaries — numbered items and markers such as `أولاً`, `ثانياً`, `1-`, `(1)`, `(أ)`, `أ-`, `البند`, `الفقرة`. If a piece is still too long, apply **semantic breakpoint splitting**: embed the sentences, compute cosine distance between adjacent sentences, and split where it exceeds the 90th-percentile distance of that article. Each piece keeps the parent `unit_id` (parent-child).
3. **Short articles (< 40 tokens)** stay as their own chunk. The context header (step 4) gives them enough signal.
4. **Context header** prepended to every chunk for embedding and BM25, and shown to the LLM:
   `{doc_type_ar}: {title_ar} — {path joined by " — "} — {article_label}`
   e.g. `قانون: قانون رقم 6 لسنة 2010 في شأن العمل في القطاع الأهلي — الباب الخامس — المادة 41`
5. **Rulings / opinions / commentary (no articles):** section-aware. Split on section headings first, then semantic chunking (same breakpoint method), target 200–450 tokens with ~1 sentence overlap.
6. **Tables:** keep each table as its own chunk, serialized as Markdown rows with the header row repeated.
7. **Quality over quantity (rule 2):**
   - drop boilerplate (gazette mastheads, signature blocks such as `صدر بقصر السيف`, page numbers, repeated watermark lines)
   - drop chunks under 8 meaningful tokens that carry no legal content
   - dedup by `content_hash` of `normalize_for_search(text)`; near-duplicate detection (MinHash, Jaccard ≥ 0.9) within the same collection, keeping the higher-authority / newer copy
   - log every dropped chunk with the reason, for audit
8. Token counting uses the embedding model's tokenizer (via TEI `/tokenize` or the HF tokenizer), not a chars-per-token guess.

Ingestion is idempotent per `doc_id` (re-ingesting replaces that doc's units/chunks in one transaction). BM25 and HNSW indexes update incrementally. There is no full-corpus rebuild.

---

## 6. Retrieval (hybrid; must be testable on its own)

Expose `POST /api/retrieval/search` (admin/eval only) that returns ranked chunks with every intermediate score, so retrieval can be evaluated independently of generation (rule 3).

### 6.1 Filters (applied inside every SQL query)
`collection_id IN (user's collections)` AND `embedding_model = current` AND validity: `valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)` AND (unless `include_repealed`) `status <> 'repealed'`. Optional `doc_type`, `legal_domain`.

### 6.2 Per-claim candidate generation (run concurrently)
1. **Exact reference lookup:** if the claim or opinion cites `المادة N من القانون رقم X لسنة Y` (regex over normalized text + the `cited_refs` from extraction), fetch those units directly. They are **pinned** into the evidence set whatever their rank, so the verifier always sees the article the author relied on.
2. **Vector search:** embed `normalize_for_embedding(claim)` (+ question context if short), pgvector cosine, top `VECTOR_K=50`.
3. **BM25 search:** `normalize_for_search(claim)`, pg_search BM25, top `BM25_K=50`.

### 6.3 Fusion — Reciprocal Rank Fusion
`RRF(d) = Σ_lists w_list / (K + rank_list(d))`, `K = 60`, weights `w_vector = w_bm25 = 1.0` (tunable). Ranks are 1-based. Keep the top `FUSED_K=30`.

### 6.4 Rerank
Send `(claim, context_header + "\n" + chunk.text)` pairs to TEI `/rerank` (`bge-reranker-v2-m3`), truncated to the model's 512-token limit. Convert raw logits to probability: `p = sigmoid(logit)`.

### 6.5 Similarity semantics (be explicit, do not mix)
- pgvector `<=>` returns **cosine distance** `d = 1 − cos_sim`, range [0, 2] for normalized vectors.
- Cosine similarity for thresholds: `sim = 1 − d`. Normalized display score in [0,1]: `sim01 = 1 − d/2` (this is `1 − distance/max_distance` with `max_distance = 2`).
- `1/(1 + distance)` applies only to unbounded distances (L2). Not used here.
- RRF uses ranks only; raw similarities never enter the fusion formula. The rerank probability `p` is the relevance score used downstream.

### 6.6 Authority weighting (bounded — breaks ties, never overrides relevance)
Authority levels (Kuwaiti hierarchy): constitution 1.00, law 0.90, decree_law 0.90, decree 0.80, regulation 0.70, ministerial_decision 0.60, circular 0.50, court_ruling (cassation) 0.75, court_ruling (other) 0.60, legal_opinion / fatwa 0.50, commentary 0.40. Keep in config.
`final = p × (0.85 + 0.15 × authority)`.
**Old bug to not repeat:** the demo multiplied the raw (possibly negative) logit by authority, which inverted the hierarchy for weak matches. Always use the sigmoid probability.

### 6.7 Noise cut and context assembly
- Drop candidates with `p < MIN_RERANK_PROB` (default 0.15, tuned on eval).
- Keep the top `PER_CLAIM_K = 6` plus pinned exact references.
- **Parent expansion:** if a kept chunk is a `clause_split`, attach the full parent article text (capped at 1,200 tokens) as context for the LLM.
- Dedup across claims by `unit_id`. Each unique passage gets one stable ID for the review (`P1`, `P2`, …).
- **Context budget (avoid overflow):** ≤ 6,000 tokens of evidence per claim and ≤ 40,000 tokens of evidence per verification call. Claims are batched (≤ 6 claims per call) so batches can run in parallel. Log it when anything is truncated.

### 6.8 Contradiction signals
The old negation-pattern resolver is kept only as a **feature** (`negation_conflict_hint: bool`) passed to the verifier. It never removes or demotes passages. Legal conflict resolution is in Section 7.4.

---

## 7. Verification pipeline

A review job runs in the worker. Stages emit SSE progress events.

### 7.1 Claim extraction (1 Claude call)
Input: question (optional) + opinion text. Output schema per FR-3. Opinions longer than ~60k tokens are processed in sections, and claims are merged and deduplicated. Cap at `MAX_CLAIMS` (default 40). Past the cap, the review status says the opinion must be split.

### 7.2 Claim verification (⌈scored_claims / 6⌉ Claude calls, run in parallel, bounded concurrency)
System prompt (Arabic, cached) states:
- Judge only from the provided passages. No outside knowledge.
- Kuwaiti hierarchy and conflict rules.
- For each claim, output a verdict and evidence. Each evidence item has a passage ID and a **verbatim quote copied exactly from that passage**, ≤ 40 words.
- `insufficient` when the passages neither support nor contradict the claim.
- `partially_supported` when the core rule is supported but a condition, exception, number, or deadline differs. Name the difference in `reasoning_ar`.

### 7.3 Deterministic evidence validation (Python, no LLM)
For every evidence item:
1. `passage_id` must exist in the passages sent for that claim. Otherwise drop it and log `hallucinated_passage`.
2. `normalize_for_search(quote)` must be a substring of `normalize_for_search(passage.text)`. Tolerate a fuzzy match ratio ≥ 0.9 (rapidfuzz `partial_ratio`) and store the exact span from the source. Otherwise drop it and log `unverified_quote`.
3. A repealed or out-of-validity source cannot be `supports`. Relabel it as `context` with a note.
4. After validation, a claim with verdict `supported` / `partially_supported` but no remaining `supports` evidence becomes `insufficient`. A claim with verdict `contradicted` but no remaining `contradicts` evidence becomes `insufficient`.

### 7.4 Scoring and status (Python, no LLM)
- Weights: `core = 2`, `supporting = 1`. `factual_premise` claims are excluded.
- Claim value: supported 1.0, partially_supported 0.5, contradicted 0.0, insufficient 0.0.
- `score = round(100 × Σ(weight × value) / Σ weight)`.
- **Blocking contradiction:** a `contradicts` evidence item is blocking when its source is in force at the as-of date **and** its authority level ≥ the highest-authority supporting source for that claim, **or** it has the same level with a later effective date (lex posterior). A contradiction from a lower-authority source is shown as `تعارض محسوم لصالح المصدر الأعلى` (resolved conflict) and does not block. Mark possible lex-specialis cases (a special law vs. a general law at the same level) with `requires_human_judgment` and treat them as blocking.
- Status:
  - `no_information` — every scored claim is `insufficient` and there is no valid evidence at all
  - `accepted` — `score ≥ ACCEPT_THRESHOLD (90)` and zero blocking contradictions
  - `needs_review` — otherwise
- `ACCEPT_THRESHOLD` is config. Calibrate it on the verification eval set (Section 9.2) to hold the **false-accept rate** under the target.

### 7.5 Report and suggested opinion (1 Claude call, only for needs_review)
Input: the validated structured results. Output: `summary_ar` (≤ 120 words) and `suggested_opinion_ar`. The suggested opinion rewrites only contradicted/insufficient claims and cites `[P#]` markers, which are validated against the review's passages exactly like 7.3.
For `accepted`, the summary is generated by the same call type but shorter. For `no_information`, no LLM call is made and the fixed message is shown.

The report itself (claims table, supporting/contradicting references) is **rendered from structured data**, not free-written by the LLM.

### 7.6 Similar opinions
One hybrid query (Section 6) over the `opinions` corpus using the whole opinion's summary (the first 2,000 tokens of the opinion embedded), grouped by document, top 5, each with a similarity score and a 1–2 line excerpt.

### 7.7 Hallucination controls (summary)
Structured output only · temperature 0 · passages-only instruction · verbatim-quote validation · passage-ID validation · deterministic score/status · fixed no-information message · repealed-source guard · every call logged with prompt version.

---

## 8. API (FastAPI, `/api` prefix, OpenAPI documented)

- Auth: `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
- Reviews: `POST /reviews` (multipart: opinion text or file, question, as_of_date, collections) → `{review_id}`; `GET /reviews/{id}`; `GET /reviews/{id}/events` (SSE); `GET /reviews` (filters, pagination); `POST /reviews/{id}/versions` (save edit draft); `GET /reviews/{id}/versions`; `GET /reviews/{id}/diff?from=&to=`; `POST /reviews/{id}/approve` (`{version}`); `POST /reviews/{id}/reject` (`{reason}`); `GET /reviews/{id}/export?format=pdf|docx`
- Sources: `GET /sources/chunks/{id}` (full text + neighbors); `GET /sources/documents/{id}`
- Retrieval (admin/eval): `POST /retrieval/search`
- Admin: users/roles CRUD, collections + ACL, `POST /admin/ingestion/jobs` (JSONL upload), `GET /admin/ingestion/jobs/{id}`, `GET /admin/corpus/stats`, `GET /admin/eval/runs`, `GET /admin/usage`, `PATCH /admin/settings`, `POST /admin/opinions/{review_id}/publish`
- Health: `GET /health/live`, `GET /health/ready` (checks DB, Redis, TEI, embedding-model guard)

Enforce per-user daily limits (queries, tokens, cost) before enqueuing a review. Return 429 with an Arabic message when exceeded.

---

## 9. Evaluation (rule 3 — retrieval validated independently of generation)

Retrieval evaluation is **`production_rules/rule3_retrieval_eval/`** (Section 14) — do not build a second retrieval evaluator. Build only the verification evaluator as `eval/` with a CLI: `python -m eval verification --gold eval/gold/verification.jsonl`. Results are logged to MLflow and stored in `eval_runs`.

### 9.1 Retrieval eval
- Gold format: `{query_ar, relevant_unit_ids: [...], as_of_date, collection, notes}`. Target ≥ 200 queries written or validated by a legal reviewer. Include colloquial phrasing, exact article citations, synonyms, Eastern-Arabic digits, and questions whose answer is a repealed/amended article.
- Metrics: Recall@5/10/20, MRR@10, nDCG@10, **exact-article hit@6**, **repealed-leak rate** (must be 0 as supporting), **ACL-leak rate** (must be 0), latency p50/p95.
- Ablations reported in every run: vector-only, BM25-only, hybrid (RRF), hybrid + rerank, hybrid + rerank + authority.
- **Phase 1 gate:** hybrid + rerank beats both single methods on nDCG@10, and Recall@10 ≥ 0.85 (adjust the target with the client once the gold set exists).

### 9.2 Verification eval
- Gold format: `{opinion_ar, question_ar, expected_status, expected_claim_verdicts: [...], notes}`. ≥ 60 opinions, including deliberately wrong ones (wrong article, repealed law, wrong deadline/number, conflict with a higher-authority source).
- Metrics: status accuracy, **false-accept rate** (wrong opinion marked accepted — the key safety metric), claim-verdict macro-F1, quote-validation drop rate, cost and latency per review.
- Use this set to calibrate `ACCEPT_THRESHOLD` and `MIN_RERANK_PROB`.

CI runs a small smoke subset on every PR. The full eval runs on demand and before each release.

---

## 10. Frontend (new, professional gray + blue)

### 10.1 Design tokens (Tailwind theme)
- Primary blue `#1F4E79`, primary hover `#173C5E`, light blue `#E8F1FB`, accent blue `#3B82C4`
- Grays (slate): background `#F5F7FA`, surface `#FFFFFF`, border `#D9DEE5`, muted text `#5B6675`, text `#1E2733`
- Semantic (used sparingly): supports = accent blue `#3B82C4` on `#E8F1FB`; contradicts = `#B42318` on `#FDECEA`; insufficient/context = gray `#5B6675` on `#EEF1F4`; accepted badge = primary blue; needs-review badge = amber `#B54708` on `#FEF3E2`
- Radius 8px, subtle shadows, 14–16px base text, generous whitespace. No gradients, no playful colors. Dark mode optional (phase 5).
- Fully RTL: logical CSS properties, mirrored icons, Arabic numerals rendered consistently (choose Western digits for article numbers and write it in DECISIONS.md).

### 10.2 Pages
1. **Login.**
2. **Reviews (home):** table of reviews — title/first line, status badge, score, date, owner, reviewer; filters; "مراجعة جديدة" button.
3. **New review:** question/facts textarea (optional); opinion textarea **or** drag-and-drop file; as-of date picker; collection scope; submit → navigates to the result page.
4. **Review result:**
   - Header: status badge, a large score (e.g. `87 / 100`), and a live stage stepper while processing.
   - Action bar: `accepted` → "تصدير" (export); `needs_review` → **اعتماد** and **تعديل واعتماد** (plus رفض); `no_information` → the fixed message, with تعديل واعتماد / رفض available.
   - Tabs: **الملخص** (summary) · **تحليل الادعاءات** (claim table: claim, type, verdict chip, evidence count, expandable reasoning + evidence) · **المراجع** (two columns: مؤيدة | معارضة; each card shows the doc title, number/year, article, status tag, ≤ 40-word quote, and "عرض النص الكامل", which opens a side drawer with the full article highlighted) · **آراء مشابهة** · **الرأي المقترح** (only for needs_review).
5. **Editor (sub page `/reviews/:id/edit`):** split layout. Main area: TipTap RTL editor preloaded with the suggested opinion (or the original opinion when there is none). Side panel: references list with "إدراج استشهاد" (insert citation). Toolbar: حفظ مسودة, عرض الفروقات (diff vs the AI version), اعتماد (confirm dialog → creates version + approval → back to the result page).
6. **Admin:** users/roles, collections and ACL, ingestion jobs (upload JSONL, progress, per-row errors), corpus stats, eval runs (metrics table + ablation chart), usage and cost, settings (thresholds, REQUIRE_HUMAN_SIGNOFF).

Accessibility: keyboard navigable, focus rings, WCAG AA contrast with the palette above.

---

## 11. Migration from the old demo

**Delete entirely (do not port):** `orchestrator.py`, `agent_state.py`, `rag_tool.py`, `agents/`, the `/query-v2` route, `call_provider` and the Gemini/Cohere/OpenRouter/Groq clients, `PROVIDER_ROUTING`, LangGraph and the extra provider keys in requirements, docker-compose, and `.env`, `_enforce_format`, `chat_history/sessions.json`, the SQLite `users.db` (migrate the users with a one-off script), ChromaDB, the in-memory BM25 (`rank_bm25`), `semantic_chunk_arabic_text` (it merged articles across boundaries), and the whole vanilla-JS frontend.

**Reuse as reference (rewrite into the new structure):**
- `contradiction_resolver.KUWAITI_LEGAL_HIERARCHY` → the authority config (Section 6.6)
- `contradiction_resolver` negation patterns → the feature only (Section 6.8)
- `ingest.ARABIC_SEPARATORS` and `extract_article_number` → reference for the clause splitter and exact-reference regex
- `ingest.clean_document_text` (watermark-line dedup) → boilerplate removal
- `ocr_pipeline.py` → the worker OCR for uploaded scanned opinions
- `user_repository` limit logic (daily queries/tokens/cost) → the new limits service

Corpus: the client's new preprocessed JSONL replaces the old `data/docs` ingestion.

---

## 12. Delivery phases (each ends with its acceptance check)

| Phase | Scope | Done when |
|---|---|---|
| P0 Foundation | Repo layout, Docker Compose, config, Alembic schema, auth/RBAC, Arabic normalizer + tests, embedding-model guard, TEI wiring, health checks | `docker compose up` works; guard blocks a mismatched model; normalizer tests pass |
| P1 Ingestion + retrieval | JSONL contract, chunker (Section 5.5) + tests, indexing, exact-ref lookup, hybrid search, RRF, rerank, authority, filters, `/retrieval/search`, eval harness 9.1 | All three `production_rules/` checks exit 0 (Section 14); ACL-leak and repealed-leak = 0 |
| P2 Verification | Worker job, claim extraction, verification, evidence validation, scoring/status, report + suggested opinion, similar opinions, SSE, llm_calls logging, eval harness 9.2 | False-accept rate on the gold set is within the target; ACCEPT_THRESHOLD calibrated |
| P3 Frontend | Design system, all pages in 10.2 except the editor | End-to-end review works in the UI |
| P4 Review workflow | Editor, versions, diff, approve/reject, audit, export PDF/DOCX, publish-to-corpus | Every action creates immutable records; export includes references |
| P5 Hardening | OTel traces, Prometheus/Grafana dashboards, load test (dozens of concurrent reviews), backups (pg_dump + WAL), rate limits, security review | NFR-1 latency met under load; restore-from-backup tested |

## 13. Repo layout

```
legal-rag-v3/
  backend/
    app/
      api/            # routers
      core/           # config, security, logging, otel
      db/             # models, session, alembic
      text/           # arabic.py normalizer, tokenization
      ingestion/      # contract.py, chunker.py, dedup.py, indexer.py
      retrieval/      # vector.py, bm25.py, fusion.py, rerank.py, authority.py, exact_ref.py, assemble.py
      verification/   # extract.py, verify.py, validate.py, scoring.py, report.py, prompts/
      llm/            # claude_client.py (retry, caching, structured output, cost)
      workers/        # arq tasks
      services/       # reviews, approvals, export, limits
    tests/
  production_rules/   # supplied — rule 1/2/3 checks (Section 14), do not modify thresholds
  eval/               # verification eval only
    gold/  runners/  metrics.py
  frontend/
    src/ (pages, components, api, theme)
  deploy/
    docker-compose.yml  nginx.conf  prometheus.yml  grafana/
  docs/
    ARCHITECTURE.md  DECISIONS.md  INGESTION_CONTRACT.md  RUNBOOK.md
```

## 14. Production rules — mandatory contract and checks

A folder `production_rules/` is supplied with this brief. Copy it into the repo root unchanged. It contains three standalone checks that run against a live deployment:

| Rule | Check | Must pass |
|---|---|---|
| 1. Same embedding model everywhere | `rule1_embedding_consistency/check_embedding_consistency.py` | After every ingestion job, every deploy, in CI |
| 2. Embedding quality > quantity | `rule2_embedding_quality/check_corpus_quality.py` | After every ingestion job |
| 3. Test retrieval separately | `rule3_retrieval_eval/run_retrieval_eval.py` | Every retrieval change, every release, nightly |

Your backend **must expose exactly this contract**, or the checks fail:

1. Table `system_meta(key text primary key, value text)` with keys `embedding_model`, `embedding_dim`, `normalizer_version`.
2. Column names on `chunks`: `id, unit_id, document_id, collection_id, chunk_kind, context_header, text, text_norm, token_count, embedding, embedding_model, doc_type, status, content_hash`. On `units`: `id, article_number`. On `documents`: `id, doc_type, status`.
3. Module `app/retrieval/embedder.py` with these public functions. They are the **only** code path used for embeddings, in both ingestion and query:
   - `build_passage_input(chunk_row: dict) -> str` — exact text that gets embedded at ingestion (context header + normalized text + any model prefix)
   - `build_query_input(query: str) -> str` — exact text that gets embedded at query time
   - `embed_texts(texts: list[str]) -> list[list[float]]` — calls TEI, returns normalized vectors
4. `POST /api/retrieval/search` (admin/eval roles) with body `{query, as_of_date, collections, mode, top_k, include_repealed}`, where `mode ∈ {vector, bm25, hybrid, hybrid_rerank, full}` (`full` = the production pipeline incl. exact-ref pinning, authority, and noise cut). Response: `{results: [{chunk_id, unit_id, collection_id, status, score}], latency_ms}`. When `collections` is null, the server scopes results to the caller's ACL.
5. Gold sets: `production_rules/rule3_retrieval_eval/gold/retrieval_gold.jsonl` (the template shows the format and categories). `relevant_unit_ids` reference unit IDs, not chunk IDs. Amended-article queries carry `wrong_version_unit_ids`.

Add a CI job that runs rule 1 and rule 2 against the seeded staging DB, and rule 3 on the smoke subset. The Phase 1 gate (Section 12) = all three checks exit 0 on the real gold set. Never change a threshold inside `production_rules/` to make a build pass; fix the pipeline or the data.

## 15. Out of scope for v1
Free-form legal Q&A chat (the retrieval layer supports it later), multi-language UI, fine-tuning any model, and automatic corpus crawling (the client's separate preprocessing handles corpus preparation).

---

**Start with P0. After each phase, report: what was built, test results, eval numbers (from P1 on), and any DECISIONS.md entries.**
