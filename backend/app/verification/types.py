"""Verification data types shared across the pipeline stages."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ClaimIn:
    id: str
    text_ar: str
    type: str  # legal_conclusion | legal_premise | factual_premise | procedural
    materiality: str  # core | supporting
    cited_refs: list[dict[str, Any]]


@dataclass
class Passage:
    pid: str
    chunk_id: str
    unit_id: str
    document_id: str
    text: str
    context_header: str
    title_ar: str
    number: str | None
    year: int | None
    article_label: str | None
    doc_type: str
    authority: float
    status: str
    effective_date: date | None
    valid_from: date | None
    valid_to: date | None
    parent_text: str | None = None
    notes: list[str] | None = None  # legislative history of the article
    pinned: bool = False
    score: float = 0.0


@dataclass
class Evidence:
    pid: str
    chunk_id: str
    stance: str  # supports | contradicts | context
    quote_ar: str
    note: str | None = None
    blocking: bool = False
    resolved_conflict: bool = False


@dataclass
class ClaimResult:
    claim: ClaimIn
    verdict: str | None  # None for factual premises (not verified)
    reasoning_ar: str
    evidence: list[Evidence] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
