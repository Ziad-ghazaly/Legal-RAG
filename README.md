# Legal-RAG v3

Kuwaiti Legal Opinion Verification Platform. Production rewrite of the v1/v2 demo.

- Design spec: `docs/superpowers/specs/2026-09-25-legal-rag-v3-p0-design.md`
- Ubiquitous language: `CONTEXT.md`
- Runbook: `docs/RUNBOOK.md`
- Decisions log: `docs/DECISIONS.md`

## Local dev

```
cp .env.example .env
# Set SECRET_KEY (openssl rand -hex 32) and ADMIN_PASSWORD.
docker compose -f deploy/docker-compose.yml up -d
```

Ports on host:
- API + Swagger: http://localhost:8100/docs
- MinIO console: http://localhost:9101
- Grafana: http://localhost:3100

## Status

- [x] **P0 Foundation** — docker stack, auth, Rule 1 guard, health, Swagger, tests (48 pass).
- [ ] P1 Ingestion + retrieval
- [ ] P2 Verification
- [ ] P3 Frontend
- [ ] P4 Review workflow
- [ ] P5 Hardening

## Tests

Unit tests (48) use SQLite in-memory and cover the invariants:
```
cd backend && pytest
```

Live docker acceptance (Rule-1 drift drill, admin login end-to-end) — see `docs/RUNBOOK.md`.
