import { ClientShell } from "@/components/client/ClientShell";

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  return <ClientShell>{children}</ClientShell>;
}
