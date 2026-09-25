"""Deterministic evidence validation (brief §7.3). No LLM.

Quotes are matched on normalize_for_search(); the stored quote is the exact matching
span of the source text, recovered through character offsets.
"""

import unicodedata
from datetime import date
from typing import Any

from rapidfuzz import fuzz

from app.text.arabic import IGNORABLE_CHARS, normalize_for_search, normalize_for_search_with_offsets
from app.verification.types import ClaimIn, ClaimResult, Evidence, Passage

MIN_FUZZY = 90.0
MAX_QUOTE_WORDS = 40
NOT_IN_FORCE_NOTE = "المصدر ملغى أو غير سارٍ في التاريخ المرجعي؛ يُعرض للسياق فقط."


def in_force(p: Passage, as_of: date) -> bool:
    if p.status == "repealed":
        return False
    if p.valid_from and p.valid_from > as_of:
        return False
    return not (p.valid_to and p.valid_to <= as_of)


MIN_QUOTE_WORDS = 4
MIN_COVERAGE = 0.9
# Normalized negators; the quote and its source span must carry exactly the same ones.
NEGATORS = frozenset({"لا", "لم", "لن", "ليس", "ليست", "غير", "عدم", "الا", "دون", "بدون"})


def _negators(words: list[str]) -> list[str]:
    return [w for w in words if w in NEGATORS]


def _source_span(quote: str, source: str) -> str | None:
    """Exact, meaning-preserving span of `source` for `quote` (tashkeel/digit/alef-insensitive).

    Rejects: quotes under MIN_QUOTE_WORDS, quotes longer than the source, fuzzy matches
    covering < MIN_COVERAGE of the quote, and any negation mismatch — including a
    negator in the source right before the matched span (dropped negation).
    """
    src = unicodedata.normalize("NFC", source)
    hay, offsets = normalize_for_search_with_offsets(src)
    needle = normalize_for_search(quote)
    if len(needle.split()) < MIN_QUOTE_WORDS or len(needle) > len(hay):
        return None
    i = hay.find(needle)
    if i >= 0:
        start, end = i, i + len(needle)
    else:
        al = fuzz.partial_ratio_alignment(needle, hay)
        if al is None or al.score < MIN_FUZZY:
            return None
        if (al.src_end - al.src_start) < MIN_COVERAGE * len(needle):
            return None
        start, end = al.dest_start, al.dest_end
    # snap to whole words
    while start > 0 and hay[start - 1] != " ":
        start -= 1
    while end < len(hay) and hay[end] != " ":
        end += 1
    span_words = hay[start:end].split()
    before = hay[:start].split()[-1:]
    if _negators(needle.split()) != _negators(span_words) or _negators(before):
        return None
    a, b = offsets[start], offsets[end - 1] + 1
    while b < len(src) and src[b] in IGNORABLE_CHARS:  # keep trailing tashkeel/tatweel
        b += 1
    return src[a:b]


def validate(
    claim: ClaimIn, raw: dict[str, Any], passages: dict[str, Passage], as_of: date
) -> ClaimResult:
    evidence: list[Evidence] = []
    dropped: list[dict[str, Any]] = []
    for item in raw.get("evidence", []):
        pid, stance, quote = (
            item.get("passage_id", ""),
            item.get("stance"),
            item.get("quote_ar", ""),
        )
        p = passages.get(pid)
        if p is None:
            dropped.append(
                {"claim_id": claim.id, "passage_id": pid, "reason": "hallucinated_passage"}
            )
            continue
        span = _source_span(quote, p.text) or (p.parent_text and _source_span(quote, p.parent_text))
        if not span:
            dropped.append(
                {
                    "claim_id": claim.id,
                    "passage_id": pid,
                    "reason": "unverified_quote",
                    "quote": quote[:200],
                }
            )
            continue
        span = " ".join(span.split()[:MAX_QUOTE_WORDS])
        note = None
        if stance == "supports" and not in_force(p, as_of):
            stance, note = "context", NOT_IN_FORCE_NOTE
        evidence.append(
            Evidence(pid=pid, chunk_id=p.chunk_id, stance=stance, quote_ar=span, note=note)
        )

    verdict = raw.get("verdict", "insufficient")
    stances = {e.stance for e in evidence}
    if (verdict in ("supported", "partially_supported") and "supports" not in stances) or (
        verdict == "contradicted" and "contradicts" not in stances
    ):
        verdict = "insufficient"
    return ClaimResult(
        claim=claim,
        verdict=verdict,
        reasoning_ar=raw.get("reasoning_ar", ""),
        evidence=evidence,
        dropped=dropped,
    )
