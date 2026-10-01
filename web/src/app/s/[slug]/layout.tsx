import type { Metadata, Viewport } from "next";
import { notFound } from "next/navigation";
import { StudioProviders } from "@/components/StudioProviders";
import { getBase, getTenant } from "@/lib/server";
import { onAccent } from "@/lib/theme";

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const t = await getTenant(slug);
  if (!t) return { title: "Студия не найдена", robots: { index: false } };
  const base = await getBase(slug);
  return {
    title: { default: t.name, template: `%s · ${t.name}` },
    description: t.tagline || t.description,
    manifest: `${base}/manifest.webmanifest`,
    // an unverified sample must never be indexed
    robots: t.is_preview ? { index: false, follow: false } : { index: true },
    icons: { icon: [{ url: t.pwa.icon192, sizes: "192x192", type: "image/png" }], apple: [{ url: t.pwa.apple_touch, sizes: "180x180" }] },
    appleWebApp: {
      capable: true,
      title: t.name,
      statusBarStyle: "black-translucent",
      startupImage: t.pwa.startup.map((s) => ({
        url: s.url,
        media: `(device-width: ${s.dw}px) and (device-height: ${s.dh}px) and (-webkit-device-pixel-ratio: ${s.ratio}) and (orientation: portrait)`,
      })),
    },
    other: { "mobile-web-app-capable": "yes" },
    openGraph: { title: t.name, description: t.tagline, type: "website", locale: "ru_RU" },
  };
}

export async function generateViewport(): Promise<Viewport> {
  return { themeColor: "#000000", colorScheme: "dark", viewportFit: "cover", width: "device-width", initialScale: 1, interactiveWidget: "resizes-content" };
}

export default async function StudioLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const tenant = await getTenant(slug);
  if (!tenant) notFound();
  const base = await getBase(slug);
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: `:root{--studio-accent:${tenant.accent};--studio-on-accent:${onAccent(tenant.accent)}}` }} />
      <StudioProviders tenant={tenant} base={base}>{children}</StudioProviders>
    </>
  );
}
