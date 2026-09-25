import pytest

from app.core.legal import AUTHORITY, DOC_TYPE_AR, LEGISLATION_TYPES, authority_for


def test_hierarchy_values_match_brief() -> None:
    assert authority_for("constitution") == 1.0
    assert authority_for("law") == authority_for("decree_law") == 0.9
    assert authority_for("circular") == 0.5
    assert authority_for("commentary") == 0.4


def test_court_ruling_depends_on_court_level() -> None:
    assert authority_for("court_ruling", "cassation") == 0.75
    assert authority_for("court_ruling") == 0.60


def test_unknown_doc_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        authority_for("blog_post")


def test_every_doc_type_has_arabic_label() -> None:
    assert set(DOC_TYPE_AR) == set(AUTHORITY)
    assert set(LEGISLATION_TYPES) <= set(AUTHORITY)
