# Decisions

Append-only log.

- **D-001** v3 repo location: sibling `C:\Users\ziadg\Demo_RAG\legal-rag-v3\`.
- **D-002** New GitHub repo for v3; v2 kept as reference.
- **D-003** P0 backend-only; `frontend/` scaffolded empty for P3.
- **D-004** v2-user migration is a cutover-time task (P4/P5), not P0.
- **D-005** Password hashing = argon2id (PHC winner).
- **D-006** `NORMALIZER_VERSION = "v1"`.
- **D-007** Default embedding model = `BAAI/bge-m3`; may swap post-P1 eval.
- **D-008** UI digits = Western.
- **D-009** All containers/ports/volumes prefixed `v3_`.
- **D-010** No code lifted from v2/v1 — concepts + `.md` only.
- **D-011** `pyproject.toml` only; no `requirements.txt`.
- **D-012** Debug bucket retention: 90 days (config).
- **D-013** 401 for auth failures; 403 for insufficient role.
- **D-014** Refresh rotation atomic: revoke old + insert new in same transaction.
- **D-015** MinIO not in P0 `/ready` check (bucket created in P1).
- **D-016** Alembic 0001 has no downgrade (baseline).
- **D-017** Models use `sa.JSON` (portable) not `JSONB`; migration still uses `JSONB` on Postgres.
- **D-018** Models use `func.now()` (portable) not `server_default="now()"`.
- **D-019** `session.py` engine created lazily so tests can monkeypatch before asyncpg is loaded.
- **D-020** Auth-router tests exercise only 5 auth tables against SQLite; Postgres-native tables (chunks with `vector`, docs/units/reviews with `ARRAY`) are validated only via the docker-compose acceptance walkthrough.
- **D-021** P1 ingests the brief's **JSONL contract** (§5.1). The earlier PDF/DOCX v2-port draft is parked on local branch `p1-draft-v2port`. `backend/tools/pdf_to_jsonl.py` is a dev-only converter.
- **D-022** `collections.id` is an **integer** (migration 0002): `production_rules` rule 3 casts `collection_id` to int and its gold uses `[1]`.
- **D-023** `embedder.embed_texts` is **synchronous** (rule 1 calls it without await); the app awaits `aembed_texts`. Same TEI call, same checks.
- **D-024** `chunks.text_norm = normalize_for_search(context_header + "\n" + text)` so BM25 covers header + text without a second index column.
- **D-025** ParadeDB pinned `0.25.10-pg16`; TEI `cpu-1.9` with `--max-batch-tokens 2048` (1.5 cannot download from HF; OOM at warm-up with defaults).
- **D-026** MinIO image `pgsty/minio` (Docker Hub removed `minio/minio` in 2026-09; quay requires auth). Network alias `minio` because botocore rejects `_` in hostnames. No SSE until a KMS is configured.
- **D-027** PgBouncer `AUTH_TYPE=scram-sha-256`; asyncpg statement cache off + unique prepared-statement names (transaction pooling).
- **D-028** DEBUG_ARTIFACTS (8 files/doc) not built; ingestion job `stats` carry row errors, doc errors, and every dropped chunk with its reason.
- **D-029** Exact-reference pinning requires law number + year; bare `المادة N` is not pinned (ambiguous across laws).
- **D-030** Rerank batches of 8 with `TEI_RERANK_TIMEOUT_S` (default 120 s): CPU TEI takes ~1.6 s per 512-token pair. The rule-3 latency gate (p95 ≤ 1.5 s) needs the GPU TEI image.
- **D-031** Semantic chunking uses sentence packing with 1-sentence overlap (not the embedding-breakpoint method); upgrade if rule 2/3 show a need.
- **D-032** CI runs lint + unit + integration (ParadeDB service, fake TEI). Production rules run against a live stack (see RUNBOOK), not in CI.
