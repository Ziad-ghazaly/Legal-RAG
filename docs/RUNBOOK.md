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
