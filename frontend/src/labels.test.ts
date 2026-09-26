import { describe, expect, it } from "vitest";
import { lawLink, noteBadges, opinionMarks } from "./labels";

describe("noteBadges", () => {
  it("derives badges from status and the compilation's footnotes", () => {
    expect(noteBadges("in_force", ["معدلة بالقانون رقم 70 لسنة 1979"]).map((b) => b.label)).toEqual(["معدّلة"]);
    expect(noteBadges("in_force", ["مضافة وفق القانون رقم 5 لسنة 2020"]).map((b) => b.label)).toEqual(["مضافة"]);
    expect(noteBadges("repealed", ["ملغاة بموجب القانون رقم 3 لسنة 1983"]).map((b) => b.label)).toEqual(["ملغاة"]);
    expect(noteBadges("suspended", ["تم وقف العمل بالمادة"]).map((b) => b.label)).toEqual(["موقوفة"]);
    expect(noteBadges("in_force", [])).toEqual([]);
  });

  it("builds deep links that survive slashes in unit ids", () => {
    expect(lawLink("kw-law-6-2010", "kw-law-6-2010/a41")).toBe("/laws/kw-law-6-2010#kw-law-6-2010%2Fa41");
  });
});

describe("opinionMarks", () => {
  it("colours a shared sentence by its most severe claim", () => {
    const marks = opinionMarks([
      { id: "C6", verdict: "supported", span: [455, 590] },
      { id: "C7", verdict: "contradicted", span: [455, 590] },
      { id: "C1", verdict: "supported", span: [257, 454] },
      { id: "C3", verdict: null, span: [81, 239] },
      { id: "C4", verdict: "supported", span: null },
    ]);
    expect(marks).toEqual([
      { id: "C1", verdict: "supported", start: 257, end: 454 },
      { id: "C7", verdict: "contradicted", start: 455, end: 590 },
    ]);
  });
});
