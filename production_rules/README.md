# Production Rules

Three standalone checks. Copy content from the brief supplier unchanged.
**Never edit thresholds here to make a build pass** — fix pipeline or data.

| Rule | Purpose | Cadence |
|---|---|---|
| 1 | Same embedding model everywhere | After ingestion, deploy, CI |
| 2 | Chunk quality > quantity          | After every ingestion job |
| 3 | Test retrieval separately        | Every retrieval change, release, nightly |

P1 acceptance gate = all three exit 0 on the real gold set.

## App contract for checks

- `system_meta(key, value)` with keys `embedding_model`, `embedding_dim`, `normalizer_version`.
- Tables per spec §5.2.
- `app/retrieval/embedder.py` — `build_passage_input`, `build_query_input`, `embed_texts` (only embedding path).
- `POST /api/retrieval/search` (admin/eval) with `mode ∈ {vector, bm25, hybrid, hybrid_rerank, full}`. Lands in P1.

Gold set: `rule3_retrieval_eval/gold/retrieval_gold.jsonl`. `relevant_unit_ids` = unit IDs.
