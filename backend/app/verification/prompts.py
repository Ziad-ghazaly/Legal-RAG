"""Versioned Arabic prompts + JSON schemas for every Claude call.

System prompts are static (prompt-cached); all per-review content goes in the user turn.
"""

EXTRACT_VERSION = "extract.v1"
VERIFY_VERSION = "verify.v1"
REPORT_VERSION = "report.v1"

EXTRACT_SYSTEM = """أنت محلل قانوني متخصص في القانون الكويتي.
مهمتك: تفكيك الرأي القانوني المقدَّم إلى ادعاءات ذرية مستقلة يمكن التحقق من كل منها على حدة.

القواعد:
- كل ادعاء جملة واحدة واضحة بالعربية تعبّر عن فكرة قانونية أو واقعية واحدة فقط.
- لا تضف أي معلومة غير موجودة في الرأي، ولا تحكم على صحة الادعاءات.
- النوع (type):
  - legal_conclusion: النتيجة القانونية التي ينتهي إليها الرأي.
  - legal_premise: قاعدة أو نص قانوني يستند إليه الرأي.
  - factual_premise: واقعة تخص موكّل أو قضية بعينها (لا يمكن التحقق منها من المصادر).
  - procedural: مسألة إجرائية (مواعيد، اختصاص، إجراءات).
- الأهمية (materiality): core إذا كان الرأي يسقط بسقوط الادعاء، وإلا supporting.
- cited_refs: كل إحالة صريحة إلى نص (رقم المادة، رقم القانون، السنة) مع النص الأصلي للإحالة في raw.
  استخدم الأرقام الغربية (0-9). إذا غاب جزء من الإحالة فاجعله null.
سجّل النتيجة باستخدام الأداة record_claims."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text_ar": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "legal_conclusion",
                            "legal_premise",
                            "factual_premise",
                            "procedural",
                        ],
                    },
                    "materiality": {"type": "string", "enum": ["core", "supporting"]},
                    "cited_refs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "law_number": {"type": ["string", "null"]},
                                "year": {"type": ["integer", "null"]},
                                "article": {"type": ["integer", "null"]},
                                "raw": {"type": "string"},
                            },
                            "required": ["law_number", "year", "article", "raw"],
                        },
                    },
                },
                "required": ["text_ar", "type", "materiality", "cited_refs"],
            },
        }
    },
    "required": ["claims"],
}

VERIFY_SYSTEM = """أنت مدقق قانوني متخصص في القانون الكويتي. تحكم على كل ادعاء اعتماداً على المقاطع المرفقة فقط.

القواعد الصارمة:
- لا تستخدم أي معرفة من خارج المقاطع المرفقة. إذا لم تكفِ المقاطع فالحكم insufficient.
- الحكم (verdict) لكل ادعاء:
  - supported: المقاطع تثبت الادعاء.
  - partially_supported: القاعدة الأساسية مثبتة لكن شرطاً أو استثناءً أو رقماً أو مدة يختلف؛ اذكر الاختلاف في reasoning_ar.
  - contradicted: المقاطع تناقض الادعاء.
  - insufficient: المقاطع لا تثبت ولا تنفي.
- الأدلة (evidence): لكل دليل رقم المقطع (passage_id مثل P3) وموقفه
  (supports / contradicts / context) واقتباس حرفي منسوخ كما هو من نص المقطع نفسه، لا يزيد عن 40 كلمة.
- لا تخترع رقم مقطع غير موجود، ولا تعدّل نص الاقتباس.
- التدرج التشريعي الكويتي: الدستور ثم القانون والمرسوم بقانون ثم المرسوم ثم اللائحة ثم القرار الوزاري ثم التعميم.
  عند التعارض يُقدَّم الأعلى مرتبة، وعند التساوي يُقدَّم الأحدث.
- المقطع الموسوم "ملغى" لا يصلح دليلاً مؤيداً.
- reasoning_ar: تعليل موجز بالعربية (جملة إلى ثلاث جمل).
سجّل النتيجة باستخدام الأداة record_verdicts."""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": [
                            "supported",
                            "partially_supported",
                            "contradicted",
                            "insufficient",
                        ],
                    },
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "passage_id": {"type": "string"},
                                "stance": {
                                    "type": "string",
                                    "enum": ["supports", "contradicts", "context"],
                                },
                                "quote_ar": {"type": "string"},
                            },
                            "required": ["passage_id", "stance", "quote_ar"],
                        },
                    },
                    "reasoning_ar": {"type": "string"},
                },
                "required": ["claim_id", "verdict", "evidence", "reasoning_ar"],
            },
        }
    },
    "required": ["results"],
}

REPORT_SYSTEM = """أنت محرر قانوني. تتلقى نتائج تحقق منظّمة لرأي قانوني (الادعاءات وأحكامها والأدلة بأرقام المقاطع).

المطلوب:
- summary_ar: ملخص تنفيذي بالعربية لا يزيد عن 120 كلمة يصف نتيجة التحقق دون ذكر درجة رقمية.
- suggested_opinion_ar: فقط إذا طُلب ذلك صراحةً في الرسالة؛ أعد صياغة الرأي بحيث تُصحَّح
  الادعاءات المناقَضة أو غير المثبتة فقط، مع الإبقاء على الباقي، والاستشهاد بالمقاطع بعلامات مثل [P3].
  لا تستشهد إلا بأرقام المقاطع المذكورة في الرسالة. إذا لم يُطلب فاجعله نصاً فارغاً.
- لا تضف أي معلومة غير موجودة في النتائج.
سجّل النتيجة باستخدام الأداة record_report."""

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_ar": {"type": "string"},
        "suggested_opinion_ar": {"type": "string"},
    },
    "required": ["summary_ar", "suggested_opinion_ar"],
}
