"""Rule 1: same embedding model + normalizer version across ingest and query."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.text.arabic import NORMALIZER_VERSION


class Rule1Violation(RuntimeError):  # noqa: N818 — canonical name used in docs + logs
    """Raised when the embedding invariant is violated at startup."""


async def _read_meta(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(text("SELECT key, value FROM system_meta"))
    return {row[0]: row[1] for row in result.all()}


async def enforce_rule_one(session: AsyncSession) -> None:
    settings = get_settings()
    meta = await _read_meta(session)

    required = {
        "embedding_model": settings.embedding_model,
        "embedding_dim": str(settings.embedding_dim),
        "normalizer_version": NORMALIZER_VERSION,
    }

    missing = [k for k in required if k not in meta]
    if missing:
        raise Rule1Violation(
            f"system_meta is missing required keys: {missing}. "
            f"جدول system_meta ينقصه المفاتيح: {missing}"
        )

    mismatches: list[str] = []
    for key, expected in required.items():
        actual = meta[key]
        if actual != expected:
            mismatches.append(f"{key}: db={actual!r} config={expected!r}")

    if mismatches:
        raise Rule1Violation(
            "Rule 1 violation — embedding invariant mismatch. Aborting startup. "
            "انتهاك القاعدة 1: عدم تطابق ثابت التضمين. تم إلغاء التشغيل. "
            + "; ".join(mismatches)
        )
