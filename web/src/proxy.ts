import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Custom domains. A request whose Host is not one of our platform hosts is looked up in the API
 * (domain -> studio) and rewritten to that studio's pages, so https://book.customer.ru/services
 * is served by /s/<slug>/services. The URL in the browser stays clean. Unknown hosts get a 404, and a
 * customer's domain can never reach another studio's /s/... paths, /admin or /owner of someone else.
 */
const API = () => (process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const platformHosts = () => (process.env.PLATFORM_HOSTS ?? "localhost,127.0.0.1").split(",").map((h) => h.trim().toLowerCase().split(":")[0]).filter(Boolean);

const cache = new Map<string, { slug: string | null; until: number }>();

async function resolveHost(host: string): Promise<string | null> {
  const hit = cache.get(host);
  if (hit && hit.until > Date.now()) return hit.slug;
  let slug: string | null = null;
  try {
    const res = await fetch(`${API()}/api/internal/host?host=${encodeURIComponent(host)}`, {
      headers: { "x-internal-token": process.env.INTERNAL_TOKEN ?? "dev-internal-token" },
      cache: "no-store",
    });
    if (res.ok) slug = ((await res.json()) as { slug: string }).slug;
  } catch {
    return null; // API unreachable: do not cache a failure
  }
  cache.set(host, { slug, until: Date.now() + (slug ? 30_000 : 10_000) });
  return slug;
}

export async function proxy(request: NextRequest) {
  const hostname = (request.headers.get("host") ?? "").toLowerCase().split(":")[0];
  if (!hostname || platformHosts().includes(hostname)) return NextResponse.next();
  const path = request.nextUrl.pathname;
  if (path.startsWith("/api/") || path.startsWith("/_next/") || path === "/favicon.ico") return NextResponse.next();
  const slug = await resolveHost(hostname);
  if (!slug || path.startsWith("/s/") || path.startsWith("/admin")) return new NextResponse("Not found", { status: 404 });
  const url = request.nextUrl.clone();
  url.pathname = `/s/${slug}${path === "/" ? "" : path}`;
  const headers = new Headers(request.headers);
  headers.set("x-studio-custom", "1");
  return NextResponse.rewrite(url, { request: { headers } });
}

export const config = { matcher: ["/((?!_next/static|_next/image).*)"] };
