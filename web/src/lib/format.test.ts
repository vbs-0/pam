import { describe, expect, it } from "vitest";
import { inrSigned, monthName, shiftMonth, toPaise } from "./format";

describe("money", () => {
  it("groups the Indian way", () => expect(inrSigned(12345678)).toBe("₹1,23,456.78"));
  it("signs negatives", () => expect(inrSigned(-5000)).toBe("−₹50.00"));
  it("parses typed amounts to paise", () => {
    expect(toPaise("1,250.5")).toBe(125050);
    expect(toPaise("₹ 99")).toBe(9900);
    expect(toPaise("12.345")).toBeNull();
    expect(toPaise("-5")).toBeNull();
    expect(toPaise("")).toBeNull();
  });
});

describe("months", () => {
  it("rolls over years", () => {
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
  });
  it("names them", () => expect(monthName("2026-03")).toBe("March 2026"));
});

describe("large amounts", () => {
  it("groups crore-scale amounts the Indian way", () => {            // U03
    expect(inrSigned(1_000_000_000)).toBe("₹1,00,00,000.00");
    expect(inrSigned(-12_345_678_900)).toBe("−₹12,34,56,789.00");
  });
});
