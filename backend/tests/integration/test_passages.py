"""Final-review #3: a claim that retrieves chunk B of a multi-chunk unit must see B's text."""

from datetime import date

import pytest

from app.ingestion.contract import DocumentIn
from app.ingestion.indexer import index_documents
from app.verification.passages import gather_passages
from app.verification.types import ClaimIn
from tests.integration.conftest import fake_count, fake_embed
from tests.integration.test_search import fake_rerank

PART_A = "وحيث إن الإجازة السنوية حق أصيل للعامل لا يجوز حرمانه منه. " * 40
PART_B = "وحيث إن مكافأة نهاية الخدمة تحسب على أساس آخر أجر تقاضاه العامل. " * 40


@pytest.mark.asyncio
async def test_second_chunk_of_a_long_ruling_section_reaches_the_verifier(pg, monkeypatch) -> None:
    from app.retrieval import embedder, rerank

    monkeypatch.setattr(embedder, "aembed_texts", fake_embed)
    monkeypatch.setattr(rerank, "rerank", fake_rerank)
    ruling = DocumentIn.model_validate({
        "doc_id": "ruling-1", "doc_type": "court_ruling", "title_ar": "حكم التمييز في الطعن 1 لسنة 2020",
        "effective_date": "2020-01-01",
        "units": [{"unit_id": "ruling-1/reasons", "level": "section", "article_label": "الأسباب",
                   "text": PART_A + PART_B}],
    })
    stats = await index_documents(pg, [ruling], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    assert stats["chunks"] >= 2
    claims = [
        ClaimIn("C1", "الإجازة السنوية حق أصيل للعامل لا يجوز حرمانه منه", "legal_premise", "core", []),
        ClaimIn("C2", "مكافأة نهاية الخدمة تحسب على أساس آخر أجر تقاضاه العامل", "legal_premise", "core", []),
    ]
    per_claim, _ = await gather_passages(pg, claims, date(2026, 1, 1), None, None)
    assert any("مكافأة نهاية الخدمة" in p.text + (p.parent_text or "") for p in per_claim["C2"])
