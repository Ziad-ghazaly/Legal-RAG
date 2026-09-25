# Architecture — Legal-RAG v3

## Diagram (P0)

```
                                        v3_prometheus  ◄─── /metrics
Client → 8100 → [ v3_api (FastAPI) ]
                     │
   ┌─────────────────┼───────────────────┬────────────────────┐
   ▼                 ▼                   ▼                    ▼
 v3_pgbouncer      v3_redis           v3_minio            v3_tei_embed
   │                 │                                     v3_tei_rerank
   ▼                 ▼
 v3_postgres     v3_worker (arq)
  (ParadeDB)
```

## Request lifecycle (P0)

1. Client → `POST /api/v1/auth/login` (form-urlencoded).
2. `RequestIdMiddleware` binds a `request_id` to structlog context.
3. `get_session` opens an async session.
4. Handler verifies password, issues access + refresh tokens.
5. Refresh row stored (hashed) in Postgres.

## Lifespan (startup)

1. `configure_logging()` → `init_otel()` → `enforce_rule_one()` → `seed_admin()` → ready.
2. Rule-1 mismatch → `SystemExit(2)`.

## Cross-refs

- `CONTEXT.md` — ubiquitous language.
- `docs/DECISIONS.md` — non-obvious calls.
- `docs/RUNBOOK.md` — deploy / restore / re-embed.
- `docs/DEBUG_ARTIFACTS.md` — ingestion debug layout (P1).
- `docs/INGESTION_CONTRACT.md` — JSONL contract (P1).
