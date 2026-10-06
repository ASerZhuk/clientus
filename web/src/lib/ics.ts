import type { ClientBooking } from "./types";

const stamp = (minute: number) => new Date(minute * 60_000).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
const esc = (s: string) => s.replace(/\\/g, "\\\\").replace(/;/g, "\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");

/** Built in the browser from the booking the client already holds: nothing is sent anywhere. */
export function buildIcs(b: ClientBooking, studio: { name: string; address: string; phone: string; slug: string }): string {
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//clientall//RU",
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

const gstamp = (minute: number) => stamp(minute);
const isApple = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  || (/macintosh/i.test(navigator.userAgent) && /safari/i.test(navigator.userAgent) && !/chrome|chromium|edg|firefox|yabrowser/i.test(navigator.userAgent));

/**
 * Add the booking to the phone's calendar without a downloaded file:
 * Apple devices open our text/calendar link and Safari shows its own "Add to Calendar" sheet;
 * everything else opens Google Calendar with the event already filled in (one tap "Save").
 */
export function addToCalendar(b: ClientBooking, studio: Parameters<typeof buildIcs>[1], api: string): void {
  if (isApple() && b.calendar_sig) {
    window.location.href = `${api}/calendar/${b.id}.ics?sig=${b.calendar_sig}`;
    return;
  }
  const q = new URLSearchParams({
    action: "TEMPLATE",
    text: `${b.service_name} — ${studio.name}`,
    dates: `${gstamp(b.start_min)}/${gstamp(b.end_min)}`,
    details: [b.car ? `Автомобиль: ${b.car}` : "", studio.phone ? `Телефон: ${studio.phone}` : ""].filter(Boolean).join("\n"),
    location: studio.address,
  });
  const w = window.open(`https://calendar.google.com/calendar/render?${q}`, "_blank", "noopener");
  if (!w) downloadIcs(b, studio); // pop-up blocked: fall back to the file
}
