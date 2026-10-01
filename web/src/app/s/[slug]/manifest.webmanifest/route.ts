import { getBase, getTenant } from "@/lib/server";

/** Dynamic per studio: id, scope and start_url stay inside /s/<slug>/ so studios install as separate apps. */
export async function GET(_req: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const t = await getTenant(slug);
  if (!t) return new Response("Not found", { status: 404 });
  const base = await getBase(slug);
  const scope = `${base}/`;
  const manifest = {
    id: scope,
    name: t.name,
    short_name: t.name.length > 14 ? t.name.slice(0, 13).trimEnd() + "…" : t.name,
    description: t.tagline,
    lang: "ru",
    dir: "ltr",
    start_url: `${scope}?source=pwa`,
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
    shortcuts: [
      { name: "Записаться", url: `${scope}?book=1` },
      { name: "Моя запись", url: `${scope}my` },
    ],
  };
  return new Response(JSON.stringify(manifest), {
    headers: { "Content-Type": "application/manifest+json; charset=utf-8", "Cache-Control": "public, max-age=300" },
  });
}
