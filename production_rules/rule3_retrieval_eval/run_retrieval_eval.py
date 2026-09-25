"""
Rule 3 — Test retrieval separately (no LLM in the loop).

Calls POST /api/retrieval/search for every gold query in every mode, computes
domain-specific metrics per mode and per category, checks the gates, and runs
an ACL-leak test with a restricted user token.

Usage:
    python -m production_rules.rule3_retrieval_eval.run_retrieval_eval \
        --gold production_rules/rule3_retrieval_eval/gold/retrieval_gold.jsonl \
        [--modes vector,bm25,hybrid,hybrid_rerank,full] [--top-k 20]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import httpx

from production_rules._common import Report, env
from production_rules.rule3_retrieval_eval.metrics import (
    dedupe_units,
    hit_at_k,
    mrr_at_k,
    ndcg_at_k,
    percentile,
    recall_at_k,
)

# ── Gates (evaluated on the "full" mode unless stated) ─────────────────────
GATE_RECALL10 = 0.85
GATE_EVIDENCE_HIT6 = 0.90
GATE_EXACT_CITATION_HIT1 = 0.98
GATE_ASOF_CORRECT = 0.95
GATE_P95_MS = 1500
PRIMARY_MODE = "full"


def load_gold(path: Path) -> list[dict]:
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        row = json.loads(line)
        for key in ("id", "query_ar", "relevant_unit_ids"):
            if key not in row:
                raise SystemExit(f"gold line {i}: missing '{key}'")
        rows.append(row)
    return rows


def search(client: httpx.Client, token: str, q: dict, mode: str, top_k: int) -> dict:
    body = {
        "query": q["query_ar"],
        "as_of_date": q.get("as_of_date"),
        "collections": q.get("collections"),
        "mode": mode,
        "top_k": top_k,
        "include_repealed": bool(q.get("include_repealed", False)),
    }
    r = client.post("/api/retrieval/search", json=body, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True, type=Path)
    ap.add_argument("--modes", default="vector,bm25,hybrid,hybrid_rerank,full")
    ap.add_argument("--top-k", type=int, default=20)
    args = ap.parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    gold = load_gold(args.gold)
    admin_token = env("API_ADMIN_TOKEN")
    rep = Report("rule3_retrieval_eval")
    client = httpx.Client(base_url=env("API_URL"), timeout=60)

    per_mode: dict[str, dict] = {}
    per_query_rows = []

    for mode in modes:
        agg = defaultdict(list)
        by_cat = defaultdict(lambda: defaultdict(list))
        latencies = []
        repealed_leaks = 0
        for q in gold:
            res = search(client, admin_token, q, mode, args.top_k)
            results = res.get("results", [])
            latencies.append(float(res.get("latency_ms", 0.0)))
            ranked = dedupe_units([r["unit_id"] for r in results])
            rel = set(q["relevant_unit_ids"])
            cat = q.get("category", "uncategorized")

            if not q.get("include_repealed", False):
                repealed_leaks += sum(1 for r in results if r.get("status") == "repealed")

            m = {
                "recall@5": recall_at_k(ranked, rel, 5),
                "recall@10": recall_at_k(ranked, rel, 10),
                "recall@20": recall_at_k(ranked, rel, 20),
                "mrr@10": mrr_at_k(ranked, rel, 10),
                "ndcg@10": ndcg_at_k(ranked, rel, 10),
                "evidence_hit@6": hit_at_k(ranked, rel, 6),
            }
            if cat == "exact_citation":
                m["exact_citation_hit@1"] = hit_at_k(ranked, rel, 1)
            if cat == "amended":
                # correct version must outrank any other version of the same article
                wrong = set(q.get("wrong_version_unit_ids", []))
                pos = {u: i for i, u in enumerate(ranked)}
                best_rel = min((pos[u] for u in rel if u in pos), default=10**9)
                best_wrong = min((pos[u] for u in wrong if u in pos), default=10**9)
                m["asof_correct"] = 1.0 if best_rel < best_wrong else 0.0

            for k, v in m.items():
                agg[k].append(v)
                by_cat[cat][k].append(v)
            per_query_rows.append({"mode": mode, "id": q["id"], "category": cat, **m, "top5": ranked[:5]})

        summary = {k: round(sum(v) / len(v), 4) for k, v in agg.items() if v}
        summary["latency_p50_ms"] = round(percentile(latencies, 0.5), 1)
        summary["latency_p95_ms"] = round(percentile(latencies, 0.95), 1)
        summary["repealed_leaks"] = repealed_leaks
        summary["by_category"] = {c: {k: round(sum(v) / len(v), 4) for k, v in d.items()} for c, d in by_cat.items()}
        per_mode[mode] = summary
        print(f"\n== {mode} ==\n{json.dumps({k: v for k, v in summary.items() if k != 'by_category'}, ensure_ascii=False)}")

    # ── Gates ─────────────────────────────────────────────────────────────
    for mode, s in per_mode.items():
        rep.add(f"{mode}.repealed_leaks", s["repealed_leaks"] == 0, s["repealed_leaks"], 0)

    if PRIMARY_MODE in per_mode:
        s = per_mode[PRIMARY_MODE]
        rep.add(f"{PRIMARY_MODE}.recall@10", s.get("recall@10", 0) >= GATE_RECALL10, s.get("recall@10"), f">={GATE_RECALL10}")
        rep.add(f"{PRIMARY_MODE}.evidence_hit@6", s.get("evidence_hit@6", 0) >= GATE_EVIDENCE_HIT6, s.get("evidence_hit@6"), f">={GATE_EVIDENCE_HIT6}")
        if "exact_citation_hit@1" in s:
            rep.add(f"{PRIMARY_MODE}.exact_citation_hit@1", s["exact_citation_hit@1"] >= GATE_EXACT_CITATION_HIT1, s["exact_citation_hit@1"], f">={GATE_EXACT_CITATION_HIT1}")
        else:
            rep.add("gold.has_exact_citation_queries", False, 0, ">0", "add exact_citation queries to the gold set")
        if "asof_correct" in s:
            rep.add(f"{PRIMARY_MODE}.asof_correct", s["asof_correct"] >= GATE_ASOF_CORRECT, s["asof_correct"], f">={GATE_ASOF_CORRECT}")
        rep.add(f"{PRIMARY_MODE}.latency_p95_ms", s["latency_p95_ms"] <= GATE_P95_MS, s["latency_p95_ms"], f"<={GATE_P95_MS}")
        for baseline in ("vector", "bm25"):
            if baseline in per_mode:
                a, b = s.get("ndcg@10", 0), per_mode[baseline].get("ndcg@10", 0)
                rep.add(f"ablation.{PRIMARY_MODE}_beats_{baseline}.ndcg@10", a > b, f"{a} vs {b}", ">")
    else:
        rep.add("modes.primary_present", False, modes, PRIMARY_MODE)

    # ── ACL leak test (restricted user must never see other collections) ──
    restricted_token = env("API_RESTRICTED_TOKEN", required=False)
    if restricted_token:
        allowed = {int(x) for x in env("RESTRICTED_ALLOWED_COLLECTIONS").split(",") if x.strip()}
        leaks = 0
        checked = 0
        for q in gold:
            q2 = {**q, "collections": None}  # ask for everything; server must scope to the user's ACL
            res = search(client, restricted_token, q2, PRIMARY_MODE if PRIMARY_MODE in modes else modes[-1], args.top_k)
            for r in res.get("results", []):
                checked += 1
                if int(r["collection_id"]) not in allowed:
                    leaks += 1
        rep.add("acl.leaks", leaks == 0, f"{leaks}/{checked}", 0)
    else:
        rep.add("acl.test_configured", False, "API_RESTRICTED_TOKEN not set", "set it", "ACL leak test is mandatory")

    rep.write({"per_mode": per_mode, "per_query": per_query_rows, "gold_size": len(gold)})
    rep.exit()


if __name__ == "__main__":
    main()
