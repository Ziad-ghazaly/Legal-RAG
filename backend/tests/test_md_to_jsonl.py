"""Converter for مجموعة التشريعات الكويتية (markdown) → ingestion JSONL."""

from app.ingestion.contract import DocumentIn
from tools.md_to_jsonl import convert

SAMPLE = """**مجموعة التشريعات الكويتية — التعديلات حتى 1 / 4 / 2026**

# فهرس القوانين

- دستور دولة الكويت — ص 4

# دستور دولة الكويت

> **والمذكرة التفسيرية**
> الصفحات 4–40 من الملف الأصلي

نحن عبد الله السالم الصباح ، أمير دولة الكويت، رغبة في استكمال أسباب الحكم الديمقراطي لوطننا العزيز.

## الباب الاول : الدولة ونظام الحكم

**مادة 1**

الكويت دولة عربية مستقلة ذات سيادة تامة، ولا يجوز النزول عن سيادتها.

**مادة 2[^p8-1]**

دين الدولة الإسلام، والشريعة الإسلامية مصدر رئيسي للتشريع.

[^p8-1]: تم وقف العمل بالمادة عملا بالامر الاميري المؤرخ 10 / 5 / 2024 وذلك لمدة لا تزيد على 4 سنوات .

## المذكرة التفسيرية لدستور دولة الكويت

**أولاً : التصوير العام لنظام الحكم**

امتثالاً لقوله تعالى وشاورهم في الأمر، واستشرافاً لمكانة الفرد وكرامته، اتجه الدستور إلى النظام الديمقراطي.

# قانون الجزاء الكويتي

> **القانون رقم 16 لسنة 1960 بإصدار قانون الجزاء وتعديلاته**
> الصفحات 110–156 من الملف الأصلي

**المادة الأولى**

يعمل بقانون الجزاء المرافق لهذا القانون من تاريخ نشره في الجريدة الرسمية.

### الباب الأول : أحكام تمهيدية

#### الفصل الأول : نطاق التطبيق

**مادة 1**

لا جريمة ولا عقوبة إلا بنص في القانون، ولا عقاب إلا على الأفعال اللاحقة لنفاذه.

**مادة 19[^p112-1]**

ملغاة

**مادة 70 مكرر[^p113-2]**

يعاقب بالحبس مدة لا تجاوز سنة كل من أذاع أخباراً كاذبة من شأنها الإضرار بالمصالح القومية.

[^p112-1]: المواد ( 20-19 - 21 ) ملغاة بموجب القانون رقم 3 لسنة 1983 بشأن الأحداث
[^p113-2]: مضافة وفق القانون رقم 5 لسنة 2020

# مرسوم الخدمة المدنية

> **مرسوم بقانون رقم 15 لسنة 1979 بشأن الخدمة المدنية**

**مادة 1**

تسري أحكام هذا القانون على الجهات الحكومية التي تتولى الخدمة المدنية وموظفيها.

# قانون الجزاء الكويتي (تابع)

> **القانون رقم 16 لسنة 1960 بإصدار قانون الجزاء وتعديلاته**

**مادة 250**

يعاقب على الشروع في الجنايات بالعقوبات المقررة في هذا الباب ما لم ينص القانون على خلاف ذلك.
"""


def by_id(docs):
    return {d["doc_id"]: d for d in docs}


def units(doc):
    return {u["unit_id"]: u for u in doc["units"]}


def test_documents_types_numbers_and_titles() -> None:
    docs = by_id(convert(SAMPLE))
    assert set(docs) == {"kw-constitution-1962", "kw-law-16-1960", "kw-decree_law-15-1979"}
    const = docs["kw-constitution-1962"]
    assert const["doc_type"] == "constitution" and const["title_ar"] == "دستور دولة الكويت"
    penal = docs["kw-law-16-1960"]
    assert (penal["number"], penal["year"]) == ("16", 1960)
    assert penal["title_ar"] == "القانون رقم 16 لسنة 1960 بإصدار قانون الجزاء وتعديلاته"
    assert docs["kw-decree_law-15-1979"]["doc_type"] == "decree_law"


def test_articles_paths_and_bis_articles() -> None:
    penal = units(by_id(convert(SAMPLE))["kw-law-16-1960"])
    a1 = penal["kw-law-16-1960/a1-2"]  # a1 is the issuing law's المادة الأولى
    assert a1["article_number"] == 1 and a1["article_label"] == "المادة 1"
    assert a1["path"] == ["الباب الأول : أحكام تمهيدية", "الفصل الأول : نطاق التطبيق"]
    assert a1["text"].startswith("لا جريمة ولا عقوبة")
    bis = penal["kw-law-16-1960/a70-bis"]
    assert bis["article_number"] == 70 and bis["article_label"] == "المادة 70 مكرر"
    assert bis["notes"] == ["مضافة وفق القانون رقم 5 لسنة 2020"]


def test_issuing_law_ordinal_article_does_not_collide_with_code_article_1() -> None:
    penal = units(by_id(convert(SAMPLE))["kw-law-16-1960"])
    assert "kw-law-16-1960/a1" in penal and "kw-law-16-1960/a1-2" in penal
    assert penal["kw-law-16-1960/a1-2"]["text"].startswith("لا جريمة")  # code article comes second


def test_repealed_and_suspended_articles() -> None:
    docs = by_id(convert(SAMPLE))
    a19 = units(docs["kw-law-16-1960"])["kw-law-16-1960/a19"]
    assert a19["status"] == "repealed"
    assert a19["text"].startswith("ملغاة") and "القانون رقم 3 لسنة 1983" in a19["text"]
    a2 = units(docs["kw-constitution-1962"])["kw-constitution-1962/a2"]
    assert a2["status"] == "suspended" and a2["notes"][0].startswith("تم وقف العمل")
    assert "[^" not in a2["text"] and "تم وقف" not in a2["text"]  # footnote not merged into the text
    assert units(docs["kw-constitution-1962"])["kw-constitution-1962/a1"].get("status") is None


def test_preamble_and_memorandum_become_sections() -> None:
    const = by_id(convert(SAMPLE))["kw-constitution-1962"]
    sections = [u for u in const["units"] if u["level"] == "section"]
    assert sections[0]["article_label"] == "الديباجة" and sections[0]["text"].startswith("نحن عبد الله")
    memo = next(u for u in sections if "المذكرة التفسيرية" in u["article_label"])
    assert "النظام الديمقراطي" in memo["text"] and "**" not in memo["text"]


def test_continuation_heading_merges_into_the_same_law() -> None:
    penal = units(by_id(convert(SAMPLE))["kw-law-16-1960"])
    assert "kw-law-16-1960/a250" in penal


def test_output_is_a_valid_ingestion_contract() -> None:
    for d in convert(SAMPLE):
        DocumentIn.model_validate(d)


def test_constitutional_court_laws_are_not_the_constitution() -> None:
    md = """# قانون انشاء المحكمة الدستورية

> **القانون رقم 14 لسنة 1973 بإنشاء المحكمة الدستورية**

**مادة 1**

تنشأ محكمة دستورية تختص دون غيرها بتفسير النصوص الدستورية.

# لائحة المحكمة الدستورية

> **مرسوم لسنة 1974 بإصدار لائحة المحكمة الدستورية**

**مادة 1**

تقدم طلبات تفسير النصوص الدستورية إلى المحكمة الدستورية من مجلس الأمة أو مجلس الوزراء.
"""
    docs = by_id(convert(md))
    assert set(docs) == {"kw-law-14-1973", "kw-regulation-1974"}


def test_plain_line_article_headings_are_split_not_merged() -> None:
    """Rule 2 found articles glued together where the compilation's heading isn't bold."""
    md = """# القانون المدني

> **المرسوم بالقانون رقم 67 لسنة 1980م بإصدار القانون المدني**

**مادة 519**

1- يسري على بيع المريض مرض الموت أحكام المادة (942).

المادة (519 مكرر)

السلم بيع مؤجل التسليم بثمن معجل.

المادة (519 مكرر أ )

يشترط في المسلم فيه أن يكون مما يجوز بيعه.

المادة 213 مكرر 10

مع عدم الإخلال بأحكام سقوط الحق بمضي المدة يترتب على إلغاء حكم الإدانة محو آثاره.

المادة السابقة تسري على العقود المبرمة قبل العمل بهذا القانون.
"""
    (doc,) = convert(md)
    u = units(doc)
    assert list(u) == [
        "kw-decree_law-67-1980/a519",
        "kw-decree_law-67-1980/a519-bis",
        "kw-decree_law-67-1980/a519-bis-أ",
        "kw-decree_law-67-1980/a213-bis-10",
    ]
    assert u["kw-decree_law-67-1980/a519"]["text"] == "1- يسري على بيع المريض مرض الموت أحكام المادة (942)."
    assert u["kw-decree_law-67-1980/a519-bis-أ"]["article_label"] == "المادة 519 مكرر أ"
    # a sentence that merely starts with "المادة السابقة" stays body text
    assert u["kw-decree_law-67-1980/a213-bis-10"]["text"].endswith("قبل العمل بهذا القانون.")


def test_bis_suffixes_with_guillemets_and_dashes_are_split() -> None:
    md = """# قانون الجزاء

> **القانون رقم 16 لسنة 1960 بإصدار قانون الجزاء**

**مادة 237 مكررا**

لا يسأل جزائيا من ارتكب الفعل تنفيذا لأمر صادر إليه.

مادة 237 مكرر1 « أ »

لا تقام الدعوى الجزائية إلا بناء على طلب.

المادة 26 مكررا -ج

يجوز للمؤجر إنهاء العقد.

المادة 26 مكرر - د

للمستأجر حق البقاء في العين.
"""
    (doc,) = convert(md)
    u = units(doc)
    assert list(u) == ["kw-law-16-1960/a237-bis", "kw-law-16-1960/a237-bis-1أ",
                       "kw-law-16-1960/a26-bis-ج", "kw-law-16-1960/a26-bis-د"]
    assert u["kw-law-16-1960/a237-bis"]["text"] == "لا يسأل جزائيا من ارتكب الفعل تنفيذا لأمر صادر إليه."


def test_heading_glued_to_its_text_starts_a_new_article() -> None:
    md = """# قانون العمالة المنزلية

> **القانون رقم 68 لسنة 2015 في شأن العمالة المنزلية**

**مادة 27**

يستحق العامل المنزلي أجراً إضافياً عن ساعات العمل الإضافية.

مادة 28إذا رفض صاحب العمل تعويض العامل المنزلي كان له التقدم بشكوى.

المادة رقم 29يشمل الأجر كل ما يتقاضاه العامل.

وفقاً للمواد 61 إلى 64 من الدستور.
"""
    (doc,) = convert(md)
    u = units(doc)
    assert list(u) == ["kw-law-68-2015/a27", "kw-law-68-2015/a28", "kw-law-68-2015/a29"]
    assert u["kw-law-68-2015/a28"]["text"] == "إذا رفض صاحب العمل تعويض العامل المنزلي كان له التقدم بشكوى."
    assert u["kw-law-68-2015/a29"]["text"].startswith("يشمل الأجر")
