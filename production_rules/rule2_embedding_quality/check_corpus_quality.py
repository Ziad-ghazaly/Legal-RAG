"""
Rule 2 — Embedding quality > quantity.

Audits the indexed corpus for duplicates, bad boundaries, noise, and missing
legal metadata. Exits 1 if any hard check fails.

Usage:
    python -m production_rules.rule2_embedding_quality.check_corpus_quality [--collection ID] [--nn-sample 300]
"""
from __future__ import annotations

import argparse

from production_rules._common import Report, db_connect, env

# ── Thresholds (tighten as data gets cleaner; never loosen to make a batch pass) ──
MIN_TOKENS = 8
MAX_CHUNK_TOKENS = 450
RERANKER_MAX_TOKENS = 512
NEAR_DUP_COS = 0.98
MAX_NEAR_DUP_SHARE = 0.01
MAX_TINY_SHARE = 0.005
MAX_OVERSIZE_SHARE = 0.01
MIN_ARABIC_RATIO = 0.6
MAX_LOW_ARABIC_SHARE = 0.01
BOILERPLATE_MIN_DOCS = 20

LEGISLATION_TYPES = ("constitution", "law", "decree_law", "decree", "regulation", "ministerial_decision", "circular")
# Article heading at line start: "المادة 12", "مادة (١٢)", "المادة الأولى"
ARTICLE_HEADING_RE = r"(^|\n)\s*(ال)?مادة\s*\(?\s*([0-9٠-٩]+|ال[^\s]+)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", type=int, default=None, help="limit to one collection_id")
    ap.add_argument("--nn-sample", type=int, default=300)
    args = ap.parse_args()

    cfg_model = env("EMBEDDING_MODEL")
    rep = Report("rule2_embedding_quality")
    conn = db_connect()
    cur = conn.cursor()

    scope = "TRUE" if args.collection is None else f"c.collection_id = {int(args.collection)}"

    cur.execute(f"SELECT count(*) FROM chunks c WHERE {scope}")
    total = cur.fetchone()[0]
    if total == 0:
        rep.add("corpus.non_empty", False, 0, ">0")
        rep.write()
        rep.exit()

    def share(n: int) -> str:
        return f"{n} ({n / total:.2%})"

    # 1. exact duplicates
    cur.execute(
        f"""SELECT c.collection_id, c.content_hash, count(*) AS n, array_agg(c.id ORDER BY c.id) AS ids
            FROM chunks c WHERE {scope}
            GROUP BY 1, 2 HAVING count(*) > 1 ORDER BY n DESC LIMIT 20"""
    )
    dup_groups = cur.fetchall()
    rep.add("dedup.exact_duplicate_groups", len(dup_groups) == 0, len(dup_groups), 0,
            f"top: {[(g[1][:10], g[2]) for g in dup_groups[:5]]}")

    # 2. near-duplicates via nearest neighbour on a sample
    cur.execute(
        f"""SELECT c.id, c.unit_id, c.collection_id FROM chunks c
            WHERE {scope} AND c.embedding_model = %s ORDER BY random() LIMIT %s""",
        (cfg_model, args.nn_sample),
    )
    sample = cur.fetchall()
    near = []
    for cid, uid, coll in sample:
        cur.execute(
            """SELECT n.id, 1 - (n.embedding <=> c.embedding) AS cos
               FROM chunks c, chunks n
               WHERE c.id = %s AND n.id <> c.id AND n.unit_id <> c.unit_id
                 AND n.collection_id = %s AND n.embedding_model = %s
               ORDER BY n.embedding <=> c.embedding LIMIT 1""",
            (cid, coll, cfg_model),
        )
        row = cur.fetchone()
        if row and row[1] >= NEAR_DUP_COS:
            near.append((cid, row[0], round(float(row[1]), 4)))
    nd_share = len(near) / max(1, len(sample))
    rep.add("dedup.near_duplicate_share", nd_share <= MAX_NEAR_DUP_SHARE, f"{nd_share:.2%} of {len(sample)}",
            f"<={MAX_NEAR_DUP_SHARE:.0%} at cos>={NEAR_DUP_COS}", f"pairs: {near[:5]}")

    # 3. tiny chunks
    cur.execute(f"SELECT count(*) FROM chunks c WHERE {scope} AND c.token_count < %s", (MIN_TOKENS,))
    n = cur.fetchone()[0]
    rep.add("size.tiny_chunks", n / total <= MAX_TINY_SHARE, share(n), f"<={MAX_TINY_SHARE:.1%}")

    # 4. oversize (tables excluded)
    cur.execute(f"SELECT count(*) FROM chunks c WHERE {scope} AND c.token_count > %s AND c.chunk_kind <> 'table'",
                (MAX_CHUNK_TOKENS,))
    n = cur.fetchone()[0]
    rep.add("size.oversize_chunks", n / total <= MAX_OVERSIZE_SHARE, share(n), f"<={MAX_OVERSIZE_SHARE:.0%} over {MAX_CHUNK_TOKENS}")

    # 5. over reranker limit
    cur.execute(f"SELECT count(*) FROM chunks c WHERE {scope} AND c.token_count > %s", (RERANKER_MAX_TOKENS,))
    n = cur.fetchone()[0]
    rep.add("size.over_reranker_limit", n == 0, share(n), f"0 over {RERANKER_MAX_TOKENS}")

    # 6. merged articles
    cur.execute(
        f"""SELECT c.id FROM chunks c WHERE {scope} AND c.chunk_kind = 'article'
            AND regexp_count(c.text, %s) >= 2 LIMIT 50""",
        (ARTICLE_HEADING_RE,),
    )
    merged = [r[0] for r in cur.fetchall()]
    rep.add("boundaries.merged_articles", len(merged) == 0, len(merged), 0, f"ids: {merged[:10]}")

    # 7. legislation articles missing article_number
    cur.execute(
        f"""SELECT count(*) FROM chunks c JOIN units u ON u.id = c.unit_id
            WHERE {scope} AND c.doc_type = ANY(%s) AND c.chunk_kind IN ('article','clause_split')
              AND u.article_number IS NULL""",
        (list(LEGISLATION_TYPES),),
    )
    n = cur.fetchone()[0]
    rep.add("metadata.article_number_missing", n == 0, share(n), 0)

    # 8. missing context header
    cur.execute(f"SELECT count(*) FROM chunks c WHERE {scope} AND coalesce(trim(c.context_header), '') = ''")
    n = cur.fetchone()[0]
    rep.add("metadata.context_header_missing", n == 0, share(n), 0)

    # 9. low Arabic ratio
    cur.execute(
        f"""SELECT count(*) FROM (
              -- numerator: Arabic letters only; denominator: all chars minus spaces, digits,
              -- punctuation (Latin + Arabic), tashkeel and tatweel
              SELECT length(regexp_replace(c.text, '[^\\u0621-\\u064A]', '', 'g'))::float
                     / nullif(length(regexp_replace(c.text,
                         '[\\s0-9٠-٩[:punct:]\\u060C\\u061B\\u061F\\u00AB\\u00BB\\u064B-\\u065F\\u0640]', '', 'g')), 0) AS r
              FROM chunks c WHERE {scope} AND c.chunk_kind <> 'table') t
            WHERE r IS NULL OR r < %s""",
        (MIN_ARABIC_RATIO,),
    )
    n = cur.fetchone()[0]
    rep.add("noise.low_arabic_ratio", n / total <= MAX_LOW_ARABIC_SHARE, share(n), f"<={MAX_LOW_ARABIC_SHARE:.0%} below {MIN_ARABIC_RATIO}")

    # 10. orphans
    cur.execute(
        f"""SELECT count(*) FROM chunks c
            LEFT JOIN units u ON u.id = c.unit_id
            LEFT JOIN documents d ON d.id = c.document_id
            WHERE {scope} AND (u.id IS NULL OR d.id IS NULL)"""
    )
    n = cur.fetchone()[0]
    rep.add("integrity.orphan_chunks", n == 0, n, 0)

    # 11. boilerplate candidates (warn only)
    cur.execute(
        f"""SELECT left(c.text_norm, 80) AS head, count(DISTINCT c.document_id) AS docs
            FROM chunks c WHERE {scope}
            GROUP BY 1 HAVING count(DISTINCT c.document_id) >= %s
            ORDER BY docs DESC LIMIT 15""",
        (BOILERPLATE_MIN_DOCS,),
    )
    boiler = cur.fetchall()
    rep.add("noise.boilerplate_candidates (warn)", True, len(boiler), f"review if >0 (≥{BOILERPLATE_MIN_DOCS} docs)",
            " | ".join(f"{h[:40]}…×{d}" for h, d in boiler[:5]))

    # 12. distribution (info)
    cur.execute(
        f"""SELECT percentile_cont(ARRAY[0.05,0.5,0.95]) WITHIN GROUP (ORDER BY c.token_count)
            FROM chunks c WHERE {scope}"""
    )
    p = cur.fetchone()[0]
    cur.execute(f"SELECT c.doc_type, count(*) FROM chunks c WHERE {scope} GROUP BY 1 ORDER BY 2 DESC")
    by_type = dict(cur.fetchall())
    rep.add("info.token_p5_p50_p95", True, p, "info")
    rep.add("info.chunks_by_doc_type", True, by_type, "info", f"total={total}")

    rep.write({"total_chunks": total, "near_duplicate_pairs": near, "merged_article_ids": merged})
    rep.exit()


if __name__ == "__main__":
    main()
