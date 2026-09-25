"""Exact legal references: `المادة N من القانون رقم X لسنة Y` → pinned units."""

import re
from dataclasses import dataclass

from app.text.arabic import normalize_for_search

# Patterns run on normalize_for_search() output: ة→ه, Western digits.
_ARTICLE = r"(?:ال)?ماده\s*\(?\s*(\d+)\s*\)?"
_LAW = (
    r"(?:\s*من)?\s*(?:ال)?(?:مرسوم\s+بقانون|قانون|مرسوم|لائحه|قرار)[^\d]{0,40}?"
    r"رقم\s*\(?\s*(\d+)\s*\)?\s*لسنه\s*(\d{4})"
)
_CITATION = re.compile(_ARTICLE + f"(?:{_LAW})?")


@dataclass(frozen=True)
class Citation:
    article: int
    number: str | None
    year: int | None


def parse_citations(text: str) -> list[Citation]:
    out: list[Citation] = []
    for m in _CITATION.finditer(normalize_for_search(text)):
        c = Citation(int(m[1]), m[2], int(m[3]) if m[3] else None)
        if c not in out:
            out.append(c)
    return out
