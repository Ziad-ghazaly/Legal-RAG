import math

from app.retrieval.exact_ref import Citation, parse_citations
from app.retrieval.search import final_score, rrf, sigmoid


def test_rrf_uses_ranks_only_and_sums_lists() -> None:
    fused = rrf([["a", "b", "c"], ["b", "d"]], k=60)
    assert fused["b"] == 1 / 62 + 1 / 61
    assert fused["a"] == 1 / 61 and fused["d"] == 1 / 62
    assert sorted(fused, key=fused.get, reverse=True)[0] == "b"


def test_sigmoid_and_bounded_authority() -> None:
    assert sigmoid(0.0) == 0.5
    p = sigmoid(-2.0)
    assert 0 < p < 0.5
    # authority breaks ties but never inverts relevance (old demo bug)
    assert final_score(0.9, 0.4) > final_score(0.5, 1.0)
    assert math.isclose(final_score(0.8, 1.0), 0.8)


def test_parse_citation_with_law_number_and_year() -> None:
    assert parse_citations("وفقاً للمادة 41 من القانون رقم 6 لسنة 2010 يستحق العامل") == [
        Citation(article=41, number="6", year=2010)
    ]


def test_parse_citation_eastern_digits_and_parentheses() -> None:
    assert parse_citations("نصت المادة (٤١) من القانون رقم ٦ لسنة ٢٠١٠") == [
        Citation(article=41, number="6", year=2010)
    ]


def test_parse_bare_article_has_no_law() -> None:
    assert parse_citations("تنص المادة 12 على ذلك") == [Citation(article=12, number=None, year=None)]


def test_parse_decree_law_citation() -> None:
    assert parse_citations("المادة 5 من المرسوم بقانون رقم 38 لسنة 1980") == [
        Citation(article=5, number="38", year=1980)
    ]
