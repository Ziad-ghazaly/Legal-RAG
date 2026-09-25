# Production Rules — Checks

Three rules, three independent checks. Each check is a standalone script you run against a live v3 deployment (Postgres + TEI + API). Each exits `0` on pass and `1` on fail, and writes a JSON + Markdown report to `reports/`.

| Rule | Folder | Script | When to run |
|---|---|---|---|
| 1. Same embedding model everywhere | `rule1_embedding_consistency/` | `check_embedding_consistency.py` | After every ingestion job, after every deploy, in CI |
| 2. Embedding quality > quantity | `rule2_embedding_quality/` | `check_corpus_quality.py` | After every ingestion job, before accepting a new data batch |
| 3. Test retrieval separately | `rule3_retrieval_eval/` | `run_retrieval_eval.py` | Every retrieval change, before every release, nightly |

## Setup

```bash
pip install -r production_rules/requirements.txt
cp production_rules/.env.example production_rules/.env   # fill in the values
```

Run from the repo root:

```bash
python -m production_rules.rule1_embedding_consistency.check_embedding_consistency
python -m production_rules.rule2_embedding_quality.check_corpus_quality
python -m production_rules.rule3_retrieval_eval.run_retrieval_eval --gold production_rules/rule3_retrieval_eval/gold/retrieval_gold.jsonl
```

## Contract these checks assume (the v3 backend must provide it)

- Table `system_meta(key text primary key, value text)` with keys `embedding_model`, `embedding_dim`, `normalizer_version`.
- Table `chunks` with at least: `id`, `unit_id`, `document_id`, `collection_id`, `chunk_kind`, `context_header`, `text`, `text_norm`, `token_count`, `embedding vector(N)`, `embedding_model`, `doc_type`, `status`, `content_hash`.
- Table `units` with `id`, `article_number`; table `documents` with `id`, `doc_type`, `status`.
- Python functions importable from the backend (rule 1 calls the **same** code path the app uses — that's the point):
  - `app.retrieval.embedder.build_passage_input(chunk_row: dict) -> str`
  - `app.retrieval.embedder.build_query_input(query: str) -> str`
  - `app.retrieval.embedder.embed_texts(texts: list[str]) -> list[list[float]]`
- Endpoint `POST /api/retrieval/search` (admin/eval only), body `{query, as_of_date, collections, mode, top_k, include_repealed}` with `mode ∈ {vector, bm25, hybrid, hybrid_rerank, full}`, response `{results: [{chunk_id, unit_id, collection_id, status, score}], latency_ms}`.

If any of these is missing, the check fails loudly. It never skips silently.
