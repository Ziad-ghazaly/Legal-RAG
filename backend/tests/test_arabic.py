"""Arabic text normalization — Rule 1's foundation."""

import pytest

from app.text.arabic import (
    NORMALIZER_VERSION,
    normalize_for_embedding,
    normalize_for_search,
)


def test_version_is_v1():
    assert NORMALIZER_VERSION == "v1"


# --- search normalization: heavy (unifies letter forms) ------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("الْمَادَّةُ", "الماده"),
        ("الــمــادة", "الماده"),
        ("المادة ٤١", "الماده 41"),
        ("أحمد إسلام آية ٱلقانون", "احمد اسلام ايه القانون"),
        ("مصطفى", "مصطفي"),
        ("قضية", "قضيه"),
        ("مسؤول رئيس", "مسوول رييس"),
        ("ال‏مادة", "الماده"),
        ("المادة   41", "الماده 41"),
        ("المــادةُ ٤١ في القـانون الأصلي", "الماده 41 في القانون الاصلي"),
    ],
)
def test_normalize_for_search(raw, expected):
    assert normalize_for_search(raw) == expected


def test_search_invariant_digit_form():
    """المادة ٤١ must equal المادة 41 after search normalization."""
    assert normalize_for_search("المادة ٤١") == normalize_for_search("المادة 41")


# --- embedding normalization: light (keeps letter forms) -----------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("الْمَادَّةُ", "المادة"),
        ("الــمــادة", "المادة"),
        ("المادة ٤١", "المادة 41"),
        ("أحمد إسلام آية", "أحمد إسلام آية"),
        ("مصطفى", "مصطفى"),
        ("قضية", "قضية"),
    ],
)
def test_normalize_for_embedding(raw, expected):
    assert normalize_for_embedding(raw) == expected


def test_empty_and_whitespace():
    assert normalize_for_search("") == ""
    assert normalize_for_embedding("") == ""
    assert normalize_for_search("   \n\t  ") == ""
