import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type LawSummary } from "../api";
import { Chip, ErrorNote } from "../components/ui";
import { DOC_TYPE_AR } from "../labels";

export default function Laws() {
  const q = useQuery({ queryKey: ["laws"], queryFn: () => api<LawSummary[]>("/laws"), staleTime: 300_000 });
  const [filter, setFilter] = useState("");
  const laws = useMemo(() => {
    const f = filter.trim();
    return (q.data ?? []).filter((l) => !f || l.title_ar.includes(f) || `${l.number ?? ""}/${l.year ?? ""}`.includes(f));
  }, [q.data, filter]);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">التشريعات</h1>
        <span className="text-sm text-muted">{q.data ? `${q.data.length} تشريعاً` : ""}</span>
        <input
          className="input ms-auto w-80"
          placeholder="ابحث باسم القانون أو رقمه (مثال: الجزاء، 67/1980)"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="البحث في التشريعات"
        />
      </div>
      <ErrorNote error={q.error} />
      {q.isLoading && <p className="text-muted">جارٍ التحميل…</p>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {laws.map((l) => (
          <Link key={l.id} to={`/laws/${encodeURIComponent(l.id)}`} className="card block space-y-2 p-4 hover:border-accent">
            <div className="flex items-center gap-2">
              <Chip tone="supported">{DOC_TYPE_AR[l.doc_type] ?? l.doc_type}</Chip>
              {l.number && l.year && <span className="text-xs text-muted">رقم {l.number} لسنة {l.year}</span>}
            </div>
            <div className="font-semibold leading-7 text-ink">{l.title_ar}</div>
            <div className="text-xs text-muted">{l.article_count} مادة</div>
          </Link>
        ))}
      </div>
      {q.data && laws.length === 0 && <p className="text-muted">لا توجد تشريعات مطابقة.</p>}
    </section>
  );
}
