# Legal-RAG v3

Kuwaiti Legal Opinion Verification Platform. Production rewrite of the v1/v2 demo.

- Design spec: `docs/superpowers/specs/2026-09-25-legal-rag-v3-p0-design.md`
- Ubiquitous language: `CONTEXT.md`
- Runbook: `docs/RUNBOOK.md`

## Local dev

```
cp .env.example .env
# edit .env — set SECRET_KEY and ADMIN_PASSWORD
docker compose -f deploy/docker-compose.yml up -d
```

Ports on host:
- API: 8100 (Swagger at http://localhost:8100/docs)
- Postgres: 5532
- MinIO console: 9101
- Grafana: 3100
