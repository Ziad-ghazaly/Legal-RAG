"""Kuwaiti legal hierarchy (authority weights) and Arabic document-type labels.

Authority is a bounded tie-breaker inside relevance (see retrieval), never an override.
"""

AUTHORITY: dict[str, float] = {
    "constitution": 1.00,
    "law": 0.90,
    "decree_law": 0.90,
    "decree": 0.80,
    "regulation": 0.70,
    "ministerial_decision": 0.60,
    "circular": 0.50,
    "court_ruling": 0.60,  # non-cassation courts; cassation handled in authority_for
    "legal_opinion": 0.50,
    "fatwa": 0.50,
    "commentary": 0.40,
}
CASSATION_AUTHORITY = 0.75

DOC_TYPE_AR: dict[str, str] = {
    "constitution": "الدستور",
    "law": "قانون",
    "decree_law": "مرسوم بقانون",
    "decree": "مرسوم",
    "regulation": "لائحة",
    "ministerial_decision": "قرار وزاري",
    "circular": "تعميم",
    "court_ruling": "حكم قضائي",
    "legal_opinion": "رأي قانوني",
    "fatwa": "فتوى",
    "commentary": "شرح",
}

LEGISLATION_TYPES: tuple[str, ...] = (
    "constitution",
    "law",
    "decree_law",
    "decree",
    "regulation",
    "ministerial_decision",
    "circular",
)
OPINION_TYPES: tuple[str, ...] = ("legal_opinion", "court_ruling", "fatwa")


def authority_for(doc_type: str, court_level: str | None = None) -> float:
    if doc_type not in AUTHORITY:
        raise ValueError(f"unknown doc_type: {doc_type!r}")
    if doc_type == "court_ruling" and court_level == "cassation":
        return CASSATION_AUTHORITY
    return AUTHORITY[doc_type]
