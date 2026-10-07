import { formatInTimeZone, fromZonedTime } from "date-fns-tz";
import { addDays, format as fnsFormat, parseISO } from "date-fns";
import { ru } from "date-fns/locale";

const CURRENCY: Record<string, string> = { RUB: "₽", USD: "$", EUR: "€", KZT: "₸", BYN: "Br", UAH: "₴" };

export function formatMoney(minor: number, currency = "RUB"): string {
  const major = minor / 100;
  const text = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: minor % 100 ? 2 : 0 }).format(major);
  return `${text}\u00a0${CURRENCY[currency] ?? currency}`;
}

/** A service price: 0 means a free visit (inspection, consultation), shown as such rather than "0 ₽". */
export function formatPrice(minor: number, currency = "RUB"): string {
  return minor === 0 ? "Бесплатно" : formatMoney(minor, currency);
}

/** minor units <-> the number a person types (major units) */
export const toMinor = (major: number) => Math.round(major * 100);
export const toMajor = (minor: number) => minor / 100;

export function plural(n: number, forms: [string, string, string]): string {
  const n10 = n % 10;
  const n100 = n % 100;
  const form = n10 === 1 && n100 !== 11 ? forms[0] : n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14) ? forms[1] : forms[2];
  return `${n} ${form}`;
}

export function formatDuration(minutes: number): string {
  if (minutes >= 1440 && minutes % 1440 === 0) return plural(minutes / 1440, ["день", "дня", "дней"]);
  if (minutes >= 60) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return plural(h, ["час", "часа", "часов"]) + (m ? ` ${m} мин` : "");
  }
  return `${minutes} мин`;
}

/** Compact form used in price lists: "2 ч", "1 ч 30 мин", "2 д". */
export function formatDurationShort(minutes: number): string {
  if (minutes >= 1440 && minutes % 1440 === 0) return `${minutes / 1440} д`;
  if (minutes >= 60) return `${Math.floor(minutes / 60)} ч${minutes % 60 ? ` ${minutes % 60} мин` : ""}`;
  return `${minutes} мин`;
}

/** Instants are UTC epoch minutes; all wall-clock display uses the studio's timezone. */
const ms = (minute: number) => minute * 60_000;
export const timeOf = (minute: number, tz: string) => formatInTimeZone(ms(minute), tz, "HH:mm");
export const dateKeyOf = (minute: number, tz: string) => formatInTimeZone(ms(minute), tz, "yyyy-MM-dd");
export const dayLabel = (minute: number, tz: string) => formatInTimeZone(ms(minute), tz, "EEE, d MMM", { locale: ru });
export const longDayLabel = (minute: number, tz: string) => formatInTimeZone(ms(minute), tz, "EEEE, d MMMM", { locale: ru });
export const weekdayShort = (dateKey: string) => fnsFormat(parseISO(dateKey), "EEEEEE", { locale: ru });
export const dayNumber = (dateKey: string) => fnsFormat(parseISO(dateKey), "d");
export const monthShort = (dateKey: string) => fnsFormat(parseISO(dateKey), "LLL", { locale: ru });
export const fullDateLabel = (dateKey: string) => fnsFormat(parseISO(dateKey), "EEEE, d MMMM", { locale: ru });

export const todayKey = (tz: string, now = Date.now()) => formatInTimeZone(now, tz, "yyyy-MM-dd");
export const shiftDateKey = (dateKey: string, days: number) => fnsFormat(addDays(parseISO(dateKey), days), "yyyy-MM-dd");
export const nowMinute = () => Math.floor(Date.now() / 60_000);

/** Wall-clock "yyyy-MM-dd" + "HH:mm" in the studio timezone -> UTC epoch minutes. */
export function localToMinute(dateKey: string, hhmm: string, tz: string): number {
  return Math.floor(fromZonedTime(`${dateKey}T${hhmm}:00`, tz).getTime() / 60_000);
}

export const hhmmToMin = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};
export const minToHhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

export const WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
export const WEEKDAYS_LONG = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];

export function formatPhone(digits: string): string {
  if (digits.length === 11 && digits.startsWith("7"))
    return `+7 ${digits.slice(1, 4)} ${digits.slice(4, 7)}-${digits.slice(7, 9)}-${digits.slice(9)}`;
  return digits ? `+${digits}` : "";
}

export const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;

/** Idempotency keys: crypto.randomUUID only exists in secure contexts (HTTPS/localhost), so fall back to getRandomValues. */
export function newKey(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

/** Shown status: no manual steps, a booking counts as done once its time is over. */
export const shownStatus = (b: { status: string; end_min: number }) => (b.status === "cancelled" ? "cancelled" : Date.now() / 60_000 >= b.end_min ? "ready" : "booked");
