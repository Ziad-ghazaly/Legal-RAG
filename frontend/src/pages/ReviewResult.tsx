import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, downloadPdf, json, streamEvents, type Reference, type Report, type ReviewDetail, type SourceChunk } from "../api";
import { useAuth } from "../auth";
import { Chip, ErrorNote, StatusBadge, Stepper } from "../components/ui";
import { CLAIM_TYPE_AR, DOC_TYPE_AR, SOURCE_STATUS_AR, VERDICT_AR, citation, formatDate } from "../labels";

const TABS = [
  { key: "summary", label: "الملخص" },
  { key: "claims", label: "تحليل الادعاءات" },
  { key: "refs", label: "المراجع" },
  { key: "similar", label: "آراء مشابهة" },
  { key: "suggested", label: "الرأي المقترح" },
] as const;
type Tab = (typeof TABS)[number]["key"];

export default function ReviewResult() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [stage, setStage] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [source, setSource] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["review", id], queryFn: () => api<ReviewDetail>(`/reviews/${id}`) });
  const processing = q.data?.status === "processing";

  useEffect(() => {
    if (!processing) return;
    const ctl = new AbortController();
    streamEvents(
      id,
      (e) => {
        setStage(e.stage);
        if (e.stage === "done" || e.stage === "failed") qc.invalidateQueries({ queryKey: ["review", id] });
      },
      ctl.signal,
    ).catch(() => {});
    const poll = setInterval(() => qc.invalidateQueries({ queryKey: ["review", id] }), 15000);
    return () => {
      ctl.abort();
      clearInterval(poll);
    };
  }, [id, processing, qc]);

  if (q.isLoading) return <p className="text-muted">جارٍ التحميل…</p>;
  if (q.error || !q.data) return <ErrorNote error={q.error} />;
  const r = q.data;
  const report = r.report;
  const tabs = TABS.filter((t) => t.key !== "suggested" || r.status === "needs_review");

  return (
    <section className="space-y-5">
      <header className="card flex flex-wrap items-center gap-6 p-5">
        <div className="min-w-0 flex-1 space-y-2">
          <h1 className="truncate text-lg font-bold">{r.title || "مراجعة"}</h1>
          <div className="flex items-center gap-3 text-sm text-muted">
            <StatusBadge status={r.status} />
            <span>{formatDate(r.created_at)}</span>
            {r.as_of_date && <span>التاريخ المرجعي: <span dir="ltr">{r.as_of_date}</span></span>}
            {r.status === "approved" && r.approved_by && (
              <span>اعتمده {r.approved_by}{r.approved_at ? ` · ${formatDate(r.approved_at)}` : ""}</span>
            )}
          </div>
        </div>
        {r.score !== null && (
          <div className="text-center">
            <div className="text-4xl font-bold text-primary" dir="ltr">{r.score} / 100</div>
            <div className="text-xs text-muted">درجة التحقق</div>
          </div>
        )}
        <ActionBar r={r} />
      </header>

      {processing && (
        <div className="card space-y-3 p-5">
          <Stepper current={stage ?? "parsing"} />
          <p className="text-sm text-muted">يجري التحقق من الرأي؛ ستظهر النتيجة تلقائياً عند الانتهاء.</p>
        </div>
      )}
      {r.status === "failed" && <ErrorNote error={new Error(r.error_ar ?? "فشل التحقق.")} />}
      {r.status === "rejected" && r.rejection_reason && (
        <p className="rounded-md bg-danger-light px-3 py-2 text-danger">سبب الرفض: {r.rejection_reason}</p>
      )}

      {report && (
        <>
          {report.warnings.map((w) => (
            <p key={w} className="rounded-md bg-warn-light px-3 py-2 text-warn">{w}</p>
          ))}
          <div role="tablist" className="flex flex-wrap gap-1 border-b border-line">
            {tabs.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
                className={`-mb-px border-b-2 px-4 py-2 ${tab === t.key ? "border-primary font-semibold text-primary" : "border-transparent text-muted"}`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div role="tabpanel">
            {tab === "summary" && <Summary report={report} />}
            {tab === "claims" && <Claims report={report} onSource={setSource} />}
            {tab === "refs" && <References report={report} onSource={setSource} />}
            {tab === "similar" && <Similar report={report} />}
            {tab === "suggested" && <Suggested text={report.suggested_opinion_ar} />}
          </div>
        </>
      )}
      {source && <SourceDrawer chunkId={source} onClose={() => setSource(null)} />}
    </section>
  );
}

function ActionBar({ r }: { r: ReviewDetail }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const staff = me?.role === "admin" || me?.role === "reviewer";
  const actionable = ["needs_review", "no_information", "accepted"].includes(r.status);
  const act = useMutation({
    mutationFn: (p: { path: string; body: unknown }) => api(`/reviews/${r.id}/${p.path}`, json(p.body)),
    onSuccess: () => {
      setRejecting(false);
      qc.invalidateQueries({ queryKey: ["review", r.id] });
      qc.invalidateQueries({ queryKey: ["reviews"] });
    },
  });
  const pdf = useMutation({ mutationFn: () => downloadPdf(r.id) });
  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex flex-wrap gap-2">
        {(r.status === "accepted" || r.status === "approved") && (
          <button className="btn btn-primary" onClick={() => pdf.mutate()} disabled={pdf.isPending}>
            {pdf.isPending ? "جارٍ تجهيز الملف…" : "تنزيل PDF"}
          </button>
        )}
        {staff && actionable && (
          <>
            <button
              className="btn btn-primary"
              disabled={act.isPending}
              onClick={() => window.confirm("اعتماد الرأي كما هو؟") && act.mutate({ path: "approve", body: {} })}
            >
              اعتماد
            </button>
            <button className="btn btn-ghost" onClick={() => nav(`/reviews/${r.id}/edit`)}>تعديل واعتماد</button>
            <button className="btn btn-ghost" onClick={() => setRejecting(!rejecting)}>رفض</button>
          </>
        )}
      </div>
      {rejecting && (
        <form
          className="flex w-full max-w-md gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            act.mutate({ path: "reject", body: { reason } });
          }}
        >
          <input className="input" placeholder="سبب الرفض" value={reason} onChange={(e) => setReason(e.target.value)} required minLength={3} autoFocus />
          <button className="btn btn-ghost text-danger" disabled={act.isPending}>تأكيد الرفض</button>
        </form>
      )}
      <ErrorNote error={act.error ?? pdf.error} />
    </div>
  );
}

function Summary({ report }: { report: Report }) {
  const counts = report.claims.reduce<Record<string, number>>((acc, c) => {
    if (c.verdict) acc[c.verdict] = (acc[c.verdict] ?? 0) + 1;
    return acc;
  }, {});
  return (
    <div className="card space-y-4 p-5">
      <p className="leading-8">{report.message_ar ?? report.summary_ar}</p>
      <div className="flex flex-wrap gap-2">
        {Object.entries(counts).map(([v, n]) => <Chip key={v} tone={v}>{VERDICT_AR[v]}: {n}</Chip>)}
      </div>
      {report.dropped_evidence_count > 0 && (
        <p className="text-xs text-muted">استُبعد {report.dropped_evidence_count} دليل لم يتطابق مع نص المصدر.</p>
      )}
    </div>
  );
}

function Claims({ report, onSource }: { report: Report; onSource: (id: string) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="card divide-y divide-line">
      {report.claims.map((c) => (
        <div key={c.id} className="p-4">
          <button className="flex w-full items-start gap-3 text-start" aria-expanded={open === c.id} onClick={() => setOpen(open === c.id ? null : c.id)}>
            <span className="text-sm text-muted">{c.id}</span>
            <span className="flex-1">{c.text_ar}</span>
            <span className="text-xs text-muted">{CLAIM_TYPE_AR[c.type]}</span>
            {c.verdict ? <Chip tone={c.verdict}>{VERDICT_AR[c.verdict]}</Chip> : <Chip tone="none">غير مُقيَّم</Chip>}
            <span className="text-xs text-muted">{c.evidence.length} دليل</span>
          </button>
          {open === c.id && (
            <div className="mt-3 space-y-2 ps-8">
              {c.reasoning_ar && <p className="text-sm text-muted">{c.reasoning_ar}</p>}
              {c.evidence.map((e) => {
                const p = report.passages[e.pid];
                return (
                  <blockquote key={e.pid + e.stance} className="rounded-md border-s-4 border-accent bg-bg p-3 text-sm">
                    <div className="mb-1 flex flex-wrap gap-2 text-xs">
                      <Chip tone={e.stance === "supports" ? "supported" : e.stance === "contradicts" ? "contradicted" : "insufficient"}>
                        {e.stance === "supports" ? "مؤيد" : e.stance === "contradicts" ? "معارض" : "سياق"}
                      </Chip>
                      {p && <span className="text-muted">[{e.pid}] {citation(p)}</span>}
                      {e.blocking && <Chip tone="contradicted">تعارض مانع</Chip>}
                      {e.note && <span className="text-warn">{e.note}</span>}
                    </div>
                    «{e.quote_ar}»
                    <button className="ms-2 text-primary underline" onClick={() => onSource(e.chunk_id)}>عرض النص الكامل</button>
                  </blockquote>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function RefCard({ r, onSource }: { r: Reference; onSource: (id: string) => void }) {
  return (
    <article className="card space-y-2 p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold">{citation(r)}</span>
        <Chip tone={r.status === "repealed" ? "contradicted" : "insufficient"}>{SOURCE_STATUS_AR[r.status] ?? r.status}</Chip>
        {r.blocking && <Chip tone="contradicted">تعارض مانع</Chip>}
      </div>
      {r.note && <p className="text-xs text-warn">{r.note}</p>}
      <p className="text-sm leading-7">«{r.quote_ar}»</p>
      <button className="text-sm text-primary underline" onClick={() => onSource(r.chunk_id)}>عرض النص الكامل</button>
    </article>
  );
}

function References({ report, onSource }: { report: Report; onSource: (id: string) => void }) {
  const col = (title: string, refs: Reference[]) => (
    <div className="space-y-3">
      <h2 className="font-bold">{title} ({refs.length})</h2>
      {refs.length === 0 && <p className="text-sm text-muted">لا توجد مراجع.</p>}
      {refs.map((r) => <RefCard key={r.pid} r={r} onSource={onSource} />)}
    </div>
  );
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {col("مؤيدة", report.references.supporting)}
      {col("معارضة", report.references.contradicting)}
    </div>
  );
}

function Similar({ report }: { report: Report }) {
  if (report.similar_opinions.length === 0) return <p className="text-muted">لا توجد آراء مشابهة في المصادر المتاحة.</p>;
  return (
    <div className="space-y-3">
      {report.similar_opinions.map((s) => (
        <article key={s.document_id} className="card p-4">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{s.title_ar}</span>
            <span className="text-xs text-muted">{DOC_TYPE_AR[s.doc_type]}</span>
          </div>
          <p className="mt-1 text-sm text-muted">{s.excerpt}…</p>
        </article>
      ))}
    </div>
  );
}

function Suggested({ text }: { text: string }) {
  return (
    <div className="card p-5">
      <p className="whitespace-pre-wrap leading-8">{text || "لم يُقترح رأي بديل."}</p>
    </div>
  );
}

function SourceDrawer({ chunkId, onClose }: { chunkId: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["source", chunkId], queryFn: () => api<SourceChunk>(`/sources/chunks/${chunkId}`) });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const d = q.data;
  return (
    <div className="fixed inset-0 z-10 flex" role="dialog" aria-modal="true" aria-label="النص الكامل للمصدر">
      <button className="flex-1 bg-ink/30" aria-label="إغلاق" onClick={onClose} />
      <aside className="h-full w-full max-w-xl overflow-y-auto bg-surface p-6 shadow-xl">
        <button className="btn btn-ghost mb-4 py-1" onClick={onClose} autoFocus>إغلاق</button>
        <ErrorNote error={q.error} />
        {d && (
          <div className="space-y-3">
            <h2 className="text-lg font-bold">{d.document.title_ar}</h2>
            <p className="text-sm text-muted">
              {DOC_TYPE_AR[d.document.doc_type]} · {SOURCE_STATUS_AR[d.document.status]}
              {d.unit.path?.length ? ` · ${d.unit.path.join(" — ")}` : ""}
            </p>
            <h3 className="font-semibold">{d.unit.article_label}</h3>
            <p className="whitespace-pre-wrap leading-8">
              {highlight(d.unit.text, d.chunk.text)}
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}

function highlight(full: string, part: string) {
  const i = full.indexOf(part);
  if (i < 0) return full;
  return (
    <>
      {full.slice(0, i)}
      <mark className="bg-primary-light">{part}</mark>
      {full.slice(i + part.length)}
    </>
  );
}
