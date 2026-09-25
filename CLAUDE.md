# CLAUDE.md — Legal-RAG v3

Kuwaiti legal-opinion **verification** platform (not a chatbot). Read `CONTEXT.md`
(vocabulary + invariants) and `docs/BRIEF.md` (the spec) before changing code.
This repo is v3 only; v1/v2 live in a different repo and share no code.

## Commands

Backend (Python 3.12, from `backend/`):
```
py -3.12 -m venv ../.venv && ../.venv/Scripts/activate
pip install -e ".[dev]"
ruff check .                     # CI gate (ruff 0.8 pinned)
pytest                           # unit tests (SQLite, no services)
V3_INTEGRATION=1 POSTGRES_HOST=localhost POSTGRES_PORT=5532 pytest tests/integration
                                 # real ParadeDB, fake TEI; uses DB legalrag_test
```

Stack (from repo root): `docker compose -f deploy/docker-compose.yml up -d --build`
— API :8100 (`/docs`), Postgres :5532, MinIO console :9101, TEI :8180/:8181, Grafana :3100.
First TEI boot downloads ~4 GB of models.

Production rules (must stay unchanged; see `docs/RUNBOOK.md` for env):
```
python -m production_rules.rule1_embedding_consistency.check_embedding_consistency
python -m production_rules.rule2_embedding_quality.check_corpus_quality
python -m production_rules.rule3_retrieval_eval.run_retrieval_eval --gold <gold.jsonl>
```

## Invariants (do not break)

- **Rule 1:** every embedding goes through `app/retrieval/embedder.py`
  (`build_passage_input`, `build_query_input`, `embed_texts` [sync, rules contract],
  `aembed_texts` [app]). API/worker refuse to boot if `system_meta` ≠ config.
- Retrieval filters (ACL `collection_id`, `embedding_model`, validity window,
  repealed) live **inside** the SQL — never filter after scoring.
- One chunk = one citation. `final = sigmoid(logit) × (0.85 + 0.15 × authority)`.
- The LLM never emits score/status/verdict truth — Python computes them.
- Claude is the only LLM provider. User-facing strings Arabic; code English.
- Never edit `production_rules/` thresholds to make a check pass.
- Collections have **integer** ids (rules contract).

## Layout

`backend/app/{api,core,db,ingestion,retrieval,text,llm,verification}` ·
`backend/workers` (arq) · `backend/tools` (dev converters) · `deploy/` · `docs/` ·
`production_rules/` · `eval/` · `frontend/`.
Decisions: `docs/DECISIONS.md` (append-only). Plans + ledgers: `docs/superpowers/`.
