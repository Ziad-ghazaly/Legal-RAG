import { useMutation } from "@tanstack/react-query";
import { useState, type DragEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote } from "../components/ui";

export default function NewReview() {
  const nav = useNavigate();
  const [question, setQuestion] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [asOf, setAsOf] = useState("");
  const [collections, setCollections] = useState("");
  const [drag, setDrag] = useState(false);

  const submit = useMutation({
    mutationFn: () => {
      const form = new FormData();
      if (file) form.append("file", file);
      else form.append("opinion_text", text);
      if (question.trim()) form.append("question", question);
      if (asOf) form.append("as_of_date", asOf);
      if (collections.trim()) form.append("collections", collections.replace(/\s/g, ""));
      return api<{ review_id: string }>("/reviews", { method: "POST", body: form });
    },
    onSuccess: (r) => nav(`/reviews/${r.review_id}`),
  });

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submit.mutate();
  }

  const ready = !!file || text.trim().length > 20;

  return (
    <form onSubmit={onSubmit} className="card mx-auto max-w-3xl space-y-5 p-6">
      <h1 className="text-xl font-bold">مراجعة جديدة</h1>
      <div>
        <label className="label" htmlFor="q">السؤال أو الوقائع (اختياري)</label>
        <textarea id="q" className="input min-h-20" value={question} onChange={(e) => setQuestion(e.target.value)} />
      </div>
      <div>
        <label className="label" htmlFor="t">نص الرأي القانوني</label>
        <textarea id="t" className="input min-h-56" value={text} disabled={!!file} placeholder="الصق نص الرأي هنا، أو أرفق ملفاً أدناه." onChange={(e) => setText(e.target.value)} />
      </div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        className={`rounded-lg border-2 border-dashed p-6 text-center ${drag ? "border-accent bg-primary-light" : "border-line"}`}
      >
        {file ? (
          <div className="flex items-center justify-center gap-3">
            <span className="font-medium">{file.name}</span>
            <button type="button" className="btn btn-ghost py-1" onClick={() => setFile(null)}>إزالة</button>
          </div>
        ) : (
          <label className="cursor-pointer text-muted">
            اسحب ملف PDF أو DOCX أو TXT هنا، أو <span className="text-primary underline">اختر ملفاً</span>
            <input type="file" accept=".pdf,.docx,.txt" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="d">التاريخ المرجعي</label>
          <input id="d" type="date" className="input" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          <p className="mt-1 text-xs text-muted">افتراضياً: تاريخ اليوم.</p>
        </div>
        <div>
          <label className="label" htmlFor="c">نطاق المجموعات (اختياري)</label>
          <input id="c" className="input" dir="ltr" placeholder="1,2" value={collections} onChange={(e) => setCollections(e.target.value)} />
          <p className="mt-1 text-xs text-muted">أرقام المجموعات مفصولة بفواصل؛ فارغ = كل المجموعات المسموح بها.</p>
        </div>
      </div>
      <ErrorNote error={submit.error} />
      <button className="btn btn-primary" disabled={!ready || submit.isPending}>
        {submit.isPending ? "جارٍ الإرسال…" : "بدء التحقق"}
      </button>
    </form>
  );
}
