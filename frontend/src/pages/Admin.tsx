import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, json, type Collection, type Job, type UserRow } from "../api";
import { ErrorNote } from "../components/ui";
import { JOB_STATUS_AR, ROLE_AR, formatDate } from "../labels";

const SECTIONS = [
  { key: "ingestion", label: "استيراد المصادر" },
  { key: "collections", label: "المجموعات" },
  { key: "users", label: "المستخدمون والصلاحيات" },
] as const;

export default function Admin() {
  const [section, setSection] = useState<(typeof SECTIONS)[number]["key"]>("ingestion");
  const collections = useQuery({ queryKey: ["collections"], queryFn: () => api<Collection[]>("/admin/collections") });
  return (
    <section className="space-y-5">
      <h1 className="text-xl font-bold">الإدارة</h1>
      <div role="tablist" className="flex gap-1 border-b border-line">
        {SECTIONS.map((s) => (
          <button key={s.key} role="tab" aria-selected={section === s.key} onClick={() => setSection(s.key)}
            className={`-mb-px border-b-2 px-4 py-2 ${section === s.key ? "border-primary font-semibold text-primary" : "border-transparent text-muted"}`}>
            {s.label}
          </button>
        ))}
      </div>
      {section === "ingestion" && <Ingestion collections={collections.data ?? []} />}
      {section === "collections" && <Collections collections={collections.data ?? []} />}
      {section === "users" && <Users collections={collections.data ?? []} />}
    </section>
  );
}

function Ingestion({ collections }: { collections: Collection[] }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [coll, setColl] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api<Job[]>("/admin/ingestion/jobs"),
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === "pending" || j.status === "processing") ? 3000 : false),
  });
  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("file", file as File);
      form.append("collection_id", coll);
      return api<{ job_id: string }>("/admin/ingestion/jobs", { method: "POST", body: form });
    },
    onSuccess: () => {
      setFile(null);
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  return (
    <div className="space-y-4">
      <form className="card flex flex-wrap items-end gap-4 p-5" onSubmit={(e: FormEvent) => { e.preventDefault(); upload.mutate(); }}>
        <div>
          <label className="label" htmlFor="jf">ملف JSONL</label>
          <input id="jf" type="file" accept=".jsonl,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        <div className="w-56">
          <label className="label" htmlFor="jc">المجموعة</label>
          <select id="jc" className="input" value={coll} onChange={(e) => setColl(e.target.value)} required>
            <option value="">اختر مجموعة</option>
            {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <button className="btn btn-primary" disabled={!file || !coll || upload.isPending}>رفع وبدء الاستيراد</button>
        <ErrorNote error={upload.error} />
      </form>
      <div className="card divide-y divide-line">
        {jobs.data?.map((j) => {
          const stats = (j.stats ?? {}) as { chunks?: number; units?: number; dropped_count?: number; row_errors?: { line: number; error: string }[]; doc_errors?: { doc_id: string; error: string }[]; error?: string };
          return (
            <div key={j.id} className="p-4">
              <button className="flex w-full flex-wrap items-center gap-4 text-start" onClick={() => setOpen(open === j.id ? null : j.id)} aria-expanded={open === j.id}>
                <span className="font-medium">{JOB_STATUS_AR[j.status] ?? j.status}</span>
                <span className="text-sm text-muted">{formatDate(j.created_at)}</span>
                <span className="text-sm">وثائق: {j.doc_count}</span>
                <span className="text-sm">مقاطع: {stats.chunks ?? "—"}</span>
                <span className={`text-sm ${j.error_count ? "text-danger" : "text-muted"}`}>أخطاء: {j.error_count}</span>
                <span className="text-sm text-muted">مستبعدة: {stats.dropped_count ?? 0}</span>
              </button>
              {open === j.id && (
                <div className="mt-3 space-y-1 text-sm">
                  {stats.error && <p className="text-danger">{stats.error}</p>}
                  {stats.row_errors?.map((e) => <p key={e.line} className="text-danger">السطر {e.line}: {e.error}</p>)}
                  {stats.doc_errors?.map((e) => <p key={e.doc_id} className="text-danger">{e.doc_id}: {e.error}</p>)}
                  {!stats.error && !stats.row_errors?.length && !stats.doc_errors?.length && <p className="text-muted">لا توجد أخطاء.</p>}
                </div>
              )}
            </div>
          );
        })}
        {jobs.data?.length === 0 && <p className="p-6 text-center text-muted">لا توجد مهام استيراد.</p>}
      </div>
    </div>
  );
}

function Collections({ collections }: { collections: Collection[] }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api<Collection>("/admin/collections", json({ name })),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["collections"] });
    },
  });
  return (
    <div className="space-y-4">
      <form className="card flex items-end gap-4 p-5" onSubmit={(e: FormEvent) => { e.preventDefault(); create.mutate(); }}>
        <div className="w-72">
          <label className="label" htmlFor="cn">اسم المجموعة</label>
          <input id="cn" className="input" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <button className="btn btn-primary" disabled={!name || create.isPending}>إضافة</button>
        <ErrorNote error={create.error} />
      </form>
      <ul className="card divide-y divide-line">
        {collections.map((c) => (
          <li key={c.id} className="flex gap-4 p-3"><span className="text-muted" dir="ltr">#{c.id}</span><span>{c.name}</span></li>
        ))}
      </ul>
    </div>
  );
}

function Users({ collections }: { collections: Collection[] }) {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<UserRow[]>("/admin/users") });
  const [form, setForm] = useState({ username: "", password: "", role: "user" });
  const create = useMutation({
    mutationFn: () => api<UserRow>("/admin/users", json({ ...form, collection_ids: [] })),
    onSuccess: () => {
      setForm({ username: "", password: "", role: "user" });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
  const setAcl = useMutation({
    mutationFn: (v: { id: string; ids: number[] }) => api<UserRow>(`/admin/users/${v.id}/collections`, json({ collection_ids: v.ids }, "PUT")),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
  return (
    <div className="space-y-4">
      <form className="card grid gap-4 p-5 sm:grid-cols-4" onSubmit={(e: FormEvent) => { e.preventDefault(); create.mutate(); }}>
        <div><label className="label" htmlFor="un">اسم المستخدم</label><input id="un" className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required /></div>
        <div><label className="label" htmlFor="pw">كلمة المرور</label><input id="pw" type="password" minLength={8} className="input" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></div>
        <div><label className="label" htmlFor="rl">الدور</label>
          <select id="rl" className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {Object.entries(ROLE_AR).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="flex items-end"><button className="btn btn-primary" disabled={create.isPending}>إضافة مستخدم</button></div>
        <div className="sm:col-span-4"><ErrorNote error={create.error ?? setAcl.error} /></div>
      </form>
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead className="bg-bg text-sm text-muted"><tr><th className="p-3 text-start">المستخدم</th><th className="p-3 text-start">الدور</th><th className="p-3 text-start">المجموعات المسموح بها</th></tr></thead>
          <tbody>
            {users.data?.map((u) => (
              <tr key={u.id} className="border-t border-line">
                <td className="p-3">{u.username}</td>
                <td className="p-3">{ROLE_AR[u.role]}</td>
                <td className="p-3">
                  {u.role === "admin" ? <span className="text-muted">كل المجموعات</span> : (
                    <div className="flex flex-wrap gap-3">
                      {collections.map((c) => (
                        <label key={c.id} className="flex items-center gap-1 text-sm">
                          <input type="checkbox" checked={u.collection_ids.includes(c.id)}
                            onChange={(e) => setAcl.mutate({ id: u.id, ids: e.target.checked ? [...u.collection_ids, c.id] : u.collection_ids.filter((x) => x !== c.id) })} />
                          {c.name}
                        </label>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
