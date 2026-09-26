"""Law browser API: list laws in the caller's ACL; a law's units in document order."""

import pytest

from app.ingestion.contract import DocumentIn
from app.ingestion.indexer import index_documents
from tests.integration.conftest import fake_count, fake_embed, login

ART = "يستحق العامل إجازة سنوية مدفوعة الأجر مدتها ثلاثون يوماً ولا يجوز للعامل التنازل عنها."


def doc(doc_id: str, number: str, units: list[dict], doc_type: str = "law") -> DocumentIn:
    return DocumentIn.model_validate({"doc_id": doc_id, "doc_type": doc_type, "number": number, "year": 2010,
                                      "title_ar": f"القانون رقم {number} لسنة 2010", "units": units})


@pytest.fixture
async def laws(api, pg):
    units = [
        {"unit_id": "labor/preamble", "level": "section", "article_label": "الديباجة", "text": "بعد الاطلاع على الدستور " + ART},
        {"unit_id": "labor/a2", "level": "article", "article_number": 2, "article_label": "المادة 2",
         "path": ["الباب الأول"], "text": ART + " الثانية", "notes": ["معدلة بالقانون رقم 1 لسنة 2020"]},
        {"unit_id": "labor/a1", "level": "article", "article_number": 1, "article_label": "المادة 1",
         "path": ["الباب الأول"], "text": "ملغاة — ملغاة بموجب القانون رقم 3 لسنة 2015 بشأن تنظيم العمل", "status": "repealed"},
    ]
    await index_documents(pg, [doc("labor", "6", units)], collection_id=1, count_tokens=fake_count, embed=fake_embed)
    await index_documents(pg, [doc("secret", "7", [{"unit_id": "secret/a1", "level": "article", "article_number": 1,
                                                    "text": ART + " سري"}])],
                          collection_id=2, count_tokens=fake_count, embed=fake_embed)
    admin = await login(api)
    await api.post("/api/v1/admin/users", headers=admin, json={
        "username": "lawyer", "password": "lawyer-pass", "role": "user", "collection_ids": [1]})
    return api


@pytest.mark.asyncio
async def test_law_list_is_scoped_to_the_callers_collections(laws) -> None:
    user = await login(laws, "lawyer", "lawyer-pass")
    items = (await laws.get("/api/v1/laws", headers=user)).json()
    assert [(x["id"], x["article_count"]) for x in items] == [("labor", 2)]
    assert items[0]["doc_type"] == "law" and items[0]["title_ar"] == "القانون رقم 6 لسنة 2010"
    admin = await login(laws)
    assert {x["id"] for x in (await laws.get("/api/v1/laws", headers=admin)).json()} == {"labor", "secret"}
    assert (await laws.get("/api/v1/laws/secret", headers=user)).status_code == 404


@pytest.mark.asyncio
async def test_law_units_come_in_document_order_with_status_and_notes(laws) -> None:
    user = await login(laws, "lawyer", "lawyer-pass")
    body = (await laws.get("/api/v1/laws/labor", headers=user)).json()
    assert body["document"]["title_ar"] == "القانون رقم 6 لسنة 2010"
    units = body["units"]
    assert [u["id"] for u in units] == ["labor/preamble", "labor/a2", "labor/a1"]
    assert units[1]["notes"] == ["معدلة بالقانون رقم 1 لسنة 2020"] and units[1]["path"] == ["الباب الأول"]
    assert units[2]["status"] == "repealed"
