import { parseSSE } from "./sse";

const BASE = "/api/v1";
const KEY = "legal-rag-v3.tokens";

type Tokens = { access_token: string; refresh_token: string; role: string };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function getTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}

export function setTokens(t: Tokens | null): void {
  try {
    if (t) localStorage.setItem(KEY, JSON.stringify(t));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: session-only login */
  }
}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* not JSON */
  }
  return "حدث خطأ غير متوقع.";
}

let inflight: Promise<boolean> | null = null;

/** Single-flight: concurrent 401s share one refresh (the backend rotates refresh tokens). */
function refresh(): Promise<boolean> {
  inflight ??= doRefresh().finally(() => {
    inflight = null;
  });
  return inflight;
}

async function doRefresh(): Promise<boolean> {
  const t = getTokens();
  if (!t) return false;
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: t.refresh_token }),
  });
  if (!res.ok) {
    setTokens(null);
    return false;
  }
  setTokens(await res.json());
  return true;
}

async function raw(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const t = getTokens();
  const headers = new Headers(init.headers);
  if (t) headers.set("Authorization", `Bearer ${t.access_token}`);
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401 && retry && (await refresh())) return raw(path, init, false);
  if (res.status === 401) {
    setTokens(null);
    window.dispatchEvent(new Event("auth:logout"));
  }
  return res;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await raw(path, init);
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return (await res.json()) as T;
}

export function json(body: unknown, method = "POST"): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export async function login(username: string, password: string): Promise<Tokens> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    body: new URLSearchParams({ username, password }),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  const tokens = (await res.json()) as Tokens;
  setTokens(tokens);
  return tokens;
}

export async function logout(): Promise<void> {
  const t = getTokens();
  setTokens(null);
  if (t) await fetch(`${BASE}/auth/logout`, json({ refresh_token: t.refresh_token })).catch(() => {});
}

/** Stream review progress events until the server closes the stream. */
export async function streamEvents(
  reviewId: string,
  onEvent: (e: { stage: string; [k: string]: unknown }) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await raw(`/reviews/${reviewId}/events`, { signal });
  if (!res.ok || !res.body) return;
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    const parsed = parseSSE(buffer + value);
    buffer = parsed.rest;
    parsed.events.forEach((e) => onEvent(e as { stage: string }));
  }
}

/** Download the approved opinion as PDF (authenticated fetch → blob → save). */
export async function downloadPdf(reviewId: string): Promise<void> {
  const res = await raw(`/reviews/${reviewId}/export.pdf`);
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `رأي-قانوني-${reviewId.slice(0, 8)}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── types (mirror the backend payloads) ─────────────────────────────────────

export type Me = { id: string; username: string; role: "admin" | "reviewer" | "user"; is_active: boolean };
export type ReviewSummary = {
  id: string;
  title: string | null;
  status: string;
  score: number | null;
  owner: string;
  created_at: string;
};
export type Evidence = {
  pid: string;
  chunk_id: string;
  stance: "supports" | "contradicts" | "context";
  quote_ar: string;
  note: string | null;
  blocking: boolean;
  resolved_conflict: boolean;
};
export type ClaimOut = {
  id: string;
  text_ar: string;
  type: string;
  materiality: string;
  verdict: string | null;
  reasoning_ar: string;
  weight: number;
  evidence: Evidence[];
};
export type PassageOut = {
  pid: string;
  chunk_id: string;
  unit_id: string;
  title_ar: string;
  number: string | null;
  year: number | null;
  article_label: string | null;
  doc_type: string;
  status: string;
  text: string;
};
export type Reference = {
  pid: string;
  chunk_id: string;
  title_ar: string;
  number: string | null;
  year: number | null;
  article_label: string | null;
  status: string;
  doc_type: string;
  quote_ar: string;
  blocking: boolean;
  note: string | null;
};
export type Report = {
  status: string;
  score: number | null;
  message_ar: string | null;
  summary_ar: string;
  suggested_opinion_ar: string;
  claims: ClaimOut[];
  passages: Record<string, PassageOut>;
  references: { supporting: Reference[]; contradicting: Reference[] };
  similar_opinions: { document_id: string; title_ar: string; doc_type: string; score: number; excerpt: string }[];
  dropped_evidence_count: number;
  warnings: string[];
};
export type ReviewDetail = {
  id: string;
  title: string | null;
  status: string;
  score: number | null;
  question: string | null;
  opinion_text: string;
  as_of_date: string | null;
  error_ar: string | null;
  created_at: string;
  report: Report | null;
  approvals: { version: number; decision: string }[];
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  final_text: string;
};
export type SourceChunk = {
  chunk: { id: string; text: string; context_header: string; status: string };
  unit: { article_label: string | null; path: string[] | null; text: string; valid_from: string | null; valid_to: string | null };
  document: { title_ar: string; doc_type: string; number: string | null; year: number | null; status: string };
};
export type Collection = { id: number; name: string; description: string | null };
export type UserRow = { id: string; username: string; role: string; is_active: boolean; collection_ids: number[] };
export type Job = {
  id: string;
  status: string;
  collection_id: number | null;
  doc_count: number;
  error_count: number;
  stats: Record<string, unknown> | null;
  created_at: string;
};
