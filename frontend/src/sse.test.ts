import { describe, expect, it } from "vitest";
import { parseSSE } from "./sse";

describe("parseSSE", () => {
  it("splits complete frames and keeps the partial tail", () => {
    const { events, rest } = parseSSE('data: {"stage":"parsing"}\n\ndata: {"stage":"verifying"}\n\ndata: {"sta');
    expect(events).toEqual([{ stage: "parsing" }, { stage: "verifying" }]);
    expect(rest).toBe('data: {"sta');
  });

  it("joins multi-line data and ignores comments and blank frames", () => {
    const { events } = parseSSE(': ping\n\ndata: {"a":\ndata: 1}\n\n');
    expect(events).toEqual([{ a: 1 }]);
  });
});
