import json

import pytest

from tests.integration.conftest import fake_count, fake_embed, login

LAW = {
    "doc_id": "kw-law-6-2010",
    "doc_type": "law",
    "title_ar": "قانون رقم 6 لسنة 2010 في شأن العمل في القطاع الأهلي",
    "number": "6",
    "year": 2010,
    "effective_date": "2010-02-21",
    "units": [
        {"unit_id": "kw-law-6-2010/a41", "level": "article", "article_number": 41, "article_label": "المادة 41",
         "text": "يستحق العامل إجازة سنوية مدفوعة الأجر مدتها ثلاثون يوماً ولا يجوز للعامل التنازل عنها."},
        {"unit_id": "kw-law-6-2010/a44", "level": "article", "article_number": 44, "article_label": "المادة 44",
         "text": "لا يجوز لصاحب العمل إنهاء عقد العمل غير محدد المدة إلا بعد إخطار العامل قبل ثلاثة أشهر."},
    ],
}


@pytest.mark.asyncio
async def test_admin_manages_collections_and_users(api) -> None:
    admin = await login(api)
    r = await api.post("/api/v1/admin/collections", json={"name": "opinions"}, headers=admin)
    assert r.status_code == 201 and isinstance(r.json()["id"], int)
    names = [c["name"] for c in (await api.get("/api/v1/admin/collections", headers=admin)).json()]
    assert names == ["legislation", "restricted", "opinions"]

    r = await api.post("/api/v1/admin/users", headers=admin, json={
        "username": "rev1", "password": "rev-pass-123", "role": "reviewer", "collection_ids": [2]})
    assert r.status_code == 201 and r.json()["collection_ids"] == [2]
    reviewer = await login(api, "rev1", "rev-pass-123")
    assert (await api.post("/api/v1/admin/collections", json={"name": "x"}, headers=reviewer)).status_code == 403

    uid = r.json()["id"]
    r = await api.put(f"/api/v1/admin/users/{uid}/collections", json={"collection_ids": [1, 2]}, headers=admin)
    assert r.json()["collection_ids"] == [1, 2]


@pytest.mark.asyncio
async def test_ingestion_job_upload_then_worker_indexes_it(api, monkeypatch) -> None:
    from app.retrieval import embedder
    from workers.tasks import run_ingestion_job

    monkeypatch.setattr(embedder, "aembed_texts", fake_embed)
    monkeypatch.setattr(embedder, "count_tokens", fake_count)
    admin = await login(api)
    body = (json.dumps(LAW, ensure_ascii=False) + "\n{broken\n").encode()
    r = await api.post("/api/v1/admin/ingestion/jobs", headers=admin, data={"collection_id": "1"},
                       files={"file": ("corpus.jsonl", body, "application/jsonl")})
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert api.jobs == [("run_ingestion_job", job_id)]
    assert (await api.get(f"/api/v1/admin/ingestion/jobs/{job_id}", headers=admin)).json()["status"] == "pending"

    await run_ingestion_job({}, job_id)

    job = (await api.get(f"/api/v1/admin/ingestion/jobs/{job_id}", headers=admin)).json()
    assert job["status"] == "completed"
    assert (job["doc_count"], job["error_count"]) == (1, 1)
    assert job["stats"]["chunks"] == 2 and job["stats"]["row_errors"][0]["line"] == 2
    listed = (await api.get("/api/v1/admin/ingestion/jobs", headers=admin)).json()
    assert [j["id"] for j in listed] == [job_id]


@pytest.mark.asyncio
async def test_ingestion_rejects_unknown_collection(api) -> None:
    admin = await login(api)
    r = await api.post("/api/v1/admin/ingestion/jobs", headers=admin, data={"collection_id": "99"},
                       files={"file": ("c.jsonl", b"{}", "application/jsonl")})
    assert r.status_code == 404
