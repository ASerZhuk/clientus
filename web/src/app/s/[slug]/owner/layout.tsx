import type { Metadata } from "next";
import { OwnerShell } from "@/components/owner/OwnerShell";
import { getBase, getTenant } from "@/lib/server";

/** The cabinet has its own manifest: "Add to Home Screen" from here installs an app that opens the cabinet, not the client site. */
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const t = await getTenant(slug);
  const base = await getBase(slug);
  return {
    title: "Кабинет",
    robots: { index: false, follow: false },
    manifest: `${base}/manifest.webmanifest?app=owner`,
    appleWebApp: { capable: true, title: t ? `${t.name} · Кабинет` : "Кабинет", statusBarStyle: "black-translucent" },
  };
}

export default function OwnerLayout({ children }: { children: React.ReactNode }) {
  return <OwnerShell>{children}</OwnerShell>;
}
