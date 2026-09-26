"""مجموعة التشريعات الكويتية (markdown) → ingestion-contract JSONL.

Format (Jazaa Al-Otaibi compilation): `# Law` headings, a blockquote with the formal
title/number/year, `##`–`######` chapter headings, `**مادة N**` article headings
(with `مكرر` / ordinal variants), and `[^pX-Y]` footnotes carrying legislative history.

    python -m tools.md_to_jsonl SOURCE.md > corpus.jsonl
"""

import json
import re
import sys
from pathlib import Path

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_ORDINALS = {
    "اولى": 1, "أولى": 1, "ثانية": 2, "ثالثة": 3, "رابعة": 4, "خامسة": 5, "سادسة": 6,
    "سابعة": 7, "ثامنة": 8, "تاسعة": 9, "عاشرة": 10, "حادية عشرة": 11, "ثانية عشرة": 12,
    "ثالثة عشرة": 13, "رابعة عشرة": 14, "خامسة عشرة": 15,
}  # fmt: skip
_ORD = "|".join(sorted(_ORDINALS, key=len, reverse=True))
_FOOTNOTE_DEF = re.compile(r"^\[\^(p\d+-\d+)\]:\s*(.*)$")
_FOOTNOTE_REF = re.compile(r"\[\^(p\d+-\d+)\]")
_ARTICLE = re.compile(
    rf"^\*\*\s*(?:ال)?مادة\s*(?:رقم\s*)?\(?\s*(?:(?P<num>[0-9٠-٩]+)|(?:ال)?(?P<ord>{_ORD}))\s*\)?"
    r"\s*(?P<bis>مكرر(?:اً|ًا|ا)?)?\s*(?P<bisn>[0-9٠-٩]+|\([^)]{1,4}\))?\s*\*\*$"
)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_NUM_YEAR = re.compile(r"(?:رقم\s*)?([0-9٠-٩]+)\s*لسنة\s*([0-9٠-٩]{4})")
_YEAR = re.compile(r"لسنة\s*([0-9٠-٩]{4})")
_REPEALED = {"ملغاة", "ملغاه", "ملغى", "ملغي"}


def _doc_type(title: str, formal: str) -> str:
    if title.startswith("دستور"):  # not "المحكمة الدستورية"
        return "constitution"
    f = formal.replace("أ", "ا")
    if re.search(r"مرسوم\s+ب(?:ال)?قانون", f):
        return "decree_law"
    if re.search(r"^(?:ال)?قانون|امر\s+اميري\s+بالقانون|مرسوم\s+اميري", f):
        return "law"
    if f.startswith(("مرسوم", "المرسوم")):
        return "regulation" if "لائحة" in f + title else "decree"
    if "قرار" in f:
        return "ministerial_decision"
    return "law"


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace("**", "")).strip()


def convert(md: str) -> list[dict]:
    lines = md.splitlines()
    notes_by_ref = {m[1]: m[2].strip() for ln in lines if (m := _FOOTNOTE_DEF.match(ln.strip()))}
    docs: dict[str, dict] = {}
    doc: dict | None = None
    path: list[tuple[int, str]] = []
    unit: dict | None = None  # article or section being filled
    formal = ""

    def close() -> None:
        nonlocal unit
        if doc is None or unit is None:
            unit = None
            return
        text = "\n".join(unit.pop("lines")).strip()
        notes = unit["notes"]
        if unit["level"] == "article":
            if re.sub(r"[^\w]", "", text) in _REPEALED:
                unit["status"] = "repealed"
                text = "ملغاة" + (" — " + "؛ ".join(notes) if notes else "")
            elif any("وقف العمل" in n for n in notes):
                unit["status"] = "suspended"
        if text:
            unit["text"] = text
            doc["units"].append(unit)
        unit = None

    def new_unit(level: str, label: str, uid: str, number: int | None = None) -> dict:
        taken = {u["unit_id"] for u in doc["units"]}  # type: ignore[index]
        base, n = uid, 2
        while uid in taken:
            uid, n = f"{base}-{n}", n + 1
        return {"unit_id": uid, "level": level, "article_number": number, "article_label": label,
                "path": [t for _, t in path], "notes": [], "lines": []}

    for i, raw in enumerate(lines):
        line = raw.strip()
        if _FOOTNOTE_DEF.match(line) or line.startswith(">"):
            continue
        refs = _FOOTNOTE_REF.findall(line)
        line = _FOOTNOTE_REF.sub("", line).strip()

        if h := _HEADING.match(line):
            level, title = len(h[1]), _clean(h[2])
            close()
            if level == 1:
                path = []
                if title == "فهرس القوانين":
                    doc = None
                    continue
                quote = next((ln for ln in lines[i + 1 : i + 6] if ln.startswith(">")), "")
                formal = _clean(quote.lstrip("> "))
                base_title = re.sub(r"\s*\(تابع\)\s*$", "", title)
                dtype = _doc_type(base_title, formal)
                ny, y = _NUM_YEAR.search(formal), _YEAR.search(formal)
                number = ny[1].translate(_DIGITS).lstrip("0") if ny else None
                year = int((ny[2] if ny else y[1] if y else "0").translate(_DIGITS)) or None
                if dtype == "constitution":
                    number, year, formal = None, 1962, base_title
                doc_id = f"kw-{dtype}-{number}-{year}" if number else f"kw-{dtype}-{year}"
                doc = docs.setdefault(doc_id, {
                    "doc_id": doc_id, "doc_type": dtype, "title_ar": formal or base_title,
                    "number": number, "year": year, "units": [],
                })
                if not doc["units"]:
                    unit = new_unit("section", "الديباجة", f"{doc_id}/preamble")
                continue
            if doc is None:
                continue
            path = [(lv, t) for lv, t in path if lv < level]
            if title != doc["title_ar"]:
                path.append((level, title))
                slug = len(doc["units"]) + 1
                unit = new_unit("section", title, f"{doc['doc_id']}/s{slug}")
                unit["path"] = [t for lv, t in path[:-1]]
            continue

        if doc is None:
            continue
        if a := _ARTICLE.match(_FOOTNOTE_REF.sub("", raw.strip())):
            close()
            num = int(a["num"].translate(_DIGITS)) if a["num"] else _ORDINALS[a["ord"]]
            label = f"المادة {num}" + (" مكرر" if a["bis"] else "")
            uid = f"{doc['doc_id']}/a{num}" + ("-bis" if a["bis"] else "")
            if a["bisn"]:
                label += f" {a['bisn']}"
                uid += "-" + re.sub(r"\W", "", a["bisn"].translate(_DIGITS))
            unit = new_unit("article", label, uid, num)
            unit["notes"].extend(notes_by_ref[r] for r in refs if r in notes_by_ref)
            continue

        if unit is None:
            continue
        unit["notes"].extend(notes_by_ref[r] for r in refs if r in notes_by_ref)
        if text := _clean(line):
            unit["lines"].append(text)
    close()

    out = []
    for d in docs.values():
        for u in d["units"]:
            if not u["notes"]:
                del u["notes"]
            if u["article_number"] is None:
                del u["article_number"]
        out.append(d)
    return out


def main() -> None:
    docs = convert(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    for d in docs:
        print(json.dumps(d, ensure_ascii=False))


if __name__ == "__main__":
    main()
