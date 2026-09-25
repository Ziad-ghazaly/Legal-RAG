import hashlib

import pytest

from app.ingestion.chunker import chunk_unit, context_header
from app.ingestion.contract import DocumentIn, UnitIn
from app.text.arabic import normalize_for_search


async def words(texts: list[str]) -> list[int]:
    return [len(t.split()) for t in texts]


def doc(**kw: object) -> DocumentIn:
    base = {
        "doc_id": "kw-law-6-2010",
        "doc_type": "law",
        "title_ar": "قانون رقم 6 لسنة 2010 في شأن العمل في القطاع الأهلي",
        "units": [{"unit_id": "u", "level": "article", "text": "x"}],
    }
    return DocumentIn.model_validate(base | kw)


def unit(text: str, **kw: object) -> UnitIn:
    base = {"unit_id": "kw-law-6-2010/a41", "level": "article", "path": ["الباب الخامس"],
            "article_number": 41, "article_label": "المادة 41", "text": text}
    return UnitIn.model_validate(base | kw)


ARTICLE = "يستحق العامل إجازة سنوية مدفوعة الأجر مدتها ثلاثون يوماً ولا يجوز للعامل التنازل عنها."


def test_context_header_format() -> None:
    assert context_header(doc(), unit(ARTICLE)) == (
        "قانون: قانون رقم 6 لسنة 2010 في شأن العمل في القطاع الأهلي — الباب الخامس — المادة 41"
    )


@pytest.mark.asyncio
async def test_short_article_is_one_article_chunk() -> None:
    chunks, dropped = await chunk_unit(doc(), unit(ARTICLE), words)
    assert dropped == []
    (c,) = chunks
    assert c.chunk_kind == "article" and c.text == ARTICLE and c.unit_id == "kw-law-6-2010/a41"
    assert c.text_norm == normalize_for_search(c.context_header + "\n" + ARTICLE)
    assert c.content_hash == hashlib.sha256(normalize_for_search(ARTICLE).encode()).hexdigest()
    assert c.token_count == len((c.context_header + "\n" + ARTICLE).split())


@pytest.mark.asyncio
async def test_long_article_splits_at_clause_markers_within_budget() -> None:
    clause = "يلتزم صاحب العمل بتوفير وسائل السلامة المهنية للعمال في جميع مواقع العمل " * 3
    text = f"أولاً: {clause}\nثانياً: {clause}\nثالثاً: {clause}"
    chunks, _ = await chunk_unit(doc(), unit(text), words, max_tokens=60)
    assert len(chunks) == 3
    assert {c.chunk_kind for c in chunks} == {"clause_split"}
    assert [c.text.split(":")[0] for c in chunks] == ["أولاً", "ثانياً", "ثالثاً"]
    assert all(c.token_count <= 60 for c in chunks)
    assert {c.unit_id for c in chunks} == {"kw-law-6-2010/a41"}


@pytest.mark.asyncio
async def test_clause_without_markers_falls_back_to_sentences() -> None:
    sentence = "يلتزم صاحب العمل بتوفير وسائل السلامة المهنية للعمال في جميع مواقع العمل."
    chunks, _ = await chunk_unit(doc(), unit(" ".join([sentence] * 8)), words, max_tokens=60)
    assert len(chunks) > 1
    assert all(c.token_count <= 60 for c in chunks)


@pytest.mark.asyncio
async def test_boilerplate_is_dropped_with_reason() -> None:
    chunks, dropped = await chunk_unit(doc(), unit("صدر بقصر السيف في 21 فبراير 2010\n12"), words)
    assert chunks == [] and dropped[0]["reason"] == "boilerplate"
    chunks, _ = await chunk_unit(doc(), unit(ARTICLE + "\nصدر بقصر السيف في 21 فبراير 2010"), words)
    assert chunks[0].text == ARTICLE


@pytest.mark.asyncio
async def test_tiny_unit_is_dropped() -> None:
    chunks, dropped = await chunk_unit(doc(), unit("ملغاة."), words)
    assert chunks == [] and dropped[0]["reason"] == "tiny"


@pytest.mark.asyncio
async def test_low_arabic_text_is_dropped() -> None:
    chunks, dropped = await chunk_unit(doc(), unit("This article was published in the official gazette issue 1234."), words)
    assert chunks == [] and dropped[0]["reason"] == "low_arabic_ratio"


@pytest.mark.asyncio
async def test_ruling_sections_become_semantic_chunks_with_overlap() -> None:
    s = [f"وحيث إن الطاعن ينعى على الحكم المطعون فيه الخطأ في تطبيق القانون في الوجه رقم {i}." for i in range(10)]
    ruling = doc(doc_type="court_ruling", title_ar="حكم محكمة التمييز")
    u = unit(" ".join(s), level="section", article_number=None, article_label="الأسباب", path=[])
    chunks, _ = await chunk_unit(ruling, u, words, max_tokens=60)
    assert len(chunks) > 1 and {c.chunk_kind for c in chunks} == {"semantic"}
    last_sentence_of_first = chunks[0].text.split(". ")[-1].rstrip(".")
    assert last_sentence_of_first in chunks[1].text  # one-sentence overlap


@pytest.mark.asyncio
async def test_table_stays_one_chunk_and_long_tables_repeat_header() -> None:
    header_row = "| البند | الغرامة |"
    rows = [f"| مخالفة رقم {i} في أحكام القانون | {i}00 دينار |" for i in range(30)]
    u = unit("\n".join([header_row, *rows]), level="table", article_number=None, article_label="جدول")
    chunks, _ = await chunk_unit(doc(), u, words, max_tokens=80)
    assert len(chunks) > 1 and {c.chunk_kind for c in chunks} == {"table"}
    assert all(c.text.startswith(header_row) for c in chunks)
    assert all(c.token_count <= 80 for c in chunks)
