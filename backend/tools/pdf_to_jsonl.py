"""Dev tool: PDF/DOCX → ingestion-contract JSONL (one document).

The client normally delivers preprocessed JSONL. This tool exists so a dev corpus
can be built from local files. Scanned PDFs (no text layer) are out of scope.

    python -m tools.pdf_to_jsonl FILE --doc-id kw-labor --doc-type law \
        --title "قانون العمل" --number 6 --year 2010 --mode articles >> corpus.jsonl
    python -m tools.pdf_to_jsonl FILE --doc-id study-1 --doc-type commentary \
        --title "..." --mode pages >> corpus.jsonl
"""

import argparse
import json
import re
import sys
from pathlib import Path

_ORDINALS = {
    "الأولى": 1, "الثانية": 2, "الثالثة": 3, "الرابعة": 4, "الخامسة": 5, "السادسة": 6,
    "السابعة": 7, "الثامنة": 8, "التاسعة": 9, "العاشرة": 10, "الحادية عشرة": 11,
    "الثانية عشرة": 12, "الثالثة عشرة": 13, "الرابعة عشرة": 14, "الخامسة عشرة": 15,
}  # fmt: skip
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_ARTICLE = re.compile(
    r"^\s*(?:ال)?مادة\s*(?:\(\s*([0-9٠-٩]+)\s*\)|([0-9٠-٩]+)|("
    + "|".join(sorted(_ORDINALS, key=len, reverse=True))
    + r"))"
)
_CHAPTER = re.compile(r"^\s*(?:الباب|الفصل|القسم)\s")


def fix_lam_alef(text: str) -> str:
    """PyMuPDF swaps lam and hamza-alef in some fonts: األ → الأ (never valid Arabic)."""
    return text.replace("األ", "الأ").replace("اإل", "الإ").replace("اآل", "الآ")


def split_articles(text: str) -> list[dict]:
    arts: list[dict] = []
    path: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if _CHAPTER.match(line):
            path = [line]
            continue
        m = _ARTICLE.match(line)
        if m:
            n = int((m[1] or m[2]).translate(_DIGITS)) if (m[1] or m[2]) else _ORDINALS[m[3]]
            arts.append({"article_number": n, "article_label": f"المادة {n}",
                         "path": list(path), "lines": [line]})
        elif arts:
            arts[-1]["lines"].append(line)
    for a in arts:
        a["text"] = "\n".join(a.pop("lines"))
    return arts


def _pages(path: Path) -> list[str]:
    if path.suffix.lower() == ".docx":
        import docx

        return ["\n".join(p.text for p in docx.Document(str(path)).paragraphs)]
    import pymupdf

    with pymupdf.open(str(path)) as d:
        return [fix_lam_alef(p.get_text("text")) for p in d]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--doc-type", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--number")
    ap.add_argument("--year", type=int)
    ap.add_argument("--effective-date")
    ap.add_argument("--mode", choices=["articles", "pages"], default="articles")
    a = ap.parse_args()

    pages = _pages(a.file)
    if a.mode == "articles":
        units = [
            {"unit_id": f"{a.doc_id}/a{x['article_number']}", "level": "article", **x}
            for x in split_articles("\n".join(pages))
        ]
    else:
        units = [
            {"unit_id": f"{a.doc_id}/p{i}", "level": "section", "article_label": f"صفحة {i}",
             "text": t.strip()}
            for i, t in enumerate(pages, start=1)
            if t.strip()
        ]
    if not units:
        sys.exit(f"no units extracted from {a.file} (scanned PDF? try --mode pages)")
    doc = {"doc_id": a.doc_id, "doc_type": a.doc_type, "title_ar": a.title, "number": a.number,
           "year": a.year, "effective_date": a.effective_date, "units": units}
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(json.dumps(doc, ensure_ascii=False))


if __name__ == "__main__":
    main()
