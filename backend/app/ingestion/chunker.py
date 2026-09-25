"""Legal-aware chunker (brief §5.5). One chunk = one citation; never merges units.

- article/clause units   → one `article` chunk; long ones split at clause markers
                           (`clause_split`), then sentences, then words.
- section/paragraph units (rulings, opinions) → `semantic` chunks, sentence-packed
  with one sentence of overlap.
- table units            → `table` chunks; long tables split by rows, header repeated.

Token counts come from the embedding model's tokenizer (injected `count_tokens`),
and cover exactly what gets embedded/reranked: context header + "\\n" + text.
"""

import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.legal import DOC_TYPE_AR
from app.ingestion.contract import DocumentIn, UnitIn
from app.text.arabic import normalize_for_search

CountTokens = Callable[[list[str]], Awaitable[list[int]]]

MAX_CHUNK_TOKENS = 450
MIN_TEXT_TOKENS = 8
MIN_ARABIC_RATIO = 0.6  # mirrors production_rules rule 2

_BOILERPLATE_LINE = [
    re.compile(r"^صدر\s+ب?قصر\s+السيف"),  # signature block
    re.compile(r"^[\d٠-٩\s\-–—|/.]+$"),  # page numbers
    re.compile(r"^الكويت\s+اليوم\b.{0,60}$"),  # gazette masthead
]
_CLAUSE_MARKER = re.compile(
    r"(?:^|(?<=\s))(?=(?:أولاً|ثانياً|ثالثاً|رابعاً|خامساً|سادساً|سابعاً|ثامناً|تاسعاً|عاشراً"
    r"|البند|الفقرة|\(\d+\)|\d+\s*[-–)]|\([أ-ي]\)|[أ-ي]\s*-\s))"
)
_SENTENCE_END = re.compile(r"(?<=[.؟!؛])\s+|\n+")
_ARABIC_LETTER = re.compile(r"[ء-ي]")
_NON_LETTER = re.compile(r"[\s0-9٠-٩\W_ً-ٟـ]")


@dataclass(frozen=True)
class ChunkDraft:
    unit_id: str
    chunk_kind: str
    context_header: str
    text: str
    text_norm: str
    token_count: int
    content_hash: str


def context_header(doc: DocumentIn, unit: UnitIn) -> str:
    parts = [f"{DOC_TYPE_AR[doc.doc_type]}: {doc.title_ar}", *unit.path]
    if unit.article_label:
        parts.append(unit.article_label)
    return " — ".join(parts)


def strip_boilerplate(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    kept = [ln for ln in lines if ln and not any(p.search(ln) for p in _BOILERPLATE_LINE)]
    return "\n".join(kept).strip()


def arabic_ratio(text: str) -> float:
    letters = len(_NON_LETTER.sub("", text))
    return len(_ARABIC_LETTER.findall(text)) / letters if letters else 0.0


def _split_clauses(text: str) -> list[str]:
    starts = sorted({m.start() for m in _CLAUSE_MARKER.finditer(text)} | {0})
    parts = [text[a:b].strip() for a, b in zip(starts, [*starts[1:], len(text)], strict=True)]
    return [p for p in parts if p]


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


async def _fit(segments: list[str], budget: int, count: CountTokens) -> list[tuple[str, int]]:
    """Break any segment over budget into sentences, then word windows."""
    out: list[tuple[str, int]] = []
    for seg, n in zip(segments, await count(segments), strict=True):
        if n <= budget:
            out.append((seg, n))
            continue
        sentences = _split_sentences(seg)
        if len(sentences) > 1:
            out.extend(await _fit(sentences, budget, count))
            continue
        words = seg.split()
        # ponytail: proportional word windows; fine for run-on text, not token-exact.
        per = max(1, int(len(words) * budget / n))
        windows = [" ".join(words[i : i + per]) for i in range(0, len(words), per)]
        out.extend(zip(windows, await count(windows), strict=True))
    return out


def _pack(pieces: list[tuple[str, int]], budget: int, overlap: bool, sep: str) -> list[str]:
    chunks: list[list[tuple[str, int]]] = []
    cur: list[tuple[str, int]] = []
    for piece in pieces:
        if cur and sum(n for _, n in cur) + piece[1] > budget:
            chunks.append(cur)
            carry = cur[-1:] if overlap and cur[-1][1] + piece[1] <= budget else []
            cur = carry
        cur.append(piece)
    if cur:
        chunks.append(cur)
    return [sep.join(t for t, _ in c) for c in chunks]


async def chunk_unit(
    doc: DocumentIn,
    unit: UnitIn,
    count_tokens: CountTokens,
    max_tokens: int = MAX_CHUNK_TOKENS,
) -> tuple[list[ChunkDraft], list[dict]]:
    header = context_header(doc, unit)
    is_table = unit.unit_type == "table"
    text = unit.text.strip() if is_table else strip_boilerplate(unit.text)

    def drop(reason: str) -> tuple[list[ChunkDraft], list[dict]]:
        return [], [{"unit_id": unit.unit_id, "reason": reason, "text": unit.text[:120]}]

    if not text:
        return drop("boilerplate")
    if not is_table and arabic_ratio(text) < MIN_ARABIC_RATIO:
        return drop("low_arabic_ratio")

    header_tokens, text_tokens = await count_tokens([header, text])
    if text_tokens < MIN_TEXT_TOKENS:
        return drop("tiny")
    budget = max_tokens - header_tokens - 2  # "\n" + tokenizer specials

    if is_table:
        kind = "table"
        head, *rows = text.splitlines()
        if text_tokens <= budget or not rows:
            texts = [text]
        else:
            (head_n,) = await count_tokens([head])
            packed = _pack(await _fit(rows, budget - head_n, count_tokens), budget - head_n, False, "\n")
            texts = [f"{head}\n{p}" for p in packed]
    elif unit.unit_type in ("article", "clause"):
        if text_tokens <= budget:
            kind, texts = "article", [text]
        else:
            kind = "clause_split"
            texts = _pack(await _fit(_split_clauses(text), budget, count_tokens), budget, False, "\n")
    else:
        kind = "semantic"
        if text_tokens <= budget:
            texts = [text]
        else:
            # ponytail: sentence packing with 1-sentence overlap; the brief's embedding
            # breakpoint splitting (90th-pct cosine gap) is the upgrade if rule 2/3 demand it.
            sentences = await _fit(_split_sentences(text), budget, count_tokens)
            texts = _pack(sentences, budget, True, " ")

    totals = await count_tokens([f"{header}\n{t}" for t in texts])
    chunks = [
        ChunkDraft(
            unit_id=unit.unit_id,
            chunk_kind=kind,
            context_header=header,
            text=t,
            text_norm=normalize_for_search(f"{header}\n{t}"),
            token_count=n,
            content_hash=hashlib.sha256(normalize_for_search(t).encode()).hexdigest(),
        )
        for t, n in zip(texts, totals, strict=True)
    ]
    return chunks, []
