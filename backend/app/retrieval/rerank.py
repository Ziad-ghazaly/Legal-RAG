"""Cross-encoder rerank via TEI /rerank. Returns raw logits in input order."""

from app.core.config import get_settings
from app.retrieval.embedder import post_tei

_BATCH = 8  # small requests keep each call well inside the timeout on CPU


async def rerank(query: str, texts: list[str]) -> list[float]:
    url = f"{get_settings().tei_rerank_url}/rerank"
    scores: list[float] = []
    for start in range(0, len(texts), _BATCH):
        batch = texts[start : start + _BATCH]
        payload = {"query": query, "texts": batch, "raw_scores": True, "truncate": True}
        data = await post_tei(url, payload, timeout=get_settings().tei_rerank_timeout_s)
        part = [0.0] * len(batch)
        for item in data:
            part[item["index"]] = float(item["score"])
        scores.extend(part)
    return scores
