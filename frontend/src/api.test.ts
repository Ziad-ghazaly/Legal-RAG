import { beforeEach, describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => store.set(k, v),
  removeItem: (k: string) => store.delete(k),
});
vi.stubGlobal("window", new EventTarget());

const { api, getTokens, setTokens } = await import("./api");

describe("token refresh", () => {
  beforeEach(() => store.clear());

  it("concurrent 401s share one refresh and keep the user logged in", async () => {
    setTokens({ access_token: "old", refresh_token: "r1", role: "admin" });
    let refreshCalls = 0;
    vi.stubGlobal("fetch", async (url: string, init: RequestInit = {}) => {
      if (url.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        const body = JSON.parse(String(init.body));
        // backend rotates: the old refresh token works exactly once
        if (body.refresh_token !== "r1" || refreshCalls > 1) return new Response("{}", { status: 401 });
        await new Promise((r) => setTimeout(r, 10));
        return Response.json({ access_token: "new", refresh_token: "r2", role: "admin" });
      }
      const auth = new Headers(init.headers).get("Authorization");
      return auth === "Bearer new" ? Response.json({ ok: true }) : new Response("{}", { status: 401 });
    });

    const results = await Promise.all([api("/a"), api("/b"), api("/c")]);
    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
    expect(refreshCalls).toBe(1);
    expect(getTokens()?.refresh_token).toBe("r2");
  });
});
