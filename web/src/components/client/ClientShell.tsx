"use client";

import { AppPrompt } from "@/components/AppPrompt";
import { UserCircle } from "@phosphor-icons/react";
import Link from "next/link";
import { createContext, useCallback, useContext, useState } from "react";
import { useStudio } from "@/components/StudioProviders";
import { AssistantSheet } from "./AssistantSheet";
import { BookingProvider } from "./BookingProvider";
import { BottomNav } from "./BottomNav";

const AssistantCtx = createContext<{ open: (seed?: "pick") => void } | null>(null);
export const useAssistant = () => useContext(AssistantCtx) ?? { open: () => undefined };

export function AppHeader() {
  const { tenant, href } = useStudio();
  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link href={href()} className="brand" aria-label={`${tenant.name}: на главную`}>
          <span className="brand-logo">
            {tenant.logo_url ? /* eslint-disable-next-line @next/next/no-img-element */ <img src={tenant.logo_url} alt="" /> : tenant.name.slice(0, 1)}
          </span>
          <span>{tenant.name}</span>
        </Link>
        <span className="grow" />
        <Link href={href("/account")} className="icon-round" aria-label="Профиль">
          <UserCircle size={32} />
        </Link>
      </div>
    </header>
  );
}

export function ClientShell({ children }: { children: React.ReactNode }) {
  const { slug, tenant } = useStudio();
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [seed, setSeed] = useState<string | undefined>();
  const open = useCallback((s?: "pick") => { setSeed(s === "pick" ? "Подобрать услугу" : undefined); setAssistantOpen(true); }, []);
  return (
    <AssistantCtx.Provider value={{ open }}>
      <BookingProvider>
        <div className="studio" data-profile={tenant.profile.type}>
          <AppHeader />
          {tenant.is_preview && (
            <p className="page muted preview-note" style={{ margin: "10px auto 0", fontSize: 13 }}>
              Образец: данные демонстрационные, уведомления не отправляются.
            </p>
          )}
          {children}
        </div>
        <BottomNav onAssistant={() => open()} />
        <AssistantSheet slug={slug} audience="client" autoAsk={seed} isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
        {!tenant.is_preview && <AppPrompt audience="client" />}
      </BookingProvider>
    </AssistantCtx.Provider>
  );
}

export function TopBar() {
  return <AppHeader />;
}
