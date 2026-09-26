import { describe, expect, it } from "vitest";
import { wordDiff } from "./diff";

describe("wordDiff", () => {
  it("marks removed and added words and keeps the rest", () => {
    const d = wordDiff("فترة التجربة لا تتجاوز ستة أشهر", "فترة التجربة لا تتجاوز ثلاثة أشهر [P3]");
    expect(d).toEqual([
      { type: "same", text: "فترة التجربة لا تتجاوز" },
      { type: "del", text: "ستة" },
      { type: "add", text: "ثلاثة" },
      { type: "same", text: "أشهر" },
      { type: "add", text: "[P3]" },
    ]);
  });

  it("handles empty sides", () => {
    expect(wordDiff("", "نص جديد")).toEqual([{ type: "add", text: "نص جديد" }]);
    expect(wordDiff("نص قديم", "")).toEqual([{ type: "del", text: "نص قديم" }]);
  });
});
