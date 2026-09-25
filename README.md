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
- Web app: http://localhost:8300
- API + Swagger: http://localhost:8100/docs
- MinIO console: http://localhost:9101
- Grafana: http://localhost:3100

## Status

- [x] **P0 Foundation** — docker stack, auth, Rule 1 guard, health, Swagger. Full stack verified in Docker (API via PgBouncer, worker, MinIO, TEI).
- [x] **P1 Ingestion + retrieval** — JSONL contract, legal-aware chunker, idempotent indexer, ingestion jobs (API → MinIO → arq worker), hybrid retrieval (pgvector + pg_search BM25 → RRF → rerank → authority → pinning), `/api/retrieval/search`. Rules 1 + 2 pass on a real dev corpus. **Gate pending:** rule 3 needs the client's reviewer-validated gold set (≥200 queries) and GPU TEI for the latency gate.
- [x] **P2 Verification** — `POST /api/v1/reviews` (text or PDF/DOCX/TXT) → arq `run_review`: Claude claim extraction → per-claim full-mode retrieval with pinned citations → batched Claude verification → deterministic quote/passage validation, repealed guard, scoring, blocking contradictions, status → summary + suggested opinion (`needs_review`) → similar opinions. SSE progress at `/reviews/{id}/events`, source viewer `/sources/chunks/{id}`. **Gate pending:** verification gold set (≥60 opinions) to calibrate `ACCEPT_THRESHOLD`; OCR for scanned PDFs not built.
- [x] **P3 Frontend** — React 18 + TS + Vite + Tailwind, Arabic RTL (IBM Plex Sans Arabic, brief palette): login, reviews list (filter, paging), new review (text or drag-and-drop file, as-of date, collections), result page (status + score, live SSE stepper, tabs: summary / claims / references with full-text drawer / similar / suggested), admin (ingestion jobs with per-row errors, collections, users + ACL). Served by nginx at **http://localhost:8300** (proxies `/api`). Approve / edit / export buttons are placeholders until P4.
- [ ] P4 Review workflow
- [ ] P5 Hardening

## Tests

```
cd backend && pytest                                   # unit (SQLite)
V3_INTEGRATION=1 POSTGRES_HOST=localhost POSTGRES_PORT=5532 pytest tests/integration   # real ParadeDB
```

Live docker acceptance (Rule-1 drift drill, admin login end-to-end) — see `docs/RUNBOOK.md`.
