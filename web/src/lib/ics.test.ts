import { describe, expect, it } from "vitest";
import { buildIcs } from "./ics";
import { onAccent } from "./theme";

describe("calendar export", () => {
  it("builds a valid one-event calendar with a 1-day alarm and escaped text", () => {
    const ics = buildIcs(
      { id: 7, status: "booked", service_name: "Мойка, премиум", price_minor: 1, start_min: 29841540, end_min: 29841660, car: "BMW; X5", plate: "", post_name: "П1", can_cancel: true, cancel_deadline_min: 0, cancel_before_hours: 24 },
      { name: "Студия", address: "ул. Тестовая, 1", phone: "+7 000", slug: "s1" },
    );
    expect(ics.startsWith("BEGIN:VCALENDAR\r\n")).toBe(true);
    expect(ics).toContain("UID:booking-7@s1");
    expect(ics).toMatch(/DTSTART:\d{8}T\d{6}Z/);
    expect(ics).toContain("SUMMARY:Мойка\\, премиум — Студия");
    expect(ics).toContain("BMW\; X5");
    expect(ics).toContain("TRIGGER:-P1D");
    expect(ics.trimEnd().endsWith("END:VCALENDAR")).toBe(true);
  });
});

describe("accent contrast", () => {
  it("picks a readable label colour for any accent", () => {
    expect(onAccent("#4690FF")).toBe("#000000");
    expect(onAccent("#0B1F5C")).toBe("#FFFFFF");
    expect(onAccent("#FFFFFF")).toBe("#000000");
  });
});
