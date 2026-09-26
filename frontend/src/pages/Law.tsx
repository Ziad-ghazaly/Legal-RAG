import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api, type LawDetail, type LawUnit } from "../api";
import { Chip, ErrorNote } from "../components/ui";
import { DOC_TYPE_AR, noteBadges } from "../labels";

/** Chapter headings (الباب / الفصل / الفرع …) that change between consecutive units. */
function headingsBefore(prev: LawUnit | undefined, unit: LawUnit): { level: number; text: string }[] {
  const out: { level: number; text: string }[] = [];
  unit.path.forEach((p, i) => {
    if (!prev || prev.path[i] !== p || out.length) out.push({ level: i, text: p });
  });
  return out;
}

export default function Law() {
  const { docId = "" } = useParams();
  const { hash } = useLocation();
  const target = decodeURIComponent(hash.replace(/^#/, ""));
  const q = useQuery({
    queryKey: ["law", docId],
    queryFn: () => api<LawDetail>(`/laws/${encodeURIComponent(docId)}`),
    staleTime: 300_000,
  });
  const [filter, setFilter] = useState("");

  const units = useMemo(() => {
    const f = filter.trim();
    return (q.data?.units ?? []).filter(
      (u) => !f || u.text.includes(f) || (u.article_label ?? "").includes(f) || String(u.article_number ?? "") === f,
    );
  }, [q.data, filter]);

  const toc = useMemo(() => {
    const seen = new Set<string>();
    const out: { level: number; text: string; unitId: string }[] = [];
    for (const u of q.data?.units ?? [])
      u.path.forEach((p, i) => {
        const key = u.path.slice(0, i + 1).join(" › ");
        if (!seen.has(key)) {
          seen.add(key);
          out.push({ level: i, text: p, unitId: u.id });
        }
      });
    return out;
  }, [q.data]);

  useEffect(() => {
    if (!target || !q.data) return;
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [target, q.data]);

  if (q.isLoading) return <p className="text-muted">جارٍ التحميل…</p>;
  if (!q.data) return <ErrorNote error={q.error} />;
  const d = q.data.document;

  return (
    <section className="space-y-4">
      <Link to="/laws" className="text-primary hover:underline">← كل التشريعات</Link>
      <header className="card space-y-2 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone="supported">{DOC_TYPE_AR[d.doc_type] ?? d.doc_type}</Chip>
          {d.number && d.year && <span className="text-sm text-muted">رقم {d.number} لسنة {d.year}</span>}
        </div>
        <h1 className="text-lg font-bold leading-8">{d.title_ar}</h1>
        <input
          className="input max-w-md"
          placeholder="ابحث داخل القانون: رقم مادة أو عبارة"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="البحث داخل القانون"
        />
      </header>
      <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
        <nav className="card h-fit max-h-[75vh] overflow-y-auto p-4 lg:sticky lg:top-4" aria-label="فهرس القانون">
          <h2 className="mb-2 font-bold">الفهرس</h2>
          {toc.length === 0 && <p className="text-sm text-muted">لا توجد أبواب أو فصول.</p>}
          {toc.map((t) => (
            <a key={`${t.unitId}-${t.level}-${t.text}`} href={`#${encodeURIComponent(t.unitId)}`}
              className="block py-1 text-sm text-muted hover:text-primary" style={{ paddingInlineStart: `${t.level * 0.9}rem` }}>
              {t.text}
            </a>
          ))}
        </nav>
        <div className="space-y-3">
          {units.map((u, i) => (
            <div key={u.id}>
              {!filter && headingsBefore(units[i - 1], u).map((h) => (
                <h3 key={`${u.id}-${h.level}`} className={`mt-4 font-bold text-primary ${h.level ? "text-base" : "text-lg"}`}>{h.text}</h3>
              ))}
              <article id={u.id}
                className={`card space-y-2 p-4 ${u.id === target ? "ring-2 ring-accent" : ""} ${u.status === "repealed" ? "opacity-70" : ""}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{u.article_label ?? "نص"}</span>
                  {noteBadges(u.status, u.notes).map((b) => <Chip key={b.label} tone={b.tone}>{b.label}</Chip>)}
                </div>
                <p className="whitespace-pre-wrap leading-8">{u.text}</p>
                {u.notes.length > 0 && (
                  <ul className="space-y-1 border-t border-line pt-2 text-xs text-warn">
                    {u.notes.map((n) => <li key={n}>{n}</li>)}
                  </ul>
                )}
              </article>
            </div>
          ))}
          {units.length === 0 && <p className="text-muted">لا توجد نتائج مطابقة.</p>}
        </div>
      </div>
    </section>
  );
}
