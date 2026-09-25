"""Arabic normalization. One module used by ingestion, BM25, and embeddings."""

import re
import unicodedata

NORMALIZER_VERSION = "v1"

# Tashkeel (harakat)
_TASHKEEL = "ًٌٍَُِّْٰٕٓٔ"
# Tatweel
_TATWEEL = "ـ"
# Zero-width and bidi format characters
_ZERO_WIDTH = "​‌‍‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"

_STRIP_CHARS = str.maketrans("", "", _TASHKEEL + _TATWEEL + _ZERO_WIDTH)

# Eastern Arabic digits → Western
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Letter unification (search only)
_LETTER_UNIFY = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
    }
)

_WHITESPACE_RE = re.compile(r"\s+")


def _pre(text: str) -> str:
    """Steps common to both normalizers: NFC, strip tashkeel/tatweel/zw, digits."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = t.translate(_STRIP_CHARS)
    t = t.translate(_DIGITS)
    return t


def normalize_for_search(text: str) -> str:
    """Heavy normalization: used for BM25 index AND BM25 query.

    Ensures ``المادة ٤١`` matches ``المادة 41``.
    """
    t = _pre(text)
    t = t.translate(_LETTER_UNIFY)
    t = _WHITESPACE_RE.sub(" ", t).strip()
    return t


def normalize_for_embedding(text: str) -> str:
    """Light normalization: keeps letter forms for the embedder's morphology signal."""
    t = _pre(text)
    t = _WHITESPACE_RE.sub(" ", t).strip()
    return t
