"""Retrieval metrics over ranked unit IDs (binary relevance). Run this file for self-tests."""
from __future__ import annotations

import math
from typing import Sequence


def dedupe_units(ranked: Sequence[str]) -> list[str]:
    """Collapse chunk-level results to unit-level, keeping first occurrence (best rank)."""
    seen: set[str] = set()
    out: list[str] = []
    for u in ranked:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def hit_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    return 1.0 if set(ranked[:k]) & relevant else 0.0


def mrr_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    for i, u in enumerate(ranked[:k], start=1):
        if u in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, u in enumerate(ranked[:k], start=1) if u in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    idx = (len(s) - 1) * p
    lo, hi = math.floor(idx), math.ceil(idx)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _selftest() -> None:
    ranked = ["a", "x", "b", "y", "c"]
    rel = {"a", "b", "z"}
    assert recall_at_k(ranked, rel, 5) == 2 / 3
    assert hit_at_k(ranked, rel, 1) == 1.0
    assert hit_at_k(["x", "y"], rel, 2) == 0.0
    assert mrr_at_k(["x", "a"], rel, 10) == 0.5
    assert abs(ndcg_at_k(["a", "b", "z"], rel, 3) - 1.0) < 1e-9
    assert abs(ndcg_at_k(["x", "a"], {"a"}, 10) - 1 / math.log2(3)) < 1e-9
    assert dedupe_units(["a", "a", "b", "a"]) == ["a", "b"]
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    print("metrics self-test: OK")


if __name__ == "__main__":
    _selftest()
