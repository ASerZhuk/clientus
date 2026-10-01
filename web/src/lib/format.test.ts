import { describe, expect, it } from "vitest";
import { dateKeyOf, formatDuration, formatMoney, localToMinute, plural, shiftDateKey, timeOf, toMinor } from "./format";

describe("money", () => {
  it("formats minor units with the studio currency", () => {
    expect(formatMoney(350000, "RUB")).toBe("3 500 ₽");
    expect(formatMoney(1050, "USD")).toContain("10,5");
    expect(toMinor(12.34)).toBe(1234);
    expect(toMinor(0.1 + 0.2)).toBe(30);
  });
});

describe("plural and duration", () => {
  it("uses Russian plural forms", () => {
    expect(plural(1, ["час", "часа", "часов"])).toBe("1 час");
    expect(plural(3, ["час", "часа", "часов"])).toBe("3 часа");
    expect(plural(11, ["час", "часа", "часов"])).toBe("11 часов");
    expect(plural(22, ["день", "дня", "дней"])).toBe("22 дня");
  });
  it("shows multi-day work in days", () => {
    expect(formatDuration(2880)).toBe("2 дня");
    expect(formatDuration(90)).toBe("1 час 30 мин");
    expect(formatDuration(45)).toBe("45 мин");
  });
});

describe("studio timezone", () => {
  it("converts wall-clock time in the studio zone to UTC minutes and back", () => {
    const m = localToMinute("2030-01-09", "09:00", "Asia/Yekaterinburg");
    expect(new Date(m * 60000).toISOString()).toBe("2030-01-09T04:00:00.000Z");
    expect(timeOf(m, "Asia/Yekaterinburg")).toBe("09:00");
    expect(timeOf(m, "Europe/Moscow")).toBe("07:00");
  });
  it("assigns the calendar day by the studio zone, not the browser zone", () => {
    const lateEvening = localToMinute("2030-01-09", "23:30", "Asia/Yekaterinburg"); // still Jan 9 there, Jan 9 18:30 UTC
    expect(dateKeyOf(lateEvening, "Asia/Yekaterinburg")).toBe("2030-01-09");
    expect(dateKeyOf(lateEvening, "Pacific/Auckland")).toBe("2030-01-10");
  });
  it("handles the DST gap: 23-hour local day keeps wall-clock times right", () => {
    const before = localToMinute("2030-03-31", "01:00", "Europe/Berlin");
    const after = localToMinute("2030-03-31", "03:00", "Europe/Berlin");
    expect(after - before).toBe(60);
  });
  it("shifts date keys across month ends", () => {
    expect(shiftDateKey("2030-01-31", 1)).toBe("2030-02-01");
    expect(shiftDateKey("2030-03-01", -1)).toBe("2030-02-28");
  });
});
