from datetime import date

import pytest
from sqlalchemy import func, select

from app.db.models import Chunk, Document, Unit
from app.ingestion.contract import DocumentIn
from app.ingestion.indexer import index_documents
from tests.integration.conftest import fake_count, fake_embed

A41 = "يستحق العامل إجازة سنوية مدفوعة الأجر مدتها ثلاثون يوماً ولا يجوز للعامل التنازل عنها."
A44 = "لا يجوز لصاحب العمل إنهاء عقد العمل غير محدد المدة إلا بعد إخطار العامل قبل ثلاثة أشهر."


def law(doc_id: str = "kw-law-6-2010", status: str = "in_force", units: list | None = None) -> DocumentIn:
    return DocumentIn.model_validate(
        {
            "doc_id": doc_id,
            "doc_type": "law",
            "title_ar": "قانون رقم 6 لسنة 2010 في شأن العمل في القطاع الأهلي",
            "number": "6",
            "year": 2010,
            "effective_date": "2010-02-21",
            "status": status,
            "units": units
            or [
                {"unit_id": f"{doc_id}/a41", "level": "article", "article_number": 41,
                 "article_label": "المادة 41", "text": A41},
                {"unit_id": f"{doc_id}/a44", "level": "article", "article_number": 44,
                 "article_label": "المادة 44", "text": A44},
            ],
        }
    )


async def counts(pg) -> tuple[int, int, int]:
    return tuple([(await pg.execute(select(func.count()).select_from(m))).scalar_one() for m in (Document, Unit, Chunk)])


@pytest.mark.asyncio
async def test_index_writes_documents_units_chunks_with_metadata(pg) -> None:
    stats = await index_documents(pg, [law()], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    assert (stats["documents"], stats["units"], stats["chunks"]) == (1, 2, 2)
    assert await counts(pg) == (1, 2, 2)
    c = (await pg.execute(select(Chunk).where(Chunk.unit_id == "kw-law-6-2010/a41"))).scalar_one()
    assert c.collection_id == 1 and c.doc_type == "law" and c.authority_level == 0.9
    assert c.embedding_model == "BAAI/bge-m3" and len(c.embedding) == 1024
    assert c.status == "in_force" and c.valid_from == date(2010, 2, 21)
    assert c.context_header.endswith("المادة 41") and c.chunk_kind == "article"
    doc = await pg.get(Document, "kw-law-6-2010")
    assert doc.collection_id == 1 and doc.authority_level == 0.9


@pytest.mark.asyncio
async def test_reingesting_same_doc_replaces_it(pg) -> None:
    await index_documents(pg, [law()], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    one = law(units=[{"unit_id": "kw-law-6-2010/a41", "level": "article", "article_number": 41,
                      "article_label": "المادة 41", "text": A41}])
    await index_documents(pg, [one], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    assert await counts(pg) == (1, 1, 1)


@pytest.mark.asyncio
async def test_duplicate_content_in_same_collection_is_dropped(pg) -> None:
    await index_documents(pg, [law()], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    copy = law(doc_id="kw-law-6-2010-copy")
    stats = await index_documents(pg, [copy], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    assert stats["chunks"] == 0
    assert {d["reason"] for d in stats["dropped"]} == {"duplicate"}
    # same content in another collection is allowed (ACL scopes differ)
    stats = await index_documents(pg, [law(doc_id="other")], collection_id=2, count_tokens=fake_count, embed=fake_embed)
    assert stats["chunks"] == 2


@pytest.mark.asyncio
async def test_repealed_documents_and_amended_units_get_status(pg) -> None:
    units = [
        {"unit_id": "d/a1-old", "level": "article", "article_number": 1, "article_label": "المادة 1",
         "text": A41, "valid_from": "2010-02-21", "valid_to": "2016-01-01"},
        {"unit_id": "d/a1-new", "level": "article", "article_number": 1, "article_label": "المادة 1",
         "text": A44, "valid_from": "2016-01-01"},
    ]
    await index_documents(pg, [law(doc_id="d", units=units)], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    rows = dict((await pg.execute(select(Chunk.unit_id, Chunk.status))).all())
    assert rows == {"d/a1-old": "amended", "d/a1-new": "in_force"}
    await index_documents(pg, [law(doc_id="r", status="repealed")], collection_id=2, count_tokens=fake_count, embed=fake_embed)
    statuses = (await pg.execute(select(Chunk.status).where(Chunk.document_id == "r"))).scalars().all()
    assert set(statuses) == {"repealed"}


@pytest.mark.asyncio
async def test_bad_document_is_reported_and_others_continue(pg) -> None:
    clash = law(doc_id="clash", units=[{"unit_id": "kw-law-6-2010/a41", "level": "article",
                                        "article_number": 41, "text": A44}])
    stats = await index_documents(pg, [law(), clash, law(doc_id="ok2", units=[
        {"unit_id": "ok2/a1", "level": "article", "article_number": 1, "text": A44 + " إضافة"}])],
        collection_id=1, count_tokens=fake_count, embed=fake_embed)
    assert [e["doc_id"] for e in stats["errors"]] == ["clash"]
    assert stats["documents"] == 2
