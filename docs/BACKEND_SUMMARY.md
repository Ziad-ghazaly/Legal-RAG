# Legal-RAG v3: Backend Logic and Changes vs v1

## 1. v3 backend logic (one request, end to end)

```
POST /api/reviews  (opinion text/file + optional question + as-of date)
  │  auth (JWT + RBAC) → daily limits → create review row → enqueue job → return review_id
  ▼
WORKER JOB  (progress streamed to UI over SSE)
  1. Parse        file → text (PyMuPDF / python-docx / OCR for scans)
  2. Extract      Claude call #1 → claims[] {text, type, core|supporting, cited_refs}
  3. Retrieve     per claim, in parallel:
                    exact ref lookup (المادة N من القانون X لسنة Y) → pinned
                    vector (pgvector, BGE-M3)  top 50 ┐
                    BM25   (pg_search, Arabic) top 50 ┴→ RRF (k=60) → top 30
                    → rerank (bge-reranker-v2-m3) → sigmoid
                    → × bounded authority (0.85 + 0.15·authority)
                    → drop p < 0.15 → top 6 + pinned → parent-article expansion
                  all filters (ACL, as-of validity, repealed, model) run INSIDE SQL
  4. Verify       Claude calls #2..n (≤6 claims/call, parallel)
                    → per claim: verdict + evidence {passage_id, supports|contradicts, verbatim quote}
  5. Validate     Python: passage_id exists? quote is really in the source?
                    repealed source cannot support → drop or relabel invalid evidence
  6. Score        Python: weighted claims (core=2, supporting=1) → 0–100
                    blocking contradiction = in-force source with authority ≥ the supporting source
  7. Status       Python: no_information | accepted (≥90 & no blocking) | needs_review
  8. Report       Claude call #last (only needs_review/accepted): short summary + suggested corrected opinion
                  the references and claims table are rendered from data, not free text
  9. Similar      one hybrid search over the opinions corpus → top 5
  ▼
REVIEW PAGE → approve | edit & approve (editor page) | reject → immutable versions + approvals + audit
```

LLM calls per review: 1 extraction + ⌈claims/6⌉ verification (parallel) + 1 report. For a typical 10-claim opinion that is 4 calls, 2 of them concurrent. Claude Sonnet 4.5 is the only provider.

---

## 2. What changed vs v1 `/query`

| Area | v1 `/query` | v3 |
|---|---|---|
| Purpose | Answer a question | Verify a legal opinion, score it, route it to approval |
| Input | One question string | Opinion (text/PDF/DOCX) + optional question + as-of date |
| Execution | Synchronous inside the HTTP request | Background worker job + SSE progress; the API stays stateless |
| LLM | Claude → Groq (ALLaM-7B) fallback | Claude Sonnet 4.5 only; retry with backoff, then a clean error |
| LLM output | Free-text Arabic with forced headers | Structured JSON (tool use / schema), temperature 0 |
| Retrieval unit | Whole question, one search | Per claim, plus exact lookup of cited articles |
| Citations | `_enforce_format` appends a sources block when missing (cosmetic) | Every quote checked verbatim against the source in Python; invalid evidence dropped |
| Decision | None (the answer is the output) | Deterministic score 0–100 + status (accepted / needs review / no information) |
| References | Every retrieved chunk listed | Only validated evidence, split into supporting vs contradicting, each with a ≤40-word quote |
| No-answer case | Prompt instruction only | Fixed message when no claim has valid evidence; no LLM call |
| Human loop | None | Approve / edit & approve / reject, versions, diff, audit, export |
| Storage | SQLite users + JSON file chat history + Chroma | PostgreSQL (users, corpus, vectors, BM25, reviews, audit) + S3 for files + Redis queue |
| Cost tracking | Claude-only math, wrong for other providers | Per-call log (tokens, cost, latency, prompt version) |
| Observability | MLflow run per request | OTel traces + Prometheus/Grafana; MLflow kept for offline eval only |
| UI | Vanilla JS chat | React + TS, RTL, gray/blue, review workflow pages |

**Removed completely:** `/query-v2`, LangGraph orchestrator, the 4 agents, `rag_tool.py`, `agent_state.py`, the Groq/Gemini/Cohere/OpenRouter clients, `PROVIDER_ROUTING`, `_enforce_format`, `sessions.json`, ChromaDB, in-memory `rank_bm25`, the vanilla frontend.

---

## 3. What changed in the RAG layer

| Stage | v1 | v3 | Why |
|---|---|---|---|
| Source data | Raw PDFs/DOCX in `data/docs`, parsed at ingest | Your preprocessed JSONL (doc metadata + one unit per article) | Parsing and OCR move out of the serving path; clean input |
| Legal metadata | Filename, article number (regex guess) | doc_type, number/year, authority, status (in force/amended/repealed), validity dates, hierarchy path | Needed for repealed-law guard, as-of dates, and conflict rules |
| Chunking | `semantic_chunk_arabic_text`: greedy sentence grouping at cos>0.7; articles could merge or split | One article = one chunk. Long articles are split at clause markers (أولاً، (أ)، البند…), then semantic breakpoints. Opinions/rulings are section-aware + semantic | Every chunk maps to exactly one citation |
| Chunk text | Raw text | Context header prepended: `قانون: … — الباب … — المادة 41` | Short articles become findable; the LLM knows where each chunk comes from |
| Normalization | Ad-hoc cleaning | One versioned module: search normalizer (alef/ya/ta-marbuta, tashkeel, Eastern digits → Western) and a lighter embedding normalizer, used identically at index and query time | `المادة ٤١` matches `المادة 41`; no index/query drift |
| Embedding model | multilingual-e5-large, 512-token limit, loaded in the API process | BGE-M3 (8192 tokens) by default, chosen by eval vs E5; served by TEI; locked in `system_meta` | Long articles are no longer truncated; rule 1 is enforced |
| Vector store | Chroma (local folder) | pgvector HNSW in Postgres | Backups, migrations, SQL filters, multi-user |
| Keyword search | `rank_bm25` over the full corpus in RAM, rebuilt on every ingest, ACL filtered after scoring | pg_search real BM25 with an Arabic tokenizer, incremental, ACL filtered inside SQL | Scales; no ACL leakage |
| Filters | folder_id only | ACL + as-of validity + repealed + embedding model, all pre-filter | Correct legal time slice |
| Exact citations | None | A cited article is fetched directly and always shown to the verifier | Checks the article the author actually relied on |
| Fusion | RRF k=60 over top 15 each | RRF k=60 over top 50 each, weighted, top 30 kept | More recall before rerank |
| Rerank | 12 pairs, text truncated to 500 chars | 30 pairs, header + text up to the 512-token limit, GPU | Better precision |
| Authority | `raw_logit × authority`: **bug**, negative logits inverted the hierarchy | `sigmoid(logit) × (0.85 + 0.15·authority)` | Authority breaks ties, never overrides relevance |
| Noise cut | None (MIN_RELEVANCE = 0) | Drop rerank prob < 0.15 (tuned on eval) | Retrieval noise out |
| Contradictions | Negation regex removed chunks | Regex is only a hint; Claude labels stance, Python applies hierarchy + later-law rules | The regex was brittle; it no longer deletes evidence |
| Context | Global top 8, 6,000-char cap (~3–4 chunks actually used) | Per claim: 6 passages + parent article, ≤6k tokens/claim, ≤40k/call, batched | No overflow, nothing silently dropped |
| Evaluation | None | Separate retrieval eval + verification eval with gates | Rule 3 |

---

## 4. The five failure modes and where v3 blocks each

| Failure | Blocked by |
|---|---|
| Bad chunking | Article-aware structural chunker, clause split, context headers, quality audit (rule 2 check) |
| Embedding mismatch | Single `Embedder`, `system_meta` lock, startup refusal, consistency check (rule 1 check) |
| Retrieval noise | SQL pre-filters, rerank threshold, dedup, boilerplate removal, bounded authority |
| Context overflow | Per-claim budgets, batching, parent expansion capped, truncation logged |
| Hallucination | Structured output, passage-ID check, verbatim-quote check, deterministic score/status, fixed no-info message |

## 5. Production rules

Each rule has its own folder under `production_rules/` with an explanation, pass/fail criteria, and a runnable check script. See `production_rules/README.md`.
