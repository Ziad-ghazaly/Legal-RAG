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
    assert c.collection_id == 1 and c.doc_type == "law" and c.authority_level == 0.7
    assert c.embedding_model == "BAAI/bge-m3" and len(c.embedding) == 1024
    assert c.status == "in_force" and c.valid_from == date(2010, 2, 21)
    assert c.context_header.endswith("المادة 41") and c.chunk_kind == "article"
    doc = await pg.get(Document, "kw-law-6-2010")
    assert doc.collection_id == 1 and doc.authority_level == 0.7


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


@pytest.mark.asyncio
async def test_duplicate_keeps_the_in_force_copy_over_a_repealed_one(pg) -> None:
    """Final-review #4: a repealed law ingested first must not swallow the in-force re-enactment."""
    old = law(doc_id="old-law", status="repealed", units=[
        {"unit_id": "old-law/a41", "level": "article", "article_number": 41, "text": A41}])
    new = law(doc_id="new-law", units=[
        {"unit_id": "new-law/a41", "level": "article", "article_number": 41, "text": A41}])
    await index_documents(pg, [old], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    stats = await index_documents(pg, [new], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    units = set((await pg.execute(select(Chunk.unit_id))).scalars())
    assert units == {"new-law/a41"}
    assert stats["chunks"] == 1 and stats["dropped"][0]["reason"] == "superseded_duplicate"
    # and the other order: the repealed copy arriving later is the one dropped
    stats = await index_documents(pg, [old], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    assert set((await pg.execute(select(Chunk.unit_id))).scalars()) == {"new-law/a41"}
    assert stats["dropped"][0]["reason"] == "duplicate"


@pytest.mark.asyncio
async def test_unit_status_notes_and_order_are_persisted(pg) -> None:
    units = [
        {"unit_id": "c/a3", "level": "article", "article_number": 3, "text": A44},
        {"unit_id": "c/a1", "level": "article", "article_number": 1, "text": A41,
         "status": "suspended", "notes": ["تم وقف العمل بالمادة عملا بالامر الاميري المؤرخ 10 / 5 / 2024"]},
        {"unit_id": "c/a2", "level": "article", "article_number": 2,
         "text": "ملغاة — ملغاة بموجب القانون رقم 31 لسنة 1970 وحل محلها المواد من 1 إلى 34", "status": "repealed"},
    ]
    await index_documents(pg, [law(doc_id="c", units=units)], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    rows = (await pg.execute(select(Unit.id, Unit.status, Unit.notes, Unit.position).order_by(Unit.position))).all()
    assert [r.id for r in rows] == ["c/a3", "c/a1", "c/a2"]
    assert [r.status for r in rows] == ["in_force", "suspended", "repealed"]
    assert rows[1].notes[0].startswith("تم وقف")
    chunk_status = dict((await pg.execute(select(Chunk.unit_id, Chunk.status))).all())
    assert chunk_status == {"c/a3": "in_force", "c/a1": "suspended", "c/a2": "repealed"}


@pytest.mark.asyncio
async def test_concurrent_jobs_do_not_both_keep_the_same_content(pg) -> None:
    """Two ingestion jobs in one collection racing on identical text keep a single copy."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession

    async def slow_embed(texts: list[str]) -> list[list[float]]:
        await asyncio.sleep(0.5)
        return await fake_embed(texts)

    async with AsyncSession(pg.bind, expire_on_commit=False) as other:
        await asyncio.gather(
            index_documents(pg, [law()], collection_id=1, count_tokens=fake_count, embed=slow_embed),
            index_documents(other, [law(doc_id="kw-law-6-2010-copy")], collection_id=1,
                            count_tokens=fake_count, embed=slow_embed),
        )
    hashes = (await pg.execute(select(Chunk.content_hash, func.count()).group_by(Chunk.content_hash))).all()
    assert hashes and all(n == 1 for _, n in hashes)
