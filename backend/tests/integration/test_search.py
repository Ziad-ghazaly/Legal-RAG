"""Retrieval pipeline on real ParadeDB (pgvector + pg_search) with fake TEI."""

import math
import re
from dataclasses import replace
from datetime import date

import pytest

from app.ingestion.contract import DocumentIn
from app.ingestion.indexer import index_documents
from app.retrieval.search import SearchParams, search
from app.text.arabic import normalize_for_search
from tests.integration.conftest import fake_count, fake_embed

ANNUAL = "يستحق العامل إجازة سنوية مدفوعة الأجر مدتها ثلاثون يوماً ولا يجوز للعامل التنازل عنها."
NOTICE = "لا يجوز لصاحب العمل إنهاء عقد العمل غير محدد المدة إلا بعد إخطار العامل قبل ثلاثة أشهر."
SHIPS = "تسري أحكام هذا القانون على السفن التجارية المسجلة في دولة الكويت وعلى طواقمها."
OLD_NOTICE = "لا يجوز لصاحب العمل إنهاء عقد العمل إلا بعد إخطار العامل قبل شهر واحد فقط."


async def fake_rerank(query: str, texts: list[str]) -> list[float]:
    """Logit grows with shared words: 0 shared → -4 (p≈0.02), 3+ shared → positive."""
    q = set(re.findall(r"\w+", normalize_for_search(query)))
    return [2.0 * len(q & set(re.findall(r"\w+", normalize_for_search(t)))) - 4.0 for t in texts]


def law(doc_id: str, number: str, units: list[dict], status: str = "in_force") -> DocumentIn:
    return DocumentIn.model_validate({
        "doc_id": doc_id, "doc_type": "law", "number": number, "year": 2010, "status": status,
        "title_ar": f"قانون رقم {number} لسنة 2010", "effective_date": "2010-02-21", "units": units,
    })


def art(uid: str, n: int, text: str, **kw: object) -> dict:
    return {"unit_id": uid, "level": "article", "article_number": n, "article_label": f"المادة {n}",
            "text": text, **kw}


@pytest.fixture
async def corpus(pg, monkeypatch):
    from app.retrieval import embedder, rerank

    monkeypatch.setattr(embedder, "embed_texts", fake_embed)
    monkeypatch.setattr(rerank, "rerank", fake_rerank)
    labor = law("labor", "6", [
        art("labor/a41", 41, ANNUAL),
        art("labor/a44-old", 44, OLD_NOTICE, valid_from="2010-02-21", valid_to="2016-01-01"),
        art("labor/a44", 44, NOTICE, valid_from="2016-01-01"),
    ])
    ships = law("ships", "9", [art("ships/a1", 1, SHIPS)])
    repealed = law("old", "1", [art("old/a3", 3, ANNUAL + " وتضاف إليها العطلات الرسمية")], status="repealed")
    secret = law("secret", "7", [art("secret/a2", 2, NOTICE + " في القطاع النفطي")])
    for docs, coll in (([labor, ships, repealed], 1), ([secret], 2)):
        await index_documents(pg, docs, collection_id=coll, count_tokens=fake_count, embed=fake_embed)
    return pg


def units(result) -> list[str]:
    return [h.unit_id for h in result.hits]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["vector", "bm25", "hybrid", "hybrid_rerank", "full"])
async def test_acl_and_repealed_filters_hold_in_every_mode(corpus, mode) -> None:
    q = SearchParams(query="إخطار العامل قبل إنهاء عقد العمل والإجازة السنوية", mode=mode, top_k=20)
    got = units(await search(corpus, q, allowed_collections=[1]))
    assert got, mode
    assert not any(u.startswith("secret/") for u in got)  # collection 2 is not allowed
    assert "old/a3" not in got  # repealed
    got = units(await search(corpus, q, allowed_collections=None))  # admin: all collections
    assert "secret/a2" in got


@pytest.mark.asyncio
async def test_include_repealed_returns_repealed_chunks(corpus) -> None:
    q = SearchParams(query="الإجازة السنوية العطلات الرسمية", mode="bm25", include_repealed=True)
    res = await search(corpus, q, allowed_collections=[1])
    assert "old/a3" in units(res)
    assert next(h for h in res.hits if h.unit_id == "old/a3").status == "repealed"


@pytest.mark.asyncio
async def test_as_of_date_selects_the_version_in_force(corpus) -> None:
    q = SearchParams(query="إخطار العامل قبل إنهاء عقد العمل", mode="bm25")
    before = units(await search(corpus, replace(q, as_of_date=date(2012, 1, 1)), allowed_collections=[1]))
    after = units(await search(corpus, replace(q, as_of_date=date(2020, 1, 1)), allowed_collections=[1]))
    assert "labor/a44-old" in before and "labor/a44" not in before
    assert "labor/a44" in after and "labor/a44-old" not in after


@pytest.mark.asyncio
async def test_bm25_matches_eastern_digit_article_reference(corpus) -> None:
    res = await search(corpus, SearchParams(query="المادة ٤١", mode="bm25"), allowed_collections=[1])
    assert units(res)[0] == "labor/a41"


@pytest.mark.asyncio
async def test_full_mode_pins_cited_article_first_and_cuts_noise(corpus) -> None:
    q = SearchParams(query="ما حكم السفن التجارية وفق المادة ٤١ من القانون رقم ٦ لسنة ٢٠١٠", mode="full")
    res = await search(corpus, q, allowed_collections=[1])
    assert res.hits[0].unit_id == "labor/a41" and res.hits[0].pinned
    assert all(h.pinned or h.p >= 0.15 for h in res.hits)
    for h in res.hits:
        assert math.isclose(h.final, h.p * (0.85 + 0.15 * h.authority))


@pytest.mark.asyncio
async def test_pinning_respects_acl(corpus) -> None:
    q = SearchParams(query="المادة 2 من القانون رقم 7 لسنة 2010", mode="full")
    assert "secret/a2" not in units(await search(corpus, q, allowed_collections=[1]))


@pytest.mark.asyncio
async def test_hits_carry_intermediate_scores(corpus) -> None:
    res = await search(corpus, SearchParams(query="إخطار العامل قبل إنهاء عقد العمل", mode="full"),
                       allowed_collections=[1])
    top = res.hits[0]
    assert top.unit_id == "labor/a44"
    assert top.vector_rank is not None and top.bm25_rank is not None and top.rrf > 0
    assert top.rerank_logit is not None and 0 < top.p <= 1
    assert res.latency_ms > 0
