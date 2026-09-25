"""Opinion file → text (PDF text layer, DOCX, TXT). Scanned PDFs are rejected clearly."""

import io

from app.text.arabic import arabic_ratio, fix_lam_alef

MIN_TEXT_CHARS = 20
MIN_ARABIC_RATIO = 0.5


class ParseError(ValueError):
    def __init__(self, message_ar: str) -> None:
        super().__init__(message_ar)
        self.message_ar = message_ar


def extract_text(filename: str, data: bytes) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1256", errors="replace")
    elif ext == "docx":
        import docx

        text = "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    elif ext == "pdf":
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as d:
            text = fix_lam_alef("\n".join(page.get_text("text") for page in d))
        if len(text.strip()) < MIN_TEXT_CHARS:
            # ponytail: no OCR yet (Tesseract `ara` in the worker is the upgrade path).
            raise ParseError("الملف ممسوح ضوئياً ولا يحتوي على نص قابل للقراءة. يرجى لصق نص الرأي.")
    else:
        raise ParseError("نوع الملف غير مدعوم. الأنواع المدعومة: PDF و DOCX و TXT.")
    text = text.strip()
    if len(text) < MIN_TEXT_CHARS:
        raise ParseError("الملف لا يحتوي على نص كافٍ للتحقق.")
    return text


def ensure_opinion_text(text: str) -> str:
    """Reject empty or non-Arabic/garbled text before any LLM call (hallucination guard)."""
    text = (text or "").strip()
    if len(text) < MIN_TEXT_CHARS:
        raise ParseError("النص قصير جداً للتحقق.")
    if arabic_ratio(text) < MIN_ARABIC_RATIO:
        raise ParseError("النص لا يبدو رأياً قانونياً مكتوباً بالعربية؛ تحقق من ترميز الملف أو النص.")
    return text
