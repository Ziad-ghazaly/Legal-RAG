import pytest

from app.core.legal import AUTHORITY, DOC_TYPE_AR, LEGISLATION_TYPES, authority_for


def test_hierarchy_values_match_the_user_specified_kuwaiti_weights() -> None:
    assert authority_for("constitution") == 0.99
    assert authority_for("law") == authority_for("decree_law") == 0.70  # Const. art. 71
    assert authority_for("decree") == 0.65
    assert authority_for("regulation") == 0.60
    assert authority_for("ministerial_decision") == 0.50
    assert authority_for("circular") == 0.30
    assert authority_for("legal_opinion") == authority_for("fatwa") == 0.15
    assert authority_for("commentary") == 0.05


def test_court_ruling_depends_on_court_level() -> None:
    assert authority_for("court_ruling", "cassation") == 0.12
    assert authority_for("court_ruling") == 0.10


def test_order_is_strictly_hierarchical() -> None:
    order = ["constitution", "law", "decree", "regulation", "ministerial_decision", "circular",
             "legal_opinion", "court_ruling", "commentary"]
    values = [authority_for(t) for t in order]
    assert values == sorted(values, reverse=True)


def test_unknown_doc_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        authority_for("blog_post")


def test_every_doc_type_has_arabic_label() -> None:
    assert set(DOC_TYPE_AR) == set(AUTHORITY)
    assert set(LEGISLATION_TYPES) <= set(AUTHORITY)
