/** The client has no account: each booking's access token lives in this browser's localStorage. */
export interface StoredBooking {
  id: number;
  token: string;
  service_name: string;
  start_min: number;
}

const key = (slug: string) => `bookings:${slug}`;

export function readBookings(slug: string): StoredBooking[] {
  try {
    const raw = window.localStorage.getItem(key(slug));
    const parsed = raw ? (JSON.parse(raw) as StoredBooking[]) : [];
    return Array.isArray(parsed) ? parsed.filter((b) => typeof b.token === "string") : [];
  } catch {
    return [];
  }
}

export function saveBooking(slug: string, entry: StoredBooking): void {
  try {
    const rest = readBookings(slug).filter((b) => b.id !== entry.id);
    window.localStorage.setItem(key(slug), JSON.stringify([entry, ...rest].slice(0, 20)));
  } catch {
    /* private mode: the confirmation screen still shows the details */
  }
}

export function removeBooking(slug: string, id: number): void {
  try {
    window.localStorage.setItem(key(slug), JSON.stringify(readBookings(slug).filter((b) => b.id !== id)));
  } catch {
    /* ignore */
  }
}

/** A booking link may arrive as /my#t=TOKEN (shared by the owner): adopt it and clean the URL. */
export function adoptTokenFromHash(slug: string): string | null {
  const match = /[#&]t=([\w-]{20,})/.exec(window.location.hash);
  if (!match) return null;
  history.replaceState(null, "", window.location.pathname + window.location.search);
  return match[1];
}
