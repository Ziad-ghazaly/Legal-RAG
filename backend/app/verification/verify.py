"""Claim verification calls (brief §7.2): ≤ 6 claims and ≤ 40k evidence tokens per call,
batches run concurrently with a bound."""

import asyncio
from typing import Any

from app.verification import prompts
from app.verification.extract import LLM
from app.verification.types import ClaimIn, Passage

CLAIMS_PER_CALL = 6
MAX_CALL_TOKENS = 40_000
CONCURRENCY = 3
_STATUS_AR = {"in_force": "ساري", "amended": "معدّل", "repealed": "ملغى", "suspended": "موقوف العمل"}


def _tokens(p: Passage) -> int:
    return max(1, len(p.text.split()) * 2) + (
        len(p.parent_text.split()) * 2 if p.parent_text else 0
    )


def _batches(claims: list[ClaimIn], per_claim: dict[str, list[Passage]]) -> list[list[ClaimIn]]:
    batches: list[list[ClaimIn]] = []
    cur: list[ClaimIn] = []
    seen: set[str] = set()
    tokens = 0
    for c in claims:
        new = [p for p in per_claim.get(c.id, []) if p.pid not in seen]
        add = sum(_tokens(p) for p in new)
        if cur and (len(cur) >= CLAIMS_PER_CALL or tokens + add > MAX_CALL_TOKENS):
            batches.append(cur)
            cur, seen, tokens = [], set(), 0
            new = per_claim.get(c.id, [])
            add = sum(_tokens(p) for p in new)
        cur.append(c)
        seen |= {p.pid for p in new}
        tokens += add
    return [*batches, cur] if cur else batches


def _user_message(batch: list[ClaimIn], per_claim: dict[str, list[Passage]]) -> str:
    passages: dict[str, Passage] = {}
    for c in batch:
        for p in per_claim.get(c.id, []):
            passages.setdefault(p.pid, p)
    parts = ["المقاطع:"]
    for p in passages.values():
        parts.append(
            f"[{p.pid}] {p.context_header} (الحالة: {_STATUS_AR.get(p.status, p.status)})\n{p.text}"
        )
        if p.parent_text:
            parts.append(f"(نص المادة كاملاً للسياق)\n{p.parent_text}")
    parts.append("\nالادعاءات:")
    for c in batch:
        pids = ", ".join(p.pid for p in per_claim.get(c.id, [])) or "لا توجد مقاطع"
        parts.append(f"{c.id}: {c.text_ar} (المقاطع: {pids})")
    return "\n\n".join(parts)


async def verify_claims(
    llm: LLM, claims: list[ClaimIn], per_claim: dict[str, list[Passage]]
) -> dict[str, dict[str, Any]]:
    sem = asyncio.Semaphore(CONCURRENCY)

    async def run(batch: list[ClaimIn]) -> list[dict[str, Any]]:
        async with sem:
            out = await llm.call_structured(
                prompts.VERIFY_SYSTEM,
                _user_message(batch, per_claim),
                "record_verdicts",
                prompts.VERIFY_SCHEMA,
                prompt_version=prompts.VERIFY_VERSION,
                max_tokens=8192,
            )
        return out.get("results", [])

    results = await asyncio.gather(*(run(b) for b in _batches(claims, per_claim)))
    by_id = {r.get("claim_id"): r for batch in results for r in batch}
    insufficient = {"verdict": "insufficient", "evidence": [], "reasoning_ar": ""}
    return {c.id: by_id.get(c.id) or {"claim_id": c.id, **insufficient} for c in claims}
