"""Deterministic score, blocking contradictions, and status (brief §7.4). No LLM."""

from dataclasses import dataclass
from datetime import date

from app.verification.types import ClaimResult, Passage
from app.verification.validate import in_force

ACCEPT_THRESHOLD = 90
WEIGHTS = {"core": 2, "supporting": 1}
VALUES = {"supported": 1.0, "partially_supported": 0.5, "contradicted": 0.0, "insufficient": 0.0}
NO_INFO_MESSAGE = "لا تتوفر معلومات في المصادر المتاحة للتحقق من هذا الرأي."
RESOLVED_CONFLICT_BADGE = "تعارض محسوم لصالح المصدر الأعلى"


@dataclass
class ScoreOut:
    score: int | None
    status: str  # accepted | needs_review | no_information
    blocking_count: int


def _mark_conflicts(r: ClaimResult, passages: dict[str, Passage], as_of: date) -> int:
    supports = [passages[e.pid] for e in r.evidence if e.stance == "supports" and e.pid in passages]
    top = max((p.authority for p in supports), default=0.0)
    blocking = 0
    for e in r.evidence:
        if e.stance != "contradicts" or e.pid not in passages:
            continue
        src = passages[e.pid]
        # ≥ the strongest supporting authority (equal level included) and in force → blocking.
        # ponytail: lex specialis (special vs general law at one level) is not detected yet.
        if in_force(src, as_of) and src.authority >= top:
            e.blocking = True
            blocking += 1
        else:
            e.resolved_conflict = True
            e.note = RESOLVED_CONFLICT_BADGE
    return blocking


def score_review(results: list[ClaimResult], passages: dict[str, Passage], as_of: date) -> ScoreOut:
    scored = [r for r in results if r.claim.type != "factual_premise"]
    blocking = sum(_mark_conflicts(r, passages, as_of) for r in scored)
    no_evidence = all(not r.evidence for r in scored)
    if not scored or (all(r.verdict == "insufficient" for r in scored) and no_evidence):
        return ScoreOut(score=None, status="no_information", blocking_count=0)
    total = sum(WEIGHTS[r.claim.materiality] for r in scored)
    got = sum(WEIGHTS[r.claim.materiality] * VALUES[r.verdict or "insufficient"] for r in scored)
    score = round(100 * got / total)
    status = "accepted" if score >= ACCEPT_THRESHOLD and blocking == 0 else "needs_review"
    return ScoreOut(score=score, status=status, blocking_count=blocking)
