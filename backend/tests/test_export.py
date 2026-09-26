import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

import pytest

from app.verification.export import render_html

REPORT = {
    "status": "needs_review", "score": 50, "summary_ar": "ملخص <b>التحقق</b>",
    "claims": [{"id": "C1", "text_ar": "فترة التجربة ستة أشهر", "type": "legal_premise", "verdict": "contradicted",
                "reasoning_ar": "المادة 3 تحددها بثلاثة أشهر",
                "evidence": [{"pid": "P1", "stance": "contradicts", "quote_ar": "لا تتجاوز ثلاثة أشهر", "note": None}]}],
    "passages": {"P1": {"title_ar": "القانون رقم 6 لسنة 2010", "number": "6", "year": 2010, "article_label": "المادة 3",
                        "status": "in_force"}},
    "references": {"supporting": [], "contradicting": [
        {"pid": "P1", "title_ar": "القانون رقم 6 لسنة 2010", "number": "6", "year": 2010,
         "article_label": "المادة 3", "status": "in_force", "quote_ar": "لا تتجاوز ثلاثة أشهر", "note": None}]},
}


def test_report_html_is_rtl_escaped_and_complete() -> None:
    html = render_html(title="رأي في فترة التجربة", question="ما مدة التجربة؟", final_text="الرأي المعتمد <script>",
                       report=REPORT, status="approved", score=50, approver="rev", approved_at="2026-09-26",
                       version=3, owner="lawyer", as_of="2026-09-26")
    assert 'dir="rtl"' in html and 'lang="ar"' in html
    assert "&lt;script&gt;" in html and "<script>" not in html  # user text escaped
    for text in ("الرأي المعتمد", "تحليل الادعاءات", "فترة التجربة ستة أشهر", "مناقَض", "المراجع المعارضة",
                 "لا تتجاوز ثلاثة أشهر", "المادة 3", "معتمد", "rev", "50 / 100"):
        assert text in html, text


def test_pdf_renders_when_weasyprint_is_available() -> None:
    try:
        from app.verification.export import html_to_pdf

        pdf = html_to_pdf(render_html(title="t", question=None, final_text="نص", report=REPORT, status="approved",
                                      score=50, approver="rev", approved_at="2026-09-26", version=1,
                                      owner="u", as_of=None))
    except OSError as e:  # Pango/GTK not installed (e.g. Windows dev machine) — runs in CI + Docker
        pytest.skip(f"WeasyPrint native libs unavailable: {e}")
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
