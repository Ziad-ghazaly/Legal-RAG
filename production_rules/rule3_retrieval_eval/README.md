# Rule 3 — Test retrieval separately

**Rule:** validate retrieval on its own, with no LLM in the loop, using metrics that match this use case. If the right article isn't in the passages, Claude cannot verify the opinion correctly, and a generation-level test won't tell you whether retrieval or the prompt is at fault.

## Gold set (you + a legal reviewer own this)
File: `gold/retrieval_gold.jsonl`. One line per query:

```json
{"id": "q001", "query_ar": "...", "relevant_unit_ids": ["kw-law-6-2010/a41"], "as_of_date": "2026-09-01",
 "collections": [1], "category": "paraphrase", "include_repealed": false}
```

- `relevant_unit_ids` are **unit IDs** (articles), not chunk IDs, so the gold set survives re-chunking.
- Target ≥ 200 queries. Cover these `category` values so you can see where retrieval breaks:
  - `exact_citation` — the query names the article (`المادة 41 من قانون العمل`)
  - `paraphrase` — the rule in different words, no article cited
  - `colloquial` — the way a client would phrase it
  - `digits_eastern` — uses ٠-٩
  - `amended` — the answer is an amended article; `as_of_date` decides which version is correct
  - `repealed_trap` — the obvious match is repealed; the correct unit is the replacement
  - `multi_article` — needs 2+ articles
  - `claim` — an actual claim sentence taken from a real opinion (this is what v3 retrieves with)
- Start with the template: 10 example lines showing each category. Replace them with real ones.

## Metrics (domain-specific, not just generic IR)

| Metric | Meaning | Gate (default) |
|---|---|---|
| Recall@5 / @10 / @20 | share of relevant units found in top k | Recall@10 ≥ 0.85 (`full` mode) |
| MRR@10 | how high the first relevant unit ranks | info |
| nDCG@10 | ranking quality | `full` beats `vector` and `bm25` |
| **Evidence hit@6** | at least one relevant unit in the top 6 — exactly what the verifier sees per claim | ≥ 0.90 |
| **Exact-citation hit@1** | for `exact_citation` queries, the cited article is rank 1 | ≥ 0.98 |
| **As-of correctness** | for `amended` queries, the version valid at `as_of_date` is ranked above the other versions | ≥ 0.95 |
| **Repealed leak rate** | a repealed unit in the results when `include_repealed=false` | **0** |
| **ACL leak rate** | the restricted user gets a chunk from a collection they can't access | **0** |
| Latency p50 / p95 per mode | from the API's `latency_ms` | p95 ≤ 1,500 ms (`full`) |

Everything is reported **per mode** (`vector`, `bm25`, `hybrid`, `hybrid_rerank`, `full`) and **per category**. The ablation shows whether each stage earns its latency.

## Run

```bash
python -m production_rules.rule3_retrieval_eval.run_retrieval_eval \
    --gold production_rules/rule3_retrieval_eval/gold/retrieval_gold.jsonl \
    --modes vector,bm25,hybrid,hybrid_rerank,full
```

`python -m production_rules.rule3_retrieval_eval.metrics` runs the metric self-tests.

Tune `VECTOR_K`, `BM25_K`, the RRF weights, `MIN_RERANK_PROB` and the authority blend **only** against this set, and commit the report with each change.
