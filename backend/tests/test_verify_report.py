import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

import pytest

from app.verification.report import write_report
from app.verification.scoring import NO_INFO_MESSAGE
from app.verification.types import ClaimIn, ClaimResult, Evidence
from app.verification.verify import verify_claims
from tests.test_verification_units import FakeLLM, passage


def claim(i: int) -> ClaimIn:
    return ClaimIn(id=f"C{i}", text_ar=f"ادعاء {i}", type="legal_conclusion", materiality="core", cited_refs=[])


@pytest.mark.asyncio
async def test_claims_are_batched_by_six_and_missing_results_default_to_insufficient() -> None:
    claims = [claim(i) for i in range(1, 14)]
    per_claim = {c.id: [passage("P1"), passage("P2", status="repealed")] for c in claims}
    outputs = [{"results": [{"claim_id": c.id, "verdict": "supported", "evidence": [], "reasoning_ar": "x"}
                            for c in claims[i:i + 6] if c.id != "C2"]} for i in (0, 6, 12)]
    llm = FakeLLM(*outputs)
    raw = await verify_claims(llm, claims, per_claim)
    assert len(llm.calls) == 3
    first = llm.calls[0]["user"]
    assert "[P1]" in first and "[P2]" in first and "ملغى" in first
    assert "C1:" in first and "C6:" in first and "C7:" not in first
    assert raw["C2"]["verdict"] == "insufficient" and raw["C1"]["verdict"] == "supported"
    assert set(raw) == {c.id for c in claims}


def _res(verdict: str, *ev: Evidence) -> ClaimResult:
    return ClaimResult(claim=claim(1), verdict=verdict, reasoning_ar="r", evidence=list(ev))


@pytest.mark.asyncio
async def test_no_information_makes_no_llm_call() -> None:
    llm = FakeLLM()
    out = await write_report(llm, [_res("insufficient")], "no_information", {})
    assert out == {"summary_ar": NO_INFO_MESSAGE, "suggested_opinion_ar": ""} and llm.calls == []


@pytest.mark.asyncio
async def test_suggested_opinion_only_for_needs_review_and_unknown_markers_are_stripped() -> None:
    p = {"P1": passage("P1")}
    ev = Evidence(pid="P1", chunk_id="ch-P1", stance="contradicts", quote_ar="إجازة سنوية")
    llm = FakeLLM({"summary_ar": "ملخص", "suggested_opinion_ar": "الرأي المصحح [P1] وأيضاً [P7]."})
    out = await write_report(llm, [_res("contradicted", ev)], "needs_review", p)
    assert out["suggested_opinion_ar"] == "الرأي المصحح [P1] وأيضاً ."
    assert "اقترح" in llm.calls[0]["user"] or "الرأي المقترح" in llm.calls[0]["user"]

    llm = FakeLLM({"summary_ar": "ملخص", "suggested_opinion_ar": "لا ينبغي"})
    out = await write_report(llm, [_res("supported")], "accepted", p)
    assert out == {"summary_ar": "ملخص", "suggested_opinion_ar": ""}


@pytest.mark.asyncio
async def test_verifier_sees_legislative_notes_of_each_passage() -> None:
    p = passage("P1", notes=["تم وقف العمل بالمادة عملا بالامر الاميري المؤرخ 10 / 5 / 2024"], status="suspended")
    llm = FakeLLM({"results": []})
    await verify_claims(llm, [claim(1)], {"C1": [p]})
    user = llm.calls[0]["user"]
    assert "موقوف العمل" in user and "تم وقف العمل بالمادة" in user
