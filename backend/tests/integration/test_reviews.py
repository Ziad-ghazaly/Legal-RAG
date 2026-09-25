"""P2 end to end on ParadeDB: POST /reviews → worker pipeline (fake Claude/TEI) → GET report."""

import re

import pytest

from app.ingestion.indexer import index_documents
from tests.integration.conftest import fake_count, fake_embed, login
from tests.integration.test_search import ANNUAL, NOTICE, SHIPS, art, fake_rerank, law

OPINION = (
    "يستحق العامل وفقاً للمادة 41 من القانون رقم 6 لسنة 2010 إجازة سنوية مدفوعة الأجر مدتها ثلاثون يوماً. "
    "ولا يجوز لصاحب العمل إنهاء عقد العمل غير محدد المدة إلا بعد إخطار العامل قبل ثلاثة أشهر."
)


class ScriptedClaude:
    """Extracts two claims; verifies each with a verbatim quote from its first passage."""

    def __init__(self, verdict: str = "supported") -> None:
        self.verdict = verdict
        self.usage: list = []
        self.calls: list[str] = []

    async def call_structured(self, system, user, tool_name, schema, *, prompt_version, max_tokens=8192):
        self.calls.append(tool_name)
        if tool_name == "record_claims":
            return {"claims": [
                {"text_ar": "للعامل إجازة سنوية مدفوعة الأجر ثلاثون يوماً", "type": "legal_conclusion",
                 "materiality": "core", "cited_refs": [{"law_number": "6", "year": 2010, "article": 41, "raw": "م41"}]},
                {"text_ar": "لا يجوز إنهاء العقد إلا بعد إخطار العامل قبل ثلاثة أشهر", "type": "legal_premise",
                 "materiality": "supporting", "cited_refs": []},
                {"text_ar": "عُيّن الموكل في عام 2015", "type": "factual_premise", "materiality": "supporting",
                 "cited_refs": []},
            ]}
        if tool_name == "record_verdicts":
            passages = dict(re.findall(r"\[(P\d+)\] [^\n]*\n([^\n]+)", user))
            out = []
            for cid, pids in re.findall(r"^(C\d+): .*\(المقاطع: ([^)]*)\)", user, flags=re.M):
                pid = pids.split(",")[0].strip()
                quote = " ".join(passages[pid].split()[:6])
                out.append({"claim_id": cid, "verdict": self.verdict, "reasoning_ar": "تعليل",
                            "evidence": [{"passage_id": pid, "stance": "supports" if self.verdict != "contradicted"
                                          else "contradicts", "quote_ar": quote},
                                         {"passage_id": "P99", "stance": "supports", "quote_ar": "مختلق"}]})
            return {"results": out}
        return {"summary_ar": "ملخص التحقق", "suggested_opinion_ar": "رأي مقترح [P1]"}


@pytest.fixture
async def world(api, pg, monkeypatch):
    from app.retrieval import embedder, rerank
    from workers import tasks

    monkeypatch.setattr(embedder, "aembed_texts", fake_embed)
    monkeypatch.setattr(rerank, "rerank", fake_rerank)
    await index_documents(pg, [law("labor", "6", [art("labor/a41", 41, ANNUAL), art("labor/a44", 44, NOTICE)]),
                               law("ships", "9", [art("ships/a1", 1, SHIPS)])],
                          collection_id=1, count_tokens=fake_count, embed=fake_embed)
    opinion = {"doc_id": "op-1", "doc_type": "legal_opinion", "title_ar": "رأي سابق في الإجازات",
               "units": [{"unit_id": "op-1/s1", "level": "section", "article_label": "الرأي",
                          "text": "انتهت إدارة الفتوى إلى أن العامل يستحق إجازة سنوية مدفوعة الأجر ثلاثين يوماً."}]}
    from app.ingestion.contract import DocumentIn

    await index_documents(pg, [DocumentIn.model_validate(opinion)], collection_id=1,
                          count_tokens=fake_count, embed=fake_embed)
    claude = ScriptedClaude()
    monkeypatch.setattr(tasks, "make_llm", lambda: claude)
    admin = await login(api)
    r = await api.post("/api/v1/admin/users", headers=admin, json={
        "username": "lawyer", "password": "lawyer-pass", "role": "user", "collection_ids": [1]})
    assert r.status_code == 201
    api.claude = claude  # type: ignore[attr-defined]
    return api


async def submit(api, headers, **form) -> str:
    r = await api.post("/api/v1/reviews", headers=headers, data=form)
    assert r.status_code == 202, r.text
    return r.json()["review_id"]


@pytest.mark.asyncio
async def test_review_end_to_end_accepted(world) -> None:
    from workers.tasks import run_review

    user = await login(world, "lawyer", "lawyer-pass")
    rid = await submit(world, user, opinion_text=OPINION, question="ما حقوق العامل؟")
    assert world.jobs[-1] == ("run_review", rid)
    assert (await world.get(f"/api/v1/reviews/{rid}", headers=user)).json()["status"] == "processing"

    await run_review({}, rid)

    body = (await world.get(f"/api/v1/reviews/{rid}", headers=user)).json()
    assert body["status"] == "accepted" and body["score"] == 100
    report = body["report"]
    assert report["summary_ar"] == "ملخص التحقق" and report["suggested_opinion_ar"] == ""
    claims = {c["id"]: c for c in report["claims"]}
    assert claims["C1"]["verdict"] == "supported" and claims["C3"]["verdict"] is None  # factual premise
    ev = claims["C1"]["evidence"]
    assert len(ev) == 1 and ev[0]["quote_ar"] in report["passages"][ev[0]["pid"]]["text"]  # P99 dropped
    assert report["dropped_evidence_count"] >= 2
    first_pid = claims["C1"]["evidence"][0]["pid"]
    assert report["passages"][first_pid]["unit_id"] == "labor/a41"  # pinned exact citation
    assert report["references"]["supporting"] and report["references"]["contradicting"] == []
    assert report["similar_opinions"][0]["document_id"] == "op-1"
    assert body["approvals"] == [{"version": 1, "decision": "system_accept"}]

    listed = (await world.get("/api/v1/reviews", headers=user)).json()
    assert [x["id"] for x in listed["items"]] == [rid]


@pytest.mark.asyncio
async def test_contradicted_opinion_needs_review_with_suggestion(world) -> None:
    from workers.tasks import run_review

    world.claude.verdict = "contradicted"
    user = await login(world, "lawyer", "lawyer-pass")
    rid = await submit(world, user, opinion_text=OPINION)
    await run_review({}, rid)
    body = (await world.get(f"/api/v1/reviews/{rid}", headers=user)).json()
    assert body["status"] == "needs_review" and body["score"] == 0
    assert body["report"]["suggested_opinion_ar"] == "رأي مقترح [P1]"
    assert body["report"]["references"]["contradicting"]
    assert body["approvals"] == []


@pytest.mark.asyncio
async def test_other_users_cannot_read_a_review_but_reviewers_can(world) -> None:
    admin = await login(world)
    for name, role in (("other", "user"), ("rev", "reviewer")):
        await world.post("/api/v1/admin/users", headers=admin, json={
            "username": name, "password": "pass-1234", "role": role, "collection_ids": [1]})
    rid = await submit(world, await login(world, "lawyer", "lawyer-pass"), opinion_text=OPINION)
    other = await login(world, "other", "pass-1234")
    assert (await world.get(f"/api/v1/reviews/{rid}", headers=other)).status_code == 404
    assert (await world.get("/api/v1/reviews", headers=other)).json()["items"] == []
    rev = await login(world, "rev", "pass-1234")
    assert (await world.get(f"/api/v1/reviews/{rid}", headers=rev)).status_code == 200


@pytest.mark.asyncio
async def test_submission_validation_and_file_upload(world) -> None:
    user = await login(world, "lawyer", "lawyer-pass")
    r = await world.post("/api/v1/reviews", headers=user, data={})
    assert r.status_code == 422
    r = await world.post("/api/v1/reviews", headers=user,
                         files={"file": ("op.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415
    r = await world.post("/api/v1/reviews", headers=user,
                         files={"file": ("op.txt", OPINION.encode(), "text/plain")})
    assert r.status_code == 202
    rid = r.json()["review_id"]
    assert any(k.startswith(f"reviews/{rid}/") for k in world.blobs)


@pytest.mark.asyncio
async def test_claude_failure_marks_review_failed_with_arabic_message(world, monkeypatch) -> None:
    from app.llm.claude_client import ClaudeError
    from workers import tasks

    class Down:
        def __init__(self) -> None:
            self.usage: list = []

        async def call_structured(self, *a, **k):
            raise ClaudeError("boom")

    monkeypatch.setattr(tasks, "make_llm", Down)
    user = await login(world, "lawyer", "lawyer-pass")
    rid = await submit(world, user, opinion_text=OPINION)
    await tasks.run_review({}, rid)
    body = (await world.get(f"/api/v1/reviews/{rid}", headers=user)).json()
    assert body["status"] == "failed" and "خدمة" in body["error_ar"]


@pytest.mark.asyncio
async def test_source_chunk_endpoint_respects_acl(world, pg) -> None:
    from sqlalchemy import text

    cid = (await pg.execute(text("SELECT id::text FROM chunks WHERE unit_id='labor/a41'"))).scalar_one()
    user = await login(world, "lawyer", "lawyer-pass")
    r = await world.get(f"/api/v1/sources/chunks/{cid}", headers=user)
    assert r.status_code == 200 and r.json()["unit"]["article_number"] == 41
    admin = await login(world)
    await world.post("/api/v1/admin/users", headers=admin, json={
        "username": "outsider", "password": "pass-1234", "role": "user", "collection_ids": [2]})
    r = await world.get(f"/api/v1/sources/chunks/{cid}", headers=await login(world, "outsider", "pass-1234"))
    assert r.status_code == 404
