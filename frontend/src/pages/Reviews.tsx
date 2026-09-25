import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type ReviewSummary } from "../api";
import { ErrorNote, StatusBadge } from "../components/ui";
import { STATUS_AR, formatDate } from "../labels";

const PAGE = 20;

export default function Reviews() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const q = useQuery({
    queryKey: ["reviews", status, page],
    queryFn: () =>
      api<{ items: ReviewSummary[]; total: number }>(
        `/reviews?limit=${PAGE}&offset=${page * PAGE}${status ? `&status=${status}` : ""}`,
      ),
    refetchInterval: (query) => (query.state.data?.items.some((r) => r.status === "processing") ? 5000 : false),
  });

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold">المراجعات</h1>
        <select className="input w-48" aria-label="تصفية حسب الحالة" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}>
          <option value="">كل الحالات</option>
          {Object.entries(STATUS_AR).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <Link to="/reviews/new" className="btn btn-primary ms-auto">مراجعة جديدة</Link>
      </div>
      <ErrorNote error={q.error} />
      <div className="card overflow-x-auto">
        <table className="w-full text-start">
          <thead className="bg-bg text-sm text-muted">
            <tr>
              <th className="p-3 text-start">الرأي</th>
              <th className="p-3 text-start">الحالة</th>
              <th className="p-3 text-start">النتيجة</th>
              <th className="p-3 text-start">التاريخ</th>
              <th className="p-3 text-start">المستخدم</th>
            </tr>
          </thead>
          <tbody>
            {q.data?.items.map((r) => (
              <tr key={r.id} className="border-t border-line hover:bg-bg">
                <td className="max-w-md truncate p-3">
                  <Link to={`/reviews/${r.id}`} className="font-medium text-primary hover:underline">{r.title || "رأي بدون عنوان"}</Link>
                </td>
                <td className="p-3"><StatusBadge status={r.status} /></td>
                <td className="p-3 font-semibold" dir="ltr">{r.score ?? "—"}</td>
                <td className="p-3 text-sm text-muted">{formatDate(r.created_at)}</td>
                <td className="p-3 text-sm">{r.owner}</td>
              </tr>
            ))}
            {q.data && q.data.items.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-muted">لا توجد مراجعات بعد.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {q.data && q.data.total > PAGE && (
        <div className="flex gap-2">
          <button className="btn btn-ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>السابق</button>
          <button className="btn btn-ghost" disabled={(page + 1) * PAGE >= q.data.total} onClick={() => setPage(page + 1)}>التالي</button>
        </div>
      )}
    </section>
  );
}
