"""Approval workflow (P4 slice): versions, approve, reject, PDF access rules."""

import pytest

from tests.integration.conftest import login
from tests.integration.test_reviews import OPINION, submit, world  # noqa: F401  (fixture)


async def reviewed(world, verdict: str = "contradicted") -> tuple[str, dict, dict]:
    from workers.tasks import run_review

    world.claude.verdict = verdict
    admin = await login(world)
    await world.post("/api/v1/admin/users", headers=admin, json={
        "username": "rev", "password": "rev-pass-123", "role": "reviewer", "collection_ids": [1]})
    user = await login(world, "lawyer", "lawyer-pass")
    rid = await submit(world, user, opinion_text=OPINION)
    await run_review({}, rid)
    return rid, user, await login(world, "rev", "rev-pass-123")


@pytest.mark.asyncio
async def test_edit_then_approve_records_versions_and_approval(world) -> None:
    rid, user, rev = await reviewed(world)
    assert (await world.get(f"/api/v1/reviews/{rid}", headers=user)).json()["status"] == "needs_review"
    r = await world.post(f"/api/v1/reviews/{rid}/versions", headers=rev, json={"text": "الرأي المعدل: فترة التجربة لا تتجاوز ثلاثة أشهر [P1]."})
    assert r.status_code == 201 and r.json()["version"] == 3  # 1 = ai_report, 2 = ai_suggested_opinion
    r = await world.post(f"/api/v1/reviews/{rid}/approve", headers=rev, json={})
    assert r.status_code == 200
    body = (await world.get(f"/api/v1/reviews/{rid}", headers=user)).json()
    assert body["status"] == "approved"
    assert body["approvals"] == [{"version": 3, "decision": "approve"}]
    assert body["final_text"].startswith("الرأي المعدل")
    kinds = [v["kind"] for v in (await world.get(f"/api/v1/reviews/{rid}/versions", headers=user)).json()]
    assert kinds == ["ai_report", "ai_suggested_opinion", "human_edit"]


@pytest.mark.asyncio
async def test_only_staff_can_act_and_rejected_is_final(world) -> None:
    rid, user, rev = await reviewed(world)
    assert (await world.post(f"/api/v1/reviews/{rid}/approve", headers=user, json={})).status_code == 403
    assert (await world.post(f"/api/v1/reviews/{rid}/versions", headers=user, json={"text": "x" * 30})).status_code == 403
    r = await world.post(f"/api/v1/reviews/{rid}/reject", headers=rev, json={"reason": "الرأي يخالف المادة الثالثة"})
    assert r.status_code == 200
    assert (await world.get(f"/api/v1/reviews/{rid}", headers=user)).json()["status"] == "rejected"
    assert (await world.post(f"/api/v1/reviews/{rid}/approve", headers=rev, json={})).status_code == 409
    assert (await world.get(f"/api/v1/reviews/{rid}/export.pdf", headers=user)).status_code == 409


@pytest.mark.asyncio
async def test_pdf_only_when_accepted_or_approved_and_only_for_owner_or_staff(world, monkeypatch) -> None:
    from app.verification import export

    monkeypatch.setattr(export, "html_to_pdf", lambda html: b"%PDF-1.7 fake " + html.encode()[:20])
    rid, user, rev = await reviewed(world)
    assert (await world.get(f"/api/v1/reviews/{rid}/export.pdf", headers=user)).status_code == 409
    await world.post(f"/api/v1/reviews/{rid}/approve", headers=rev, json={})
    r = await world.get(f"/api/v1/reviews/{rid}/export.pdf", headers=user)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    admin = await login(world)
    await world.post("/api/v1/admin/users", headers=admin, json={
        "username": "stranger", "password": "pass-1234", "role": "user", "collection_ids": [1]})
    other = await login(world, "stranger", "pass-1234")
    assert (await world.get(f"/api/v1/reviews/{rid}/export.pdf", headers=other)).status_code == 404
