import { describe, expect, it } from "vitest";
import { lawLink, noteBadges } from "./labels";

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
