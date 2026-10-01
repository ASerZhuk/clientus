import { errorMessage } from "./errors";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail?: unknown,
  ) {
    super(errorMessage(code, status));
  }
}

let csrfToken: string | null = null;
export const setCsrf = (token: string | null) => {
  csrfToken = token;
};

interface Options {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData;
  bookingToken?: string;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

function extractCode(payload: unknown, status: number): { code: string; detail?: unknown } {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return { code: detail };
  if (Array.isArray(detail)) return { code: "validation_error", detail };
  if (detail && typeof detail === "object" && "code" in detail) return { code: String((detail as { code: unknown }).code), detail };
  return { code: status === 429 ? "too_many_requests" : "server_error" };
}

/** Same-origin fetch to FastAPI. Owner mutations carry the CSRF token held in memory only. */
export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken && (path.includes("/owner/") || path.includes("/api/admin/"))) headers["X-CSRF-Token"] = csrfToken;
  if (opts.bookingToken) headers["X-Booking-Token"] = opts.bookingToken;
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
      credentials: "same-origin",
      cache: "no-store",
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network_error");
  }
  if (res.status === 204) return undefined as T;
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const { code, detail } = extractCode(payload, res.status);
    throw new ApiError(res.status, code, detail);
  }
  return payload as T;
}

export const studioApi = (slug: string) => `/api/s/${slug}`;
export const ownerApi = (slug: string) => `/api/s/${slug}/owner`;
