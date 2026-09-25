"""Report summary + suggested opinion (brief §7.5) and similar opinions (§7.6)."""

import json
import re
from collections import OrderedDict
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.legal import OPINION_TYPES
from app.retrieval.search import SearchParams, search
from app.verification import prompts
from app.verification.extract import LLM
from app.verification.scoring import NO_INFO_MESSAGE
from app.verification.types import ClaimResult, Passage

_MARKER = re.compile(r"\[(P\d+)\]")
SIMILAR_QUERY_CHARS = 4000
SIMILAR_TOP = 5


async def write_report(
    llm: LLM, results: list[ClaimResult], status: str, passages: dict[str, Passage]
) -> dict[str, str]:
    if status == "no_information":
        return {"summary_ar": NO_INFO_MESSAGE, "suggested_opinion_ar": ""}
    data = [
        {
            "claim_id": r.claim.id,
            "claim": r.claim.text_ar,
            "type": r.claim.type,
            "verdict": r.verdict,
            "reasoning": r.reasoning_ar,
            "evidence": [
                {"passage_id": e.pid, "stance": e.stance, "quote": e.quote_ar} for e in r.evidence
            ],
        }
        for r in results
    ]
    want = status == "needs_review"
    user = (
        "نتائج التحقق:\n"
        + json.dumps(data, ensure_ascii=False, indent=1)
        + (
            "\n\nالمطلوب: الملخص والرأي المقترح (suggested_opinion_ar)."
            if want
            else "\n\nالمطلوب: الملخص فقط؛ اجعل suggested_opinion_ar نصاً فارغاً."
        )
    )
    out = await llm.call_structured(
        prompts.REPORT_SYSTEM,
        user,
        "record_report",
        prompts.REPORT_SCHEMA,
        prompt_version=prompts.REPORT_VERSION,
        max_tokens=8192,
    )
    suggested = out.get("suggested_opinion_ar", "") if want else ""
    suggested = _MARKER.sub(lambda m: m[0] if m[1] in passages else "", suggested)
    return {"summary_ar": out.get("summary_ar", ""), "suggested_opinion_ar": suggested}


async def similar_opinions(
    session: AsyncSession, text: str, allowed: list[int] | None, as_of: date | None
) -> list[dict]:
    res = await search(
        session,
        SearchParams(
            query=text[:SIMILAR_QUERY_CHARS],
            mode="hybrid",
            top_k=50,
            as_of_date=as_of,
            doc_types=list(OPINION_TYPES),
        ),
        allowed,
    )
    docs: OrderedDict[str, dict] = OrderedDict()
    for h in res.hits:
        if h.document_id not in docs:
            docs[h.document_id] = {
                "document_id": h.document_id,
                "title_ar": h.title_ar,
                "doc_type": h.doc_type,
                "score": round(h.score, 4),
                "excerpt": " ".join(h.text.split()[:40]),
            }
    return list(docs.values())[:SIMILAR_TOP]
