# Rule 1 — Same embedding model everywhere

**Rule:** ingestion, indexing, and query use the exact same embedding model, dimension, input format (prefixes, context header, normalization), and serving endpoint. A mismatch doesn't crash anything. It silently returns wrong results, which is why it needs its own check.

## What can go wrong
- The corpus is embedded with model A, but queries are embedded with model B after a config change or a new container.
- The same model is used with different input formats (e.g. E5 without the `query:`/`passage:` prefixes, or the context header added at ingest but a different header at re-embed).
- The normalizer changed (new version) but the old vectors were kept.
- Mixed batches: half the corpus re-embedded with a new model.
- The TEI container serves a different model than the config says.

## How v3 enforces it (design)
1. One config object holds `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `NORMALIZER_VERSION`.
2. One `Embedder` module (`app/retrieval/embedder.py`) builds passage input, builds query input, and calls TEI. Ingestion and query both import it. Nothing else calls TEI for embeddings.
3. `system_meta` stores the locked values. API and workers refuse to start on mismatch.
4. Every chunk row stores `embedding_model`. Queries filter `embedding_model = current`.
5. A model change is a migration: re-embed into a shadow column → run rule 3 → atomic swap.

## Check: `check_embedding_consistency.py`

| # | Check | Pass criterion |
|---|---|---|
| 1 | Config vs `system_meta` | `embedding_model`, `embedding_dim`, `normalizer_version` all equal |
| 2 | TEI serves the configured model | TEI `/info` `model_id` == `EMBEDDING_MODEL` |
| 3 | One model in the corpus | `SELECT DISTINCT embedding_model FROM chunks` returns exactly the configured one |
| 4 | No missing vectors | `embedding IS NULL` count = 0 |
| 5 | One dimension | `vector_dims(embedding)` is the same everywhere and = `EMBEDDING_DIM` |
| 6 | Vectors normalized | sampled L2 norm within 1 ± 0.001 |
| 7 | **Re-embed round trip** | re-embed N sampled chunks through the app's own `build_passage_input` + `embed_texts`; cosine(stored, fresh) ≥ 0.999 for ≥ 99% of the sample. Catches any input-format drift. |
| 8 | **Self-retrieval probe** | for N sampled chunks, embed `build_query_input(chunk text)` and run a pgvector search; the chunk itself is top-1 for ≥ 95%. Catches query/passage asymmetry (wrong prefixes, wrong normalizer on the query side). |

Run it after every ingestion job, after every deploy, and in CI against a staging DB. A failure blocks release.
