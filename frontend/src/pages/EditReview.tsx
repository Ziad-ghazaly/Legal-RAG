import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, json, type ReviewDetail } from "../api";
import { ErrorNote } from "../components/ui";
import { wordDiff } from "../diff";
import { SOURCE_STATUS_AR, citation } from "../labels";

export default function EditReview() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["review", id], queryFn: () => api<ReviewDetail>(`/reviews/${id}`) });
  const [text, setText] = useState("");
  const [showDiff, setShowDiff] = useState(false);
  const [savedAs, setSavedAs] = useState<number | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const r = q.data;
  const aiText = r?.report?.suggested_opinion_ar || r?.opinion_text || "";

  useEffect(() => {
    if (r && !text) setText(r.final_text !== r.opinion_text ? r.final_text : aiText);
  }, [r, aiText, text]);

  const save = useMutation({
    mutationFn: () => api<{ version: number }>(`/reviews/${id}/versions`, json({ text })),
    onSuccess: (v) => setSavedAs(v.version),
  });
  const approve = useMutation({
    mutationFn: async () => {
      const v = savedAs ?? (await api<{ version: number }>(`/reviews/${id}/versions`, json({ text }))).version;
      return api(`/reviews/${id}/approve`, json({ version: v }));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review", id] });
      qc.invalidateQueries({ queryKey: ["reviews"] });
      nav(`/reviews/${id}`);
    },
  });

  function insert(pid: string) {
    const el = area.current;
    const at = el ? el.selectionStart : text.length;
    setText(`${text.slice(0, at)} [${pid}]${text.slice(at)}`);
    setSavedAs(null);
    requestAnimationFrame(() => el?.focus());
  }

  if (q.isLoading) return <p className="text-muted">جارٍ التحميل…</p>;
  if (!r) return <ErrorNote error={q.error} />;
  const passages = Object.values(r.report?.passages ?? {});

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link to={`/reviews/${id}`} className="text-primary hover:underline">← العودة إلى النتيجة</Link>
        <h1 className="text-xl font-bold">تعديل واعتماد الرأي</h1>
        <div className="ms-auto flex gap-2">
          <button className="btn btn-ghost" onClick={() => setShowDiff(!showDiff)}>
            {showDiff ? "إخفاء الفروقات" : "عرض الفروقات"}
          </button>
          <button className="btn btn-ghost" disabled={save.isPending || text.trim().length < 20} onClick={() => save.mutate()}>
            حفظ مسودة
          </button>
          <button
            className="btn btn-primary"
            disabled={approve.isPending || text.trim().length < 20}
            onClick={() => window.confirm("اعتماد النص المعدّل؟ لا يمكن التراجع عن الاعتماد.") && approve.mutate()}
          >
            اعتماد
          </button>
        </div>
      </div>
      {savedAs && <p className="text-sm text-muted">حُفظت المسودة كنسخة رقم {savedAs}.</p>}
      <ErrorNote error={save.error ?? approve.error} />
      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-3">
          <textarea
            ref={area}
            className="input min-h-[28rem] leading-8"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setSavedAs(null);
            }}
            aria-label="نص الرأي المعدل"
          />
          {showDiff && (
            <div className="card p-4 leading-8" aria-label="الفروقات مقارنة بنص الذكاء الاصطناعي">
              {wordDiff(aiText, text).map((p, i) => (
                <span
                  key={i}
                  className={
                    p.type === "add" ? "bg-primary-light text-primary" : p.type === "del" ? "bg-danger-light text-danger line-through" : ""
                  }
                >
                  {p.text}{" "}
                </span>
              ))}
            </div>
          )}
        </div>
        <aside className="card h-fit max-h-[36rem] space-y-3 overflow-y-auto p-4">
          <h2 className="font-bold">مراجع المراجعة</h2>
          {passages.length === 0 && <p className="text-sm text-muted">لا توجد مراجع.</p>}
          {passages.map((p) => (
            <div key={p.pid} className="space-y-1 border-b border-line pb-2 text-sm last:border-0">
              <div className="font-semibold">[{p.pid}] {citation(p)}</div>
              <div className="text-xs text-muted">{SOURCE_STATUS_AR[p.status] ?? p.status}</div>
              <p className="line-clamp-3 text-muted">{p.text}</p>
              <button className="text-primary underline" onClick={() => insert(p.pid)}>إدراج استشهاد</button>
            </div>
          ))}
        </aside>
      </div>
    </section>
  );
}
