import type { ClientBooking } from "./types";

const stamp = (minute: number) => new Date(minute * 60_000).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
const esc = (s: string) => s.replace(/\\/g, "\\\\").replace(/;/g, "\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");

/** Built in the browser from the booking the client already holds: nothing is sent anywhere. */
export function buildIcs(b: ClientBooking, studio: { name: string; address: string; phone: string; slug: string }): string {
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Clientus//RU",
    "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:booking-${b.id}@${studio.slug}`,
    `DTSTAMP:${stamp(Math.floor(Date.now() / 60_000))}`,
    `DTSTART:${stamp(b.start_min)}`,
    `DTEND:${stamp(b.end_min)}`,
    `SUMMARY:${esc(`${b.service_name} — ${studio.name}`)}`,
    `LOCATION:${esc(studio.address)}`,
    `DESCRIPTION:${esc(`Автомобиль: ${b.car}${studio.phone ? `\nТелефон студии: ${studio.phone}` : ""}`)}`,
    "BEGIN:VALARM",
    "TRIGGER:-P1D",
    "ACTION:DISPLAY",
    `DESCRIPTION:${esc(`Завтра: ${b.service_name}`)}`,
    "END:VALARM",
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
}

export function downloadIcs(b: ClientBooking, studio: Parameters<typeof buildIcs>[1]): void {
  const blob = new Blob([buildIcs(b, studio)], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `zapis-${b.id}.ics`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
