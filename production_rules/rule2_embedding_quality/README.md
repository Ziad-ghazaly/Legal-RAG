# Rule 2 — Embedding quality > quantity

**Rule:** a smaller corpus of clean, correctly bounded, deduplicated, metadata-complete chunks beats a large noisy one. Every junk vector is a candidate that can outrank a real article. In legal work a wrong top-ranked chunk becomes a wrong citation.

## What produces noisy vectors
- Duplicates (the same law ingested twice, gazette reprints, near-identical amendment copies). They crowd the top-k with one source.
- Merged articles (two articles in one chunk). The citation becomes ambiguous and the vector gets diluted.
- Oversized chunks: meaning is diluted, and the reranker truncates them at 512 tokens.
- Tiny or empty chunks, boilerplate (mastheads, signatures, page numbers, watermarks).
- OCR garbage / low-Arabic-ratio text.
- Missing legal metadata (article number, context header). The chunk can't be cited or filtered.

## How v3 enforces it (design)
Article-aware chunking, clause split, context headers, boilerplate removal, exact + near-duplicate dedup, a minimum-content filter, and a drop log with reasons. All at ingestion, before embedding.

## Check: `check_corpus_quality.py`

Thresholds live at the top of the script. Tighten them once your data is clean.

| # | Check | Default pass criterion |
|---|---|---|
| 1 | Exact duplicates (same `content_hash` in a collection) | 0 groups |
| 2 | Near-duplicates (sampled nearest neighbour, cosine ≥ 0.98, different unit) | ≤ 1% of sample |
| 3 | Tiny chunks (< 8 tokens) | ≤ 0.5% |
| 4 | Oversize chunks (> `MAX_CHUNK_TOKENS`, default 450; tables excluded) | ≤ 1% |
| 5 | Chunks over the reranker limit (> 512 tokens) | 0 |
| 6 | Merged articles (an `article` chunk with ≥ 2 article headings inside) | 0 |
| 7 | Legislation article chunks with no `article_number` | 0 |
| 8 | Chunks with an empty `context_header` | 0 |
| 9 | Low Arabic ratio (< 0.6 of letters) | ≤ 1% |
| 10 | Orphans (chunk without unit/document) | 0 |
| 11 | Repeated text across many documents (boilerplate candidates) | **warn only**; listed for manual review |
| 12 | Token-length distribution, chunks per document type | **info**, for tracking drift between batches |

Run it after every ingestion job. A failed check means you fix the preprocessing or the chunker; you do not raise the threshold.
