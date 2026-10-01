/**
 * Runtime proxy /api/* -> FastAPI (INTERNAL_API_URL is read per request, not baked in at build).
 * In production the reverse proxy sends /api straight to FastAPI and this route is never hit;
 * it keeps dev, previews and single-origin setups working with the same browser code.
 */
const UPSTREAM = () => (process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const HOP = new Set(["host", "connection", "content-length", "transfer-encoding", "keep-alive", "upgrade", "accept-encoding"]);

async function proxy(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = new URL(req.url);
  const target = `${UPSTREAM()}/api/${path.map(encodeURIComponent).join("/")}${url.search}`;
  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!HOP.has(k.toLowerCase())) headers.set(k, v);
  });
  headers.set("x-forwarded-host", req.headers.get("host") ?? "");
  headers.set("x-forwarded-for", req.headers.get("x-forwarded-for") ?? "127.0.0.1");
  const hasBody = !["GET", "HEAD"].includes(req.method);
  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body: hasBody ? req.body : undefined,
    // @ts-expect-error Node's fetch requires duplex when streaming a request body
    duplex: hasBody ? "half" : undefined,
    redirect: "manual",
    cache: "no-store",
  }).catch(() => null);
  if (!upstream) return Response.json({ detail: "upstream_unavailable" }, { status: 502 });
  const out = new Headers();
  upstream.headers.forEach((v, k) => {
    if (!HOP.has(k.toLowerCase()) && k.toLowerCase() !== "set-cookie") out.set(k, v);
  });
  for (const cookie of upstream.headers.getSetCookie()) out.append("set-cookie", cookie);
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
export const dynamic = "force-dynamic";
