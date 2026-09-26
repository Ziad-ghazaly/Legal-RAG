"""PDF export of a verified opinion: Arabic RTL HTML → WeasyPrint (HarfBuzz shaping).

The document is rendered from structured data only; every user/LLM string is escaped.
"""

from html import escape
from typing import Any

STATUS_AR = {
    "accepted": "مقبول",
    "approved": "معتمد",
    "needs_review": "يحتاج مراجعة",
    "no_information": "لا تتوفر معلومات",
    "rejected": "مرفوض",
}
VERDICT_AR = {
    "supported": "مؤيد",
    "partially_supported": "مؤيد جزئياً",
    "contradicted": "مناقَض",
    "insufficient": "غير كافٍ",
}
TYPE_AR = {
    "legal_conclusion": "نتيجة قانونية",
    "legal_premise": "مقدمة قانونية",
    "factual_premise": "واقعة",
    "procedural": "إجرائي",
}
SOURCE_STATUS_AR = {
    "in_force": "ساري",
    "amended": "معدّل",
    "repealed": "ملغى",
    "suspended": "موقوف العمل",
}
STANCE_AR = {"supports": "مؤيد", "contradicts": "معارض", "context": "سياق"}

_CSS = """
@page { size: A4; margin: 18mm 16mm 20mm;
  @bottom-center { content: "صفحة " counter(page) " من " counter(pages); font-size: 9pt; color: #5B6675; } }
body { font-family: "IBM Plex Sans Arabic", "Noto Naskh Arabic", "Noto Sans Arabic", serif;
  font-size: 11pt; color: #1E2733; line-height: 1.7; }
h1 { color: #1F4E79; font-size: 18pt; margin: 0 0 4pt; }
h2 { color: #1F4E79; font-size: 13pt; border-bottom: 1.5pt solid #1F4E79; padding-bottom: 2pt; margin-top: 16pt; }
.muted { color: #5B6675; font-size: 9.5pt; }
table { width: 100%; border-collapse: collapse; margin-top: 6pt; }
th, td { border: 0.6pt solid #D9DEE5; padding: 4pt 6pt; vertical-align: top; text-align: right; }
th { background: #F5F7FA; }
.meta td:first-child { width: 28%; background: #F5F7FA; font-weight: 600; }
.opinion { white-space: pre-wrap; border: 0.6pt solid #D9DEE5; background: #FFFFFF; padding: 8pt; }
.quote { background: #F5F7FA; border-right: 2.5pt solid #3B82C4; padding: 3pt 6pt; margin: 3pt 0; }
.con .quote { border-right-color: #B42318; }
.chip { font-weight: 600; }
.contradicted { color: #B42318; } .supported, .partially_supported { color: #1F4E79; }
.insufficient { color: #5B6675; } .note { color: #B54708; font-size: 9.5pt; }
"""


def _cite(p: dict[str, Any]) -> str:
    law = f" (رقم {p['number']} لسنة {p['year']})" if p.get("number") and p.get("year") else ""
    art = f" — {p['article_label']}" if p.get("article_label") else ""
    return escape(f"{p.get('title_ar', '')}{law}{art}")


def _refs(title: str, refs: list[dict[str, Any]], cls: str) -> str:
    if not refs:
        return f"<h2>{title}</h2><p class='muted'>لا توجد مراجع.</p>"
    items = "".join(
        f"<div><b>{_cite(r)}</b> <span class='muted'>({escape(SOURCE_STATUS_AR.get(r.get('status', ''), ''))})</span>"
        f"<div class='quote'>«{escape(r.get('quote_ar', ''))}»</div>"
        + (f"<div class='note'>{escape(r['note'])}</div>" if r.get("note") else "")
        + "</div>"
        for r in refs
    )
    return f"<h2>{title}</h2><div class='{cls}'>{items}</div>"


def render_html(
    *,
    title: str | None,
    question: str | None,
    final_text: str,
    report: dict[str, Any],
    status: str,
    score: int | None,
    approver: str | None,
    approved_at: str | None,
    version: int | None,
    owner: str,
    as_of: str | None,
) -> str:
    passages = report.get("passages", {})
    rows = []
    for c in report.get("claims", []):
        ev = "".join(
            f"<div class='quote'><span class='chip'>{STANCE_AR.get(e['stance'], '')}</span> "
            f"[{escape(e['pid'])}] {_cite(passages.get(e['pid'], {}))}<br>«{escape(e['quote_ar'])}»"
            + (f"<div class='note'>{escape(e['note'])}</div>" if e.get("note") else "")
            + "</div>"
            for e in c.get("evidence", [])
        )
        verdict = c.get("verdict")
        rows.append(
            f"<tr><td>{escape(c['id'])}</td><td>{escape(c['text_ar'])}"
            f"<div class='muted'>{escape(c.get('reasoning_ar') or '')}</div>{ev}</td>"
            f"<td>{escape(TYPE_AR.get(c.get('type', ''), ''))}</td>"
            f"<td class='{escape(verdict or '')}'>{escape(VERDICT_AR.get(verdict or '', 'غير مُقيَّم'))}</td></tr>"
        )
    meta = [
        ("الحالة", STATUS_AR.get(status, status)),
        ("درجة التحقق", f"{score} / 100" if score is not None else "—"),
        ("مقدم الطلب", owner),
        ("المعتمِد", approver or "النظام (قبول تلقائي)"),
        ("تاريخ الاعتماد", approved_at or "—"),
        ("رقم النسخة المعتمدة", str(version) if version else "—"),
        ("التاريخ المرجعي", as_of or "—"),
    ]
    meta_rows = "".join(f"<tr><td>{escape(k)}</td><td>{escape(v)}</td></tr>" for k, v in meta)
    refs = report.get("references", {})
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{_CSS}</style></head><body>
<h1>تقرير التحقق من الرأي القانوني</h1>
<div class="muted">{escape(title or "")}</div>
<table class="meta">{meta_rows}</table>
{f"<h2>السؤال أو الوقائع</h2><p>{escape(question)}</p>" if question else ""}
<h2>الرأي القانوني المعتمد</h2><div class="opinion">{escape(final_text)}</div>
<h2>ملخص التحقق</h2><p>{escape(report.get("message_ar") or report.get("summary_ar") or "")}</p>
<h2>تحليل الادعاءات</h2>
<table><tr><th>#</th><th>الادعاء والأدلة</th><th>النوع</th><th>الحكم</th></tr>{"".join(rows)}</table>
{_refs("المراجع المؤيدة", refs.get("supporting", []), "sup")}
{_refs("المراجع المعارضة", refs.get("contradicting", []), "con")}
<p class="muted">أُعدّ هذا التقرير آلياً من المصادر المتاحة في المنصة واعتُمد وفق سجل المراجعة.</p>
</body></html>"""


def html_to_pdf(html: str) -> bytes:
    from weasyprint import HTML  # native Pango/HarfBuzz; imported lazily

    return HTML(string=html).write_pdf()
