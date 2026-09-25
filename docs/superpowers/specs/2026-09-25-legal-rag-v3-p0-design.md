# Legal-RAG v3 — P0 Foundation Design Spec

**Date**: 2026-09-25
**Status**: Approved (conversational). Awaiting written-spec review.
**Author**: Session collaboration between Ziad Ghazaly and Claude Opus 4.7
**Supersedes**: none (v3 is a clean rewrite of the `legal-rag/` v1/v2 demo)

---

## 1. Purpose

Phase 0 lays the foundation for the Kuwaiti Legal Opinion Verification
Platform (v3). It is **backend-only**: repo scaffolding, Docker Compose,
Postgres+ParadeDB schema, authentication, Arabic normalizer, embedding-
model guard, TEI wiring for BGE-M3 embeddings + BGE-reranker, health
checks, and the debug-artifact contract for future ingestion.

The intent is not to run any query or ingest any document in P0. The
intent is to prove the platform can start cleanly, refuse to start when
its invariants are violated, and expose the Rule-1 embedding contract so
Phase 1 can bolt on ingestion without retrofitting.

## 2. Scope

**In scope:**

- Repo layout under `legal-rag-v3/` (sibling to v2 at
  `C:\Users\ziadg\Demo_RAG\legal-rag-v3\`).
- Docker Compose stack with 10 services on non-conflicting ports.
- Postgres 16 via ParadeDB image with `pg_search` (BM25) and `pgvector`.
- Alembic single migration `0001_p0_foundation.py` creating the full v3
  schema. P0 populates only auth + `system_meta` tables. Every other
  table is created empty so P1+ never runs a schema-reset migration.
- JWT auth (access 15 min, refresh 7 days rotating) with argon2 hashes
  and RBAC (`admin` / `reviewer` / `user`).
- Arabic normalizer module with two functions and a `NORMALIZER_VERSION`.
- Embedding-model guard: API and worker refuse to start on
  `{embedding_model, embedding_dim, normalizer_version}` mismatch between
  config and `system_meta`.
- `Embedder` class implementing the Rule-1 contract
  (`build_passage_input`, `build_query_input`, `embed_texts`) as the
  **only** path used for embeddings anywhere in v3.
- TEI containers for `BAAI/bge-m3` and `BAAI/bge-reranker-v2-m3`.
- Health endpoints (`/health/live`, `/health/ready`) and Swagger.
- Ingestion & OCR debug-artifact **contract** (endpoints stubbed,
  documented). Actual artifact writing lands in Phase 1.
- Structured JSON logs with `request_id`, Prometheus scrape endpoint,
  OpenTelemetry hooks (traces wired in P5).
- GitHub Actions CI running the P0 test suite.
- P0 test suite: normalizer, startup guard, auth, health, embedder.

**Out of scope for P0** (deferred to later phases):

- Ingestion pipeline, parsing, OCR execution, chunker (P1).
- Retrieval, RRF, rerank, exact-reference pinning (P1).
- Verification, claim extraction, Claude calls, scoring (P2).
- Frontend UI (P3). `frontend/` exists in the repo as `.gitkeep` only.
- Editor / versions / approvals / export (P4).
- Load testing, OTel trace forwarders, restore drills (P5).
- User migration script from v2 SQLite. Documented as a cutover-time
  task at v3 launch, not P0.

## 3. Non-negotiable invariants (carried from `CONTEXT.md`)

- **Rule 1 — same embedding model everywhere.** Every embedding path
  goes through `app/retrieval/embedder.py`. Startup guard blocks
  mismatch on `embedding_model`, `embedding_dim`, `normalizer_version`.
- **Single LLM provider policy.** v3 talks to Anthropic Claude only.
  Model `claude-sonnet-4-5`. Temperature 0. Structured output on every
  call. Prompt caching on static system prompts. Retry with exponential
  backoff, then fail with a clean Arabic error. No Groq / Gemini /
  Cohere / OpenRouter / LangGraph. **(This is P2 concern; P0 ships the
  client stub with retry semantics only.)**
- **Deterministic code decides.** Score, status, citation validity,
  source validity are computed in Python. The LLM never emits them.
- **Arabic in UI, English in code.**
- **Fresh state.** No cache, no volumes, no data lifted from v2. Every
  file the user uploads goes through v3's pipeline from scratch.

## 4. Repository layout

```
legal-rag-v3/
├── backend/
│   ├── app/
│   │   ├── api/                    # FastAPI routers
│   │   │   ├── auth.py             # /auth/login,refresh,logout,me
│   │   │   ├── health.py           # /health/live,ready
│   │   │   └── admin/
│   │   │       └── ingestion.py    # debug endpoints (stubbed for P0)
│   │   ├── core/
│   │   │   ├── config.py           # Pydantic Settings, single source of truth
│   │   │   ├── security.py         # argon2 + JWT helpers
│   │   │   ├── logging.py          # JSON structlog config
│   │   │   ├── otel.py             # tracer + middleware (span emit only in P0)
│   │   │   └── startup_guard.py    # Rule-1 enforcement
│   │   ├── db/
│   │   │   ├── session.py          # async SQLAlchemy engine + session
│   │   │   ├── models.py           # SQLAlchemy 2.0 declarative models
│   │   │   └── alembic/
│   │   │       ├── env.py
│   │   │       └── versions/
│   │   │           └── 0001_p0_foundation.py
│   │   ├── text/
│   │   │   ├── arabic.py           # NORMALIZER_VERSION="v1" + 2 functions
│   │   │   └── tokenization.py     # HF tokenizer wrapper for token counts
│   │   ├── retrieval/
│   │   │   └── embedder.py         # Rule-1 contract
│   │   ├── llm/
│   │   │   └── claude_client.py    # stub with retry+backoff; no calls in P0
│   │   ├── services/
│   │   │   └── users.py            # user CRUD + admin seed on startup
│   │   └── main.py                 # FastAPI app factory, lifespan hooks
│   ├── workers/
│   │   └── arq_app.py              # arq worker boot; no tasks defined in P0
│   ├── tests/
│   │   ├── conftest.py             # fixtures: db, tei, http client
│   │   ├── test_arabic.py          # >=30 cases inc. الماده ٤١ ↔ 41 invariant
│   │   ├── test_startup_guard.py   # mismatch + happy path
│   │   ├── test_auth.py            # login/refresh/logout/me/role gate
│   │   ├── test_health.py          # live + ready with deps mocked
│   │   └── test_embedder.py        # dim, determinism, error path
│   ├── pyproject.toml              # single source of dep truth (no requirements.txt)
│   └── Dockerfile
├── production_rules/               # copied unchanged from brief supplier
│   ├── rule1_embedding_consistency/
│   ├── rule2_embedding_quality/
│   ├── rule3_retrieval_eval/
│   └── README.md
├── eval/
│   └── .gitkeep                    # populated in P2
├── deploy/
│   ├── docker-compose.yml          # 10 services (see §5)
│   ├── docker-compose.dev.yml      # override: CPU TEI, exposed ports
│   ├── nginx.conf                  # frontend proxy shell (unused in P0)
│   ├── prometheus.yml
│   └── grafana/
│       └── provisioning/           # datasource + dashboard skeletons
├── docs/
│   ├── ARCHITECTURE.md             # 1-page diagram + request lifecycle
│   ├── DECISIONS.md                # append-only log
│   ├── INGESTION_CONTRACT.md       # JSONL schema template
│   ├── DEBUG_ARTIFACTS.md          # ingestion-debug layout (§7)
│   └── RUNBOOK.md
├── frontend/
│   └── .gitkeep                    # P3 fills this in
├── CONTEXT.md                      # copied from v2 root, source of truth
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│       └── p0.yml                  # lint + typecheck + pytest
└── README.md
```

## 5. Docker Compose services (P0)

All services under one network `v3_net`. Named volumes prefixed `v3_`.
Fresh state everywhere. **Zero collision with v2.**

| Service | Image | Host→ctr port | Notes |
|---|---|---|---|
| `v3_api` | built from `backend/` | `8100→8000` | Uvicorn, FastAPI |
| `v3_worker` | same image, `cmd: arq workers.arq_app.WorkerSettings` | — | No tasks in P0 |
| `v3_postgres` | `paradedb/paradedb:latest` | `5532→5432` | Postgres 16 + pg_search + pgvector |
| `v3_pgbouncer` | `edoburu/pgbouncer` | `6532→5432` | Transaction pool |
| `v3_redis` | `redis:7-alpine` | `6479→6379` | Queue for arq |
| `v3_minio` | `minio/minio` | `9100→9000`, `9101→9001` | S3-compatible storage |
| `v3_tei_embed` | `ghcr.io/huggingface/text-embeddings-inference:cpu-1.5` (dev) | `8180→80` | `BAAI/bge-m3` |
| `v3_tei_rerank` | same image family | `8181→80` | `BAAI/bge-reranker-v2-m3` |
| `v3_prometheus` | `prom/prometheus` | `9190→9090` | Scrapes `v3_api`, `v3_worker` |
| `v3_grafana` | `grafana/grafana` | `3100→3000` | Empty dashboards folder in P0 |

Volumes: `v3_postgres_data`, `v3_minio_data`, `v3_tei_cache`. Health checks
on every service. `depends_on` with `condition: service_healthy` on API.

`docker-compose.dev.yml` overrides the TEI images to the CPU variant and
mounts a local model cache to avoid re-downloading during rebuilds. Prod
override (in P5) will swap to GPU images.

## 6. Database schema (P0 subset)

Alembic revision `0001_p0_foundation.py` creates the full v3 schema.
Only the tables below are populated in P0; the rest are created empty.

**Populated in P0:**

- `users` — id (uuid), username (unique), email (unique, nullable),
  hashed_password (argon2), role (`admin`/`reviewer`/`user`),
  is_active bool, created_at, updated_at.
- `collections` — id, name (unique), description, created_at.
- `user_collections` — (user_id, collection_id) composite PK.
- `refresh_tokens` — id, user_id, token_hash, expires_at, revoked bool,
  created_at. Rotating: on refresh, old row is revoked and new one
  inserted atomically.
- `system_meta` — key (PK, text), value (text). Seeded with:
  - `embedding_model = BAAI/bge-m3`
  - `embedding_dim = 1024`
  - `normalizer_version = v1`
  - `schema_version = 0001`

**Empty in P0, defined so P1+ doesn't need a schema-reset migration:**

- `documents`, `units`, `chunks` (with `vector(1024)` column and HNSW
  index created against the empty table; `pg_search` BM25 index on
  `text_norm` similarly created empty).
- `reviews`, `claims`, `claim_evidence`, `review_versions`, `approvals`.
- `llm_calls`, `audit_log`, `ingestion_jobs`, `eval_runs`.

Composite / functional indexes created in the same migration:

- `chunks (embedding_model, collection_id)` — for the Rule-1 filter.
- `chunks (collection_id, status, valid_from, valid_to)` — for as-of
  validity filter.
- `units (document_id, article_number, valid_from)` — for exact-ref
  lookup.
- HNSW on `chunks.embedding` with `m=16, ef_construction=128` and
  `vector_cosine_ops`.

## 7. Ingestion & OCR debug-artifact contract (design only in P0)

Requirement: every uploaded document produces inspectable artifacts so
the user (admin) can eyeball exactly what parsing and OCR did to it.
**P0 designs the contract and stubs the endpoints. P1 writes actual
artifacts.**

MinIO bucket `v3-ingestion-debug/` with layout:

```
{ingestion_job_id}/
  {doc_id}/
    01_original.pdf                exact bytes uploaded
    02_extraction.json             parser output (raw text per page,
                                    method used: pymupdf|python-docx|txt)
    03_ocr.json                    OCR output if fired (Tesseract ara),
                                    per-page confidence + text
    04_cleaned.txt                 after boilerplate removal, watermark
                                    lines dropped and logged
    05_units.json                  discovered legal units (article
                                    boundaries, section paths)
    06_chunks.json                 final chunks: text, text_norm,
                                    context_header, token_count
    07_dropped.jsonl               every chunk dropped with reason
                                    (dupe, boilerplate, garbage)
    report.md                      human-readable summary
```

Admin endpoints (stubbed 501 in P0; wired in P1):

- `GET /api/v1/admin/ingestion/jobs/{job_id}/debug/{doc_id}` — returns
  signed download URLs for the seven artifacts.
- `GET /api/v1/admin/ingestion/jobs/{job_id}/debug/{doc_id}/report` —
  inline Markdown for quick browser inspection.

Contract documented in full at `docs/DEBUG_ARTIFACTS.md`.

## 8. Authentication + RBAC

- **Password hashing**: argon2id via `argon2-cffi` with defaults from
  `argon2.PasswordHasher()`. Logged in DECISIONS.md as picked over
  bcrypt (both allowed by brief).
- **Access token**: JWT (HS256), 15 min expiry, subject = user id.
- **Refresh token**: opaque random 32-byte token, stored hashed in
  `refresh_tokens`, 7 day expiry, rotating on every use. Old row
  revoked atomically with new insert.
- **RBAC**: FastAPI dependency `require_role("admin")` etc. Roles enum
  defined in `app.core.roles`.
- **Endpoints**:
  - `POST /auth/login` — body `{username, password}` → tokens.
  - `POST /auth/refresh` — body `{refresh_token}` → tokens.
  - `POST /auth/logout` — revokes current refresh row.
  - `GET /auth/me` — returns user profile.
- **Admin seed on startup**: reads `ADMIN_PASSWORD` from env. If unset
  and no admin exists in DB, refuse to boot with clear error. If admin
  exists, seed is skipped (no password rewrite).
- **`SECRET_KEY` guard**: required in env, refuse to boot if unset,
  short, or equal to a documented placeholder.

## 9. Arabic normalizer

Module `app/text/arabic.py`. Constant `NORMALIZER_VERSION = "v1"`.

`normalize_for_search(text: str) -> str`:

1. Strip tashkeel: `ً ٌ ٍ َ ُ ِ ّ ْ`.
2. Strip tatweel: `ـ`.
3. Strip zero-width chars: `​–‏`, `‪–‮`, `﻿`.
4. Unify: `أ إ آ ٱ → ا`, `ى → ي`, `ة → ه`, `ؤ → و`, `ئ → ي`.
5. Eastern Arabic digits `٠-٩` → `0-9`.
6. Collapse whitespace.

`normalize_for_embedding(text: str) -> str`:

Same steps 1, 2, 3, 5, 6 — **skip letter unification** (step 4) to keep
morphological signal for the embedder.

Test set at `backend/tests/test_arabic.py` — ≥ 30 real Kuwaiti legal
snippets, including the golden invariant `المادة ٤١` ≡ `المادة 41`
after `normalize_for_search`.

## 10. Startup guard (Rule 1)

`app/core/startup_guard.py`, called from FastAPI lifespan and from arq
worker startup:

```
read system_meta rows for keys:
  embedding_model, embedding_dim, normalizer_version
compare each to config.EMBEDDING_MODEL, config.EMBEDDING_DIM,
        text.arabic.NORMALIZER_VERSION
if any mismatch:
    log both values in a structured JSON error
    raise SystemExit with:
      "Rule 1 violation: embedding invariant mismatch. Aborting startup.
       انتهاك القاعدة 1: عدم تطابق ثابت التضمين. تم إلغاء التشغيل."
```

Both API and worker share the same guard module — a single point of
enforcement. Test: fixture rigs `system_meta` with a mismatch, asserts
the guard raises `SystemExit`.

## 11. Embedder (`app/retrieval/embedder.py`)

Public API (matches `production_rules/` expectations):

```python
def build_passage_input(chunk: dict) -> str:
    """Exact text embedded at ingestion time.
    context_header + '\\n' + normalize_for_embedding(text)"""

def build_query_input(query: str) -> str:
    """Exact text embedded at query time.
    normalize_for_embedding(query)"""

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batched POST to TEI /embed, batch=32, timeout=30s.
    3 retries, backoff 0.5→2→8 seconds, then raise EmbedderError."""
```

Guarantees:

- Returns list of vectors of dim `EMBEDDING_DIM` (1024).
- Vectors returned normalized (BGE-M3 emits normalized; defensive check).
- Deterministic given the same input (bge-m3 at inference).
- Raises `EmbedderError` on any non-recoverable failure. No fallback,
  no silent degradation.

## 12. Health checks and observability

- `GET /health/live` — 200 iff process is up.
- `GET /health/ready` — checks in this order, short-circuits on first
  failure:
  1. Postgres `SELECT 1`.
  2. Redis `PING`.
  3. TEI embed `GET /health`.
  4. TEI rerank `GET /health`.
  5. MinIO bucket location.
  6. Startup guard passed.
- `GET /metrics` — Prometheus format, includes:
  - `http_requests_total{method,route,status}`
  - `http_request_duration_seconds` (histogram)
  - `startup_guard_status` (gauge, 0 or 1)
- OTel: SDK initialized, `TracerProvider` set, but no exporter wired
  in P0 (P5 adds the collector). Spans are still emitted in-process
  and visible via test double.
- Structured JSON logs everywhere, one line per event, with:
  `timestamp, level, request_id, user_id, event, ...`

## 13. Tests (P0 acceptance signal)

All tests run in CI on every push. Total must pass in < 60 seconds.

| Test file | What it proves |
|---|---|
| `test_arabic.py` | Normalizer correctness on 30+ real legal snippets, including the digit-form invariant. |
| `test_startup_guard.py` | Guard raises `SystemExit` on any mismatch key. Happy path succeeds. |
| `test_auth.py` | Login returns tokens. Refresh rotates. Logout revokes. `/auth/me` requires auth. `require_role("admin")` gates admin routes with 403. |
| `test_health.py` | `/health/live` always 200. `/health/ready` returns 503 when any dep is down (parameterized). |
| `test_embedder.py` | Vector dim = 1024. Same input → same output (determinism). TEI unreachable → `EmbedderError` after 3 retries. |

Manual pre-P1 smoke test the operator runs once:

- `docker compose up -d` on a fresh machine.
- `curl -X POST http://localhost:8100/auth/login -d '{"username":"admin","password":"…"}'`.
- Confirm `/docs`, `/health/ready`, and `/metrics` reachable.

## 14. CI (P0 scope)

`.github/workflows/p0.yml`:

```
name: p0
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres: paradedb/paradedb:latest (with pgvector + pg_search)
      redis:    redis:7-alpine
      tei-embed: ghcr.io/huggingface/text-embeddings-inference:cpu-1.5 (bge-m3)
      minio:    minio/minio
    steps:
      - checkout
      - setup-python 3.12
      - pip install
      - alembic upgrade head
      - pytest -q backend/tests/
      - ruff check
      - mypy backend/app
```

Rule 1 / 2 / 3 checks from `production_rules/` are **not** wired in
P0 CI — they need ingestion data. P1 CI adds them.

## 15. P0 acceptance gate

P0 is done when **all** are true:

1. `docker compose -f deploy/docker-compose.yml up -d` on a fresh
   machine, `docker compose ps` shows every service healthy inside 60
   seconds.
2. `pytest backend/tests/` → 100% green.
3. Manual embedding-drift simulation: patch `system_meta` to a wrong
   `embedding_model`, restart API — service refuses to boot with the
   Arabic+English error message.
4. `GET http://localhost:8100/docs` renders. `POST /auth/login` with
   the seeded admin returns tokens. `GET /auth/me` returns
   `{role: "admin"}`. `GET /health/ready` returns 200.
5. CI green on `main`.

No ingestion, no retrieval, no LLM calls, no frontend. Those live in
P1–P3.

## 16. Decisions logged (initial `DECISIONS.md` entries)

- **D-001**: v3 repo location = sibling `C:\Users\ziadg\Demo_RAG\legal-rag-v3\`.
- **D-002**: v3 is a **new GitHub repo**; v2 repo remains as reference.
- **D-003**: P0 is backend-only. Frontend directory scaffolded but
  empty; P3 populates it.
- **D-004**: User migration from v2 SQLite is a **cutover-time task**,
  not P0. Seed admin from env in P0.
- **D-005**: Password hashing = **argon2id** (`argon2-cffi`) over bcrypt.
  Winner of PHC and stronger defaults.
- **D-006**: `NORMALIZER_VERSION = "v1"` at repo creation.
- **D-007**: Default embedding model in `system_meta` seed =
  `BAAI/bge-m3`. Locked-in choice remains subject to P1 eval-harness
  swap to `intfloat/multilingual-e5-large` if it wins on Recall@10.
- **D-008**: Digits in UI = Western digits for article numbers (also
  produced by `normalize_for_search`; keeps UI ↔ search consistent).
- **D-009**: All v3 container names, network, volumes, ports prefixed
  `v3_` so v2 can keep running unaffected.
- **D-010**: **No code lifted from v2/v1.** Only concepts and .md files
  ported. `KUWAITI_LEGAL_HIERARCHY`, negation patterns, article regex,
  boilerplate rules, OCR flow — all rewritten fresh in v3.
- **D-011**: Dependency management = **`pyproject.toml` only** (uv or
  pip-tools sync). No `requirements.txt`. Locked via `uv.lock` /
  `requirements.lock` for reproducible builds.
- **D-012**: The debug-artifact bucket `v3-ingestion-debug/` is
  created empty at MinIO bootstrap. Retention policy = 90 days
  (configurable), documented in `RUNBOOK.md`.

## 17. Cross-references

- Ubiquitous language: `CONTEXT.md` (at v2 workspace root; copied into
  v3 root during scaffolding).
- Production rules: `production_rules/README.md` (supplied unchanged by
  brief).
- The v3 build brief itself (pasted into the session).

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| ParadeDB image incompatibility with pgvector version | Pin exact tag; document `\dx` output in `RUNBOOK.md`; fallback path to plain Postgres + `tsvector` documented in DECISIONS.md if we hit an issue. |
| TEI cold-start slow on GPU-less dev machines | CPU images with model cache mount; first boot documented as ~5 min. |
| Startup guard false-positive on migrations that touch `system_meta` | Guard reads only after Alembic completes; migration wraps `system_meta` updates in the same transaction as the schema change. |
| P0 CI slow due to model download | GitHub Actions cache for TEI model volumes; first CI run ~10 min, subsequent < 3 min. |

---

**Approval flow**: this spec, once approved, unlocks invoking the
`superpowers:writing-plans` skill to produce the P0 implementation plan.
The plan, once approved, unlocks P0 implementation.
