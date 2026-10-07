import { getBase, getTenant } from "@/lib/server";

/** Dynamic per studio: id, scope and start_url stay inside /s/<slug>/ (with the slash, so studios never overlap:
 *  "alex" does not capture "alexmotors"). src/proxy.ts sends /s/<slug> to /s/<slug>/. */
export async function GET(req: Request, { params }: { params: Promise<{ slug: string }> }) {
  // ?app=owner: the owner cabinet is its own home-screen app (opens straight into the cabinet, where push is switched on)
  const qs = new URL(req.url).searchParams;
  const owner = qs.get("app") === "owner";
  const k = owner && /^[\w.-]{10,120}$/.test(qs.get("k") ?? "") ? qs.get("k") : null; // sign-in code for the iPhone app's first launch
  const { slug } = await params;
  const t = await getTenant(slug);
  if (!t) return new Response("Not found", { status: 404 });
  const base = await getBase(slug);
  const scope = `${base}/`;
  const manifest = {
    id: owner ? `${scope}owner` : scope,
    name: owner ? `${t.name} · Кабинет` : t.name,
    short_name: t.name.length > 14 ? t.name.slice(0, 13).trimEnd() + "…" : t.name,
    description: owner ? "Записи, расписание и уведомления владельца" : t.tagline,
    lang: "ru",
    dir: "ltr",
    start_url: owner ? `${scope}owner?source=pwa${k ? `&k=${k}` : ""}` : `${scope}?source=pwa`,
    scope,
    display: "standalone",
    orientation: "portrait",
    background_color: "#000000",
    theme_color: "#000000",
    categories: ["business", "lifestyle"],
    icons: [
      { src: t.pwa.icon192, sizes: "192x192", type: "image/png", purpose: "any" },
      { src: t.pwa.icon512, sizes: "512x512", type: "image/png", purpose: "any" },
      { src: t.pwa.maskable512, sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: owner
      ? [{ name: "Расписание", url: `${scope}owner` }, { name: "Услуги", url: `${scope}owner/services` }]
      : [{ name: "Записаться", url: `${scope}?book=1` }, { name: "Моя запись", url: `${scope}my` }],
  };
  return new Response(JSON.stringify(manifest), {
    headers: { "Content-Type": "application/manifest+json; charset=utf-8", "Cache-Control": k ? "no-store" : "public, max-age=300" },
  });
}
