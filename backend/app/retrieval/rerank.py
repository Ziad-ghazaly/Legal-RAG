"""Cross-encoder rerank via TEI /rerank. Returns raw logits in input order."""

from app.core.config import get_settings
from app.retrieval.embedder import post_tei

_BATCH = 32  # TEI max_client_batch_size


async def rerank(query: str, texts: list[str]) -> list[float]:
    url = f"{get_settings().tei_rerank_url}/rerank"
    scores: list[float] = []
    for start in range(0, len(texts), _BATCH):
        batch = texts[start : start + _BATCH]
        data = await post_tei(
            url, {"query": query, "texts": batch, "raw_scores": True, "truncate": True}
        )
        part = [0.0] * len(batch)
        for item in data:
            part[item["index"]] = float(item["score"])
        scores.extend(part)
    return scores
