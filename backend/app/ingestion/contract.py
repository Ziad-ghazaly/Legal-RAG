"""JSONL ingestion contract (brief §5.1, docs/INGESTION_CONTRACT.md).

One document per line. Bad lines become row-level errors; the job continues.
"""

import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.legal import AUTHORITY
from app.text.arabic import normalize_for_search

UnitType = Literal["article", "clause", "section", "paragraph", "table"]
Status = Literal["in_force", "amended", "repealed"]


class UnitIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    unit_id: str = Field(min_length=1, max_length=255)
    unit_type: UnitType = Field(alias="level")
    path: list[str] = []
    article_number: int | None = None
    article_label: str | None = None
    text: str = Field(min_length=1)
    valid_from: date | None = None
    valid_to: date | None = None
    amended_by: list[str] | None = None

    @field_validator("article_number", mode="before")
    @classmethod
    def _digits(cls, v: object) -> object:
        # "٤١" → 41; the corpus mixes Eastern and Western digits.
        return int(normalize_for_search(v)) if isinstance(v, str) else v


class DocumentIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_id: str = Field(min_length=1, max_length=255)
    doc_type: str
    title_ar: str = Field(min_length=1)
    number: str | None = None
    year: int | None = None
    issuing_authority: str | None = None
    issue_date: date | None = None
    effective_date: date | None = None
    status: Status = "in_force"
    repealed_by: str | None = None
    gazette_ref: str | None = None
    legal_domain: list[str] | None = None
    court_level: str | None = None  # "cassation" raises court_ruling authority
    language: str = "ar"
    jurisdiction: str = "KW"
    source_uri: str | None = None
    units: list[UnitIn] = Field(min_length=1)

    @field_validator("number", mode="before")
    @classmethod
    def _law_number(cls, v: object) -> object:
        from app.retrieval.exact_ref import normalize_law_number

        return normalize_law_number(v) if v is not None and str(v).strip() else None

    @field_validator("doc_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in AUTHORITY:
            raise ValueError(f"unknown doc_type {v!r}; expected one of {sorted(AUTHORITY)}")
        return v


def parse_jsonl(data: bytes) -> tuple[list[DocumentIn], list[dict]]:
    docs: list[DocumentIn] = []
    errors: list[dict] = []
    for line_no, line in enumerate(data.decode("utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            docs.append(DocumentIn.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            errors.append({"line": line_no, "error": str(e)[:500]})
    return docs, errors
