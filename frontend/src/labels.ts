export const STATUS_AR: Record<string, string> = {
  processing: "قيد المعالجة",
  accepted: "مقبول",
  needs_review: "يحتاج مراجعة",
  no_information: "لا تتوفر معلومات",
  approved: "معتمد",
  rejected: "مرفوض",
  failed: "فشل",
};

export const VERDICT_AR: Record<string, string> = {
  supported: "مؤيد",
  partially_supported: "مؤيد جزئياً",
  contradicted: "مناقَض",
  insufficient: "غير كافٍ",
};

export const CLAIM_TYPE_AR: Record<string, string> = {
  legal_conclusion: "نتيجة قانونية",
  legal_premise: "مقدمة قانونية",
  factual_premise: "واقعة",
  procedural: "إجرائي",
};

export const SOURCE_STATUS_AR: Record<string, string> = {
  in_force: "ساري",
  amended: "معدّل",
  repealed: "ملغى",
  suspended: "موقوف العمل",
};

/** Badges from an article's legislative notes (footnotes of the compilation). */
export function noteBadges(status: string, notes: string[]): { label: string; tone: string }[] {
  const all = notes.join(" ");
  const out: { label: string; tone: string }[] = [];
  if (status === "repealed") out.push({ label: "ملغاة", tone: "contradicted" });
  if (status === "suspended") out.push({ label: "موقوفة", tone: "warn" });
  if (/معدل|مستبدل|عدلت|استبدل/.test(all)) out.push({ label: "معدّلة", tone: "supported" });
  if (/مضاف|اضيف|أضيف/.test(all)) out.push({ label: "مضافة", tone: "supported" });
  return out;
}

export function lawLink(documentId: string, unitId: string): string {
  return `/laws/${encodeURIComponent(documentId)}#${encodeURIComponent(unitId)}`;
}

export const DOC_TYPE_AR: Record<string, string> = {
  constitution: "الدستور",
  law: "قانون",
  decree_law: "مرسوم بقانون",
  decree: "مرسوم",
  regulation: "لائحة",
  ministerial_decision: "قرار وزاري",
  circular: "تعميم",
  court_ruling: "حكم قضائي",
  legal_opinion: "رأي قانوني",
  fatwa: "فتوى",
  commentary: "شرح",
};

export const ROLE_AR: Record<string, string> = { admin: "مشرف", reviewer: "مراجع", user: "مستخدم" };

export const JOB_STATUS_AR: Record<string, string> = {
  pending: "في الانتظار",
  processing: "قيد المعالجة",
  completed: "مكتملة",
  failed: "فشلت",
};

export const STAGES: { key: string; label: string }[] = [
  { key: "parsing", label: "قراءة الرأي" },
  { key: "extracting_claims", label: "استخراج الادعاءات" },
  { key: "retrieving", label: "البحث في المصادر" },
  { key: "verifying", label: "التحقق" },
  { key: "scoring", label: "حساب النتيجة" },
];

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ar-KW-u-nu-latn", { dateStyle: "medium", timeStyle: "short" });
}

export function citation(r: { title_ar: string; number: string | null; year: number | null; article_label: string | null }): string {
  const law = r.number && r.year ? ` (رقم ${r.number} لسنة ${r.year})` : "";
  return `${r.title_ar}${law}${r.article_label ? ` — ${r.article_label}` : ""}`;
}

const SEVERITY: Record<string, number> = { supported: 0, insufficient: 1, partially_supported: 2, contradicted: 3 };

export type OpinionMark = { id: string; verdict: string; start: number; end: number };

/** Non-overlapping highlight marks; a sentence shared by several claims shows its most severe verdict. */
export function opinionMarks(
  claims: { id: string; verdict?: string | null; span?: [number, number] | null }[],
): OpinionMark[] {
  const marks = claims
    .filter((c) => c.span && c.verdict)
    .map((c) => ({ id: c.id, verdict: c.verdict as string, start: c.span![0], end: c.span![1] }))
    .sort((a, b) => a.start - b.start || (SEVERITY[b.verdict] ?? 0) - (SEVERITY[a.verdict] ?? 0));
  const out: OpinionMark[] = [];
  for (const m of marks) if (!out.length || m.start >= out[out.length - 1].end) out.push(m);
  return out;
}
