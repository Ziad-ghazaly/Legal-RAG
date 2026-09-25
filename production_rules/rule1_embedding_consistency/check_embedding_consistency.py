"""
Rule 1 — Same embedding model everywhere.

Checks config ↔ system_meta ↔ TEI ↔ stored vectors ↔ live query path.
Uses the backend's own embedder functions, so it tests the real code path.

Usage:
    python -m production_rules.rule1_embedding_consistency.check_embedding_consistency [--sample 200]
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import httpx
import numpy as np

from production_rules._common import Report, db_connect, env

ROUND_TRIP_MIN_COS = 0.999
ROUND_TRIP_MIN_SHARE = 0.99
SELF_RETRIEVAL_MIN_TOP1 = 0.95
NORM_TOLERANCE = 1e-3


def _load_embedder():
    backend = Path(env("BACKEND_PATH")).resolve()
    sys.path.insert(0, str(backend))
    try:
        mod = importlib.import_module("app.retrieval.embedder")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"[rule1] cannot import app.retrieval.embedder from {backend}: {exc}")
    for fn in ("build_passage_input", "build_query_input", "embed_texts"):
        if not hasattr(mod, fn):
            raise SystemExit(f"[rule1] app.retrieval.embedder is missing required function: {fn}")
    return mod


def _parse_vec(v) -> np.ndarray:
    if isinstance(v, str):  # pgvector text form "[0.1,0.2,...]"
        return np.array([float(x) for x in v.strip("[]").split(",")], dtype=np.float32)
    return np.asarray(v, dtype=np.float32)


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=200)
    args = ap.parse_args()

    cfg_model = env("EMBEDDING_MODEL")
    cfg_dim = int(env("EMBEDDING_DIM"))
    cfg_norm = env("NORMALIZER_VERSION")
    rep = Report("rule1_embedding_consistency")

    conn = db_connect()
    cur = conn.cursor()

    # 1. config vs system_meta
    cur.execute("SELECT key, value FROM system_meta WHERE key IN ('embedding_model','embedding_dim','normalizer_version')")
    meta = dict(cur.fetchall())
    for key, expected in (("embedding_model", cfg_model), ("embedding_dim", str(cfg_dim)), ("normalizer_version", cfg_norm)):
        rep.add(f"system_meta.{key}", meta.get(key) == expected, meta.get(key), expected)

    # 2. TEI serves the configured model
    try:
        info = httpx.get(env("TEI_EMBED_URL").rstrip("/") + "/info", timeout=10).json()
        served = info.get("model_id")
    except Exception as exc:  # noqa: BLE001
        served = f"error: {exc}"
    rep.add("tei.model_id", served == cfg_model, served, cfg_model)

    # 3. exactly one model in the corpus
    cur.execute("SELECT embedding_model, count(*) FROM chunks GROUP BY 1")
    models = dict(cur.fetchall())
    rep.add("chunks.distinct_models", list(models.keys()) == [cfg_model], models, [cfg_model])

    # 4. no missing vectors
    cur.execute("SELECT count(*) FROM chunks WHERE embedding IS NULL")
    nulls = cur.fetchone()[0]
    rep.add("chunks.null_embeddings", nulls == 0, nulls, 0)

    # 5. one dimension
    cur.execute("SELECT vector_dims(embedding), count(*) FROM chunks WHERE embedding IS NOT NULL GROUP BY 1")
    dims = dict(cur.fetchall())
    rep.add("chunks.vector_dims", list(dims.keys()) == [cfg_dim], dims, [cfg_dim])

    # Sample for 6–8
    cur.execute(
        """SELECT c.id, c.unit_id, c.document_id, c.chunk_kind, c.context_header, c.text, c.text_norm, c.embedding::text
           FROM chunks c TABLESAMPLE SYSTEM (5)
           WHERE c.embedding IS NOT NULL AND c.embedding_model = %s
           LIMIT %s""",
        (cfg_model, args.sample),
    )
    cols = [d.name for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    if len(rows) < min(20, args.sample):  # small corpus: fall back to random order
        cur.execute(
            """SELECT c.id, c.unit_id, c.document_id, c.chunk_kind, c.context_header, c.text, c.text_norm, c.embedding::text
               FROM chunks c WHERE c.embedding IS NOT NULL AND c.embedding_model = %s ORDER BY random() LIMIT %s""",
            (cfg_model, args.sample),
        )
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    if not rows:
        rep.add("sample.available", False, 0, ">0", "no chunks to sample")
        rep.write()
        rep.exit()

    stored = [_parse_vec(r["embedding"]) for r in rows]

    # 6. normalized
    norms = np.array([np.linalg.norm(v) for v in stored])
    bad_norm = int(np.sum(np.abs(norms - 1.0) > NORM_TOLERANCE))
    rep.add("vectors.l2_normalized", bad_norm == 0, f"{bad_norm}/{len(norms)} off", f"|norm-1|<={NORM_TOLERANCE}")

    emb = _load_embedder()

    # 7. re-embed round trip through the app's own passage path
    passage_inputs = [emb.build_passage_input({k: v for k, v in r.items() if k != "embedding"}) for r in rows]
    fresh = [np.asarray(v, dtype=np.float32) for v in emb.embed_texts(passage_inputs)]
    cos = np.array([_cos(a, b) for a, b in zip(stored, fresh)])
    share = float(np.mean(cos >= ROUND_TRIP_MIN_COS))
    worst = [rows[i]["id"] for i in np.argsort(cos)[:5]]
    rep.add(
        "roundtrip.passage_reembed",
        share >= ROUND_TRIP_MIN_SHARE,
        f"{share:.3f} (min cos {cos.min():.4f})",
        f">={ROUND_TRIP_MIN_SHARE} with cos>={ROUND_TRIP_MIN_COS}",
        f"worst chunk ids: {worst}",
    )

    # 8. self-retrieval through the app's own query path
    probe = rows[: min(len(rows), 100)]
    q_inputs = [emb.build_query_input(r["text"]) for r in probe]
    q_vecs = emb.embed_texts(q_inputs)
    hits = 0
    misses = []
    for r, qv in zip(probe, q_vecs):
        vec_literal = "[" + ",".join(f"{x:.7f}" for x in qv) + "]"
        cur.execute(
            "SELECT id FROM chunks WHERE embedding_model = %s ORDER BY embedding <=> %s::vector LIMIT 1",
            (cfg_model, vec_literal),
        )
        top = cur.fetchone()
        if top and top[0] == r["id"]:
            hits += 1
        else:
            misses.append(r["id"])
    top1 = hits / len(probe)
    rep.add(
        "probe.self_retrieval_top1",
        top1 >= SELF_RETRIEVAL_MIN_TOP1,
        f"{top1:.3f}",
        f">={SELF_RETRIEVAL_MIN_TOP1}",
        f"sample misses: {misses[:5]} (near-duplicate chunks also cause misses — cross-check rule 2)",
    )

    rep.write({"config": {"model": cfg_model, "dim": cfg_dim, "normalizer_version": cfg_norm}})
    rep.exit()


if __name__ == "__main__":
    main()
