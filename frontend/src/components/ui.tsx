import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ROLE_AR, STAGES, STATUS_AR } from "../labels";

const STATUS_STYLE: Record<string, string> = {
  accepted: "bg-primary text-white",
  approved: "bg-primary text-white",
  needs_review: "bg-warn-light text-warn",
  no_information: "bg-neutral-light text-muted",
  processing: "bg-primary-light text-primary",
  failed: "bg-danger-light text-danger",
  rejected: "bg-danger-light text-danger",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full px-3 py-0.5 text-sm font-semibold ${STATUS_STYLE[status] ?? "bg-neutral-light"}`}>
      {STATUS_AR[status] ?? status}
    </span>
  );
}

const VERDICT_STYLE: Record<string, string> = {
  supported: "bg-primary-light text-accent",
  partially_supported: "bg-primary-light text-accent",
  contradicted: "bg-danger-light text-danger",
  insufficient: "bg-neutral-light text-muted",
  warn: "bg-warn-light text-warn",
};

export function Chip({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-semibold ${VERDICT_STYLE[tone] ?? "bg-neutral-light text-muted"}`}>{children}</span>;
}

export function Stepper({ current, failed }: { current: string | null; failed?: boolean }) {
  const idx = STAGES.findIndex((s) => s.key === current);
  return (
    <ol className="flex flex-wrap gap-2" aria-label="مراحل التحقق">
      {STAGES.map((s, i) => {
        const state = i < idx ? "done" : i === idx ? (failed ? "failed" : "active") : "todo";
        const cls = {
          done: "bg-primary text-white",
          active: "bg-primary-light text-primary animate-pulse",
          failed: "bg-danger-light text-danger",
          todo: "bg-neutral-light text-muted",
        }[state];
        return (
          <li key={s.key} className={`rounded-md px-3 py-1 text-sm ${cls}`} aria-current={state === "active" ? "step" : undefined}>
            {i + 1}. {s.label}
          </li>
        );
      })}
    </ol>
  );
}

export function Layout() {
  const { me, logout } = useAuth();
  const nav = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1.5 ${isActive ? "bg-primary-light text-primary font-semibold" : "text-muted hover:text-ink"}`;
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <span className="text-lg font-bold text-primary">التحقق من الآراء القانونية</span>
          <nav className="flex gap-1">
            <NavLink to="/" end className={link}>المراجعات</NavLink>
            <NavLink to="/reviews/new" className={link}>مراجعة جديدة</NavLink>
            <NavLink to="/laws" className={link}>التشريعات</NavLink>
            {me?.role === "admin" && <NavLink to="/admin" className={link}>الإدارة</NavLink>}
          </nav>
          <div className="ms-auto flex items-center gap-3 text-sm text-muted">
            <span>{me?.username} · {ROLE_AR[me?.role ?? ""]}</span>
            <button className="btn btn-ghost py-1" onClick={async () => { await logout(); nav("/login"); }}>
              خروج
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return <p role="alert" className="rounded-md bg-danger-light px-3 py-2 text-danger">{error instanceof Error ? error.message : "حدث خطأ."}</p>;
}
