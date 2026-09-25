import pytest

from app.ingestion.indexer import index_documents
from tests.integration.conftest import fake_count, fake_embed, login
from tests.integration.test_search import NOTICE, SHIPS, art, fake_rerank, law


@pytest.fixture
async def seeded(api, pg, monkeypatch):
    from app.retrieval import embedder, rerank

    monkeypatch.setattr(embedder, "aembed_texts", fake_embed)
    monkeypatch.setattr(rerank, "rerank", fake_rerank)
    await index_documents(pg, [law("labor", "6", [art("labor/a44", 44, NOTICE)]),
                               law("ships", "9", [art("ships/a1", 1, SHIPS)])],
                          collection_id=1, count_tokens=fake_count, embed=fake_embed)
    await index_documents(pg, [law("secret", "7", [art("secret/a2", 2, NOTICE + " في القطاع النفطي")])],
                          collection_id=2, count_tokens=fake_count, embed=fake_embed)
    admin = await login(api)
    for name, role in (("rev1", "reviewer"), ("user1", "user")):
        r = await api.post("/api/v1/admin/users", headers=admin, json={
            "username": name, "password": "pass-1234", "role": role, "collection_ids": [1]})
        assert r.status_code == 201
    return api


BODY = {"query": "إخطار العامل قبل إنهاء عقد العمل", "as_of_date": None, "collections": None,
        "mode": "full", "top_k": 10, "include_repealed": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/retrieval/search", "/api/v1/retrieval/search"])
async def test_search_contract_for_production_rules(seeded, path) -> None:
    r = await seeded.post(path, json=BODY, headers=await login(seeded))
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["latency_ms"], float)
    first = body["results"][0]
    assert {"chunk_id", "unit_id", "collection_id", "status", "score"} <= set(first)
    assert isinstance(first["collection_id"], int)
    assert {x["unit_id"] for x in body["results"]} >= {"labor/a44", "secret/a2"}  # admin sees all


@pytest.mark.asyncio
@pytest.mark.parametrize("collections", [None, [2], [1, 2]])
async def test_reviewer_is_scoped_to_own_collections(seeded, collections) -> None:
    headers = await login(seeded, "rev1", "pass-1234")
    r = await seeded.post("/api/retrieval/search", json=BODY | {"collections": collections}, headers=headers)
    assert r.status_code == 200
    assert all(x["collection_id"] == 1 for x in r.json()["results"])


@pytest.mark.asyncio
async def test_plain_user_cannot_use_retrieval_api(seeded) -> None:
    headers = await login(seeded, "user1", "pass-1234")
    assert (await seeded.post("/api/retrieval/search", json=BODY, headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_tei_outage_is_a_clean_arabic_503(seeded, monkeypatch) -> None:
    from app.retrieval import embedder

    async def down(texts):
        raise embedder.EmbedderError("TEI unreachable")

    monkeypatch.setattr(embedder, "aembed_texts", down)
    r = await seeded.post("/api/retrieval/search", json=BODY, headers=await login(seeded))
    assert r.status_code == 503 and "خدمة" in r.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_mode_is_422(seeded) -> None:
    r = await seeded.post("/api/retrieval/search", json=BODY | {"mode": "magic"}, headers=await login(seeded))
    assert r.status_code == 422
