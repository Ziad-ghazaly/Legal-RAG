import json
from datetime import date

from app.ingestion.contract import parse_jsonl

GOOD = {
    "doc_id": "kw-law-6-2010",
    "doc_type": "law",
    "title_ar": "قانون رقم 6 لسنة 2010 في شأن العمل في القطاع الأهلي",
    "number": "6",
    "year": 2010,
    "effective_date": "2010-02-21",
    "status": "in_force",
    "legal_domain": ["labor"],
    "units": [
        {
            "unit_id": "kw-law-6-2010/a41",
            "level": "article",
            "path": ["الباب الخامس"],
            "article_number": 41,
            "article_label": "المادة 41",
            "text": "يستحق العامل إجازة سنوية مدفوعة الأجر مدتها ثلاثون يوماً.",
            "valid_from": "2010-02-21",
        }
    ],
}


def _jsonl(*rows: object) -> bytes:
    return "\n".join(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows).encode()


def test_valid_row_parses_with_typed_fields() -> None:
    docs, errors = parse_jsonl(_jsonl(GOOD))
    assert errors == []
    (doc,) = docs
    assert doc.doc_id == "kw-law-6-2010" and doc.year == 2010
    assert doc.units[0].unit_type == "article"  # "level" is an alias
    assert doc.units[0].valid_from == date(2010, 2, 21)


def test_bad_rows_are_reported_with_line_numbers_and_job_continues() -> None:
    bad_type = {**GOOD, "doc_id": "x", "doc_type": "blog_post"}
    docs, errors = parse_jsonl(_jsonl(GOOD, "{not json", bad_type, "", GOOD | {"doc_id": "y"}))
    assert [d.doc_id for d in docs] == ["kw-law-6-2010", "y"]
    assert [e["line"] for e in errors] == [2, 3]
    assert all(e["error"] for e in errors)


def test_document_without_units_is_rejected() -> None:
    _, errors = parse_jsonl(_jsonl({**GOOD, "units": []}))
    assert errors and errors[0]["line"] == 1


def test_eastern_digit_article_numbers_are_accepted() -> None:
    row = {**GOOD, "units": [{**GOOD["units"][0], "article_number": "٤١"}]}
    docs, errors = parse_jsonl(_jsonl(row))
    assert errors == [] and docs[0].units[0].article_number == 41


def test_law_numbers_are_normalized_like_citations() -> None:
    """Final-review #8: '٦', '06', ' 6 ' must all pin 'القانون رقم 6'."""
    for raw in ("٦", "06", " 6 "):
        docs, errors = parse_jsonl(_jsonl({**GOOD, "number": raw}))
        assert errors == [] and docs[0].number == "6"
