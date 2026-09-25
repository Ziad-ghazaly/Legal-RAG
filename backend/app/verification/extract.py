"""Claim extraction (brief §7.1): one Claude call per opinion section."""

from typing import Any, Protocol

from app.text.arabic import normalize_for_search
from app.verification import prompts
from app.verification.types import ClaimIn

MAX_CLAIMS = 40
SECTION_CHARS = 120_000  # ≈ 60k tokens of Arabic


class LLM(Protocol):
    async def call_structured(
        self,
        system: str,
        user: str,
        tool_name: str,
        schema: dict[str, Any],
        *,
        prompt_version: str,
        max_tokens: int = ...,
    ) -> dict[str, Any]: ...


def _sections(text: str) -> list[str]:
    out, cur = [], ""
    for para in text.split("\n"):
        if cur and len(cur) + len(para) > SECTION_CHARS:
            out.append(cur)
            cur = ""
        cur += para + "\n"
    return [*out, cur] if cur.strip() else out


async def extract_claims(
    llm: LLM, opinion: str, question: str | None
) -> tuple[list[ClaimIn], bool]:
    raw: list[dict[str, Any]] = []
    for section in _sections(opinion):
        user = (
            f"السؤال أو الوقائع:\n{question}\n\n" if question else ""
        ) + f"الرأي القانوني:\n{section}"
        out = await llm.call_structured(
            prompts.EXTRACT_SYSTEM,
            user,
            "record_claims",
            prompts.EXTRACT_SCHEMA,
            prompt_version=prompts.EXTRACT_VERSION,
            max_tokens=8192,
        )
        raw.extend(out.get("claims", []))

    seen: set[str] = set()
    claims: list[ClaimIn] = []
    for c in raw:
        key = normalize_for_search(c.get("text_ar", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        claims.append(
            ClaimIn(
                id=f"C{len(claims) + 1}",
                text_ar=c["text_ar"].strip(),
                type=c.get("type", "legal_premise"),
                materiality=c.get("materiality", "supporting"),
                cited_refs=c.get("cited_refs") or [],
            )
        )
    return claims[:MAX_CLAIMS], len(claims) > MAX_CLAIMS
