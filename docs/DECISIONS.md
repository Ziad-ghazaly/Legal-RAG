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
