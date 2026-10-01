import type { Metadata } from "next";
import { OwnerShell } from "@/components/owner/OwnerShell";

export const metadata: Metadata = { title: "Кабинет", robots: { index: false, follow: false } };

export default function OwnerLayout({ children }: { children: React.ReactNode }) {
  return <OwnerShell>{children}</OwnerShell>;
}
