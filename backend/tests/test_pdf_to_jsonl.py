from tools.pdf_to_jsonl import fix_lam_alef, split_articles

TEXT = """قانون العمل الكويتي
الفصل الأول: تعريفات ونطاق التطبيق
تسري أحكام هذا القانون على جميع علاقات العمل.
المادة الأولى: تعريف صاحب العمل
يقصد بصاحب العمل كل شخص طبيعي أو معنوي.
الفصل الثاني: إبرام عقد العمل
المادة (2)
يجب أن يتضمن عقد العمل البيانات التالية.
المادة ١٢: فترة التجربة
يجوز الاتفاق على فترة تجربة.
"""


def test_split_articles_numbers_ordinals_and_chapter_paths() -> None:
    arts = split_articles(TEXT)
    assert [a["article_number"] for a in arts] == [1, 2, 12]
    assert arts[0]["path"] == ["الفصل الأول: تعريفات ونطاق التطبيق"]
    assert arts[1]["path"] == ["الفصل الثاني: إبرام عقد العمل"]
    assert arts[0]["article_label"] == "المادة 1"
    assert arts[0]["text"].startswith("المادة الأولى: تعريف صاحب العمل")
    assert "يقصد بصاحب العمل" in arts[0]["text"]
    assert "الفصل الثاني" not in arts[0]["text"]


def test_fix_lam_alef_repairs_swapped_hamza_ligature() -> None:
    assert fix_lam_alef("الفصل األول واإلجراءات") == "الفصل الأول والإجراءات"
