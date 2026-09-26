# Runbook

## First-time boot

```bash
cd legal-rag-v3
cp .env.example .env
# Set SECRET_KEY (openssl rand -hex 32) and ADMIN_PASSWORD.
docker compose -f deploy/docker-compose.yml up -d
docker compose logs -f v3_api    # wait for "ready"
```

Ports: API 8100, Postgres 5532, MinIO console 9101, Grafana 3100.

## Health

```bash
curl http://localhost:8100/health/live
curl http://localhost:8100/health/ready
```

## First login

```bash
curl -X POST http://localhost:8100/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=$ADMIN_PASSWORD"
```

## Rule 1 drift drill

```bash
docker compose exec v3_postgres psql -U legalrag legalrag \
  -c "UPDATE system_meta SET value='wrong-model' WHERE key='embedding_model';"
docker compose restart v3_api
docker compose logs v3_api | tail
# Expect: exit code 2, "Rule 1 violation" / "انتهاك القاعدة 1"
```

Reset:
```bash
docker compose exec v3_postgres psql -U legalrag legalrag \
  -c "UPDATE system_meta SET value='BAAI/bge-m3' WHERE key='embedding_model';"
docker compose restart v3_api
```

## Backup

```bash
docker compose exec v3_postgres pg_dump -U legalrag legalrag > backup.sql
```

MinIO: `mc mirror` to a remote S3 bucket.

## Model swap (P1+)

1. Add shadow column `embedding_shadow vector(N)` in a migration.
2. Re-embed all chunks into shadow (worker job).
3. Run Rule 3 eval on shadow.
4. Atomically: update `system_meta.embedding_model` + rename shadow → embedding in one migration.

Never mix embeddings from two models.

## v2 → v3 user migration (cutover-time)

`deploy/scripts/migrate_v2_users.py` (P4). Reads v2 `users.db`, transforms rows,
inserts. v2 uses bcrypt; v3 uses argon2id → users go through a one-time password
reset flow at cutover.

## Rollback

Roll back the API image; data untouched. Schema rollback: restore from `pg_dump`.

## Ingest a corpus (P1)

1. Create a collection: `POST /api/v1/admin/collections {"name": "legislation"}` → integer `id`.
2. Upload JSONL (contract: `docs/INGESTION_CONTRACT.md`):
   `curl -H "Authorization: Bearer $TOKEN" -F collection_id=1 -F file=@corpus.jsonl http://localhost:8100/api/v1/admin/ingestion/jobs`
3. Poll `GET /api/v1/admin/ingestion/jobs/{job_id}` until `completed`; `stats` lists row errors and dropped chunks with reasons.
4. Grant access: `PUT /api/v1/admin/users/{id}/collections {"collection_ids": [1]}`.

Dev corpus from local files (not the real corpus):
`cd backend && python -m tools.pdf_to_jsonl FILE --doc-id ID --doc-type law --title "..." --number 6 --year 2010 --mode articles > corpus.jsonl`

## Production rules (after every ingestion / deploy)

```bash
pip install -r production_rules/requirements.txt
export DATABASE_URL=postgresql://legalrag:legalrag@localhost:5532/legalrag \
       EMBEDDING_MODEL=BAAI/bge-m3 EMBEDDING_DIM=1024 NORMALIZER_VERSION=v1 \
       TEI_EMBED_URL=http://localhost:8180 BACKEND_PATH=./backend \
       POSTGRES_HOST=localhost POSTGRES_PORT=5532 SECRET_KEY=... ADMIN_PASSWORD=...
python -m production_rules.rule1_embedding_consistency.check_embedding_consistency
python -m production_rules.rule2_embedding_quality.check_corpus_quality
# rule 3: API_URL=http://localhost:8100 API_ADMIN_TOKEN=... API_RESTRICTED_TOKEN=... RESTRICTED_ALLOWED_COLLECTIONS=2
python -m production_rules.rule3_retrieval_eval.run_retrieval_eval --gold production_rules/rule3_retrieval_eval/gold/retrieval_gold.jsonl
```
Note: `production_rules/.env.example` says `NORMALIZER_VERSION=1`; v3 stores `v1` — set `v1`.

## Load / reload the Kuwaiti legislation corpus

```bash
cd backend
python -m tools.md_to_jsonl /path/to/JEZAALOTAIBI-15.md > kw_corpus.jsonl   # 72 laws
# Admin UI → الإدارة → استيراد المصادر → upload kw_corpus.jsonl into «التشريعات الكويتية»
# (or split into several files; re-ingesting a law replaces it — idempotent per doc_id)
```
On CPU TEI a full load takes ~45–60 min. Then run production rules 1 and 2.
