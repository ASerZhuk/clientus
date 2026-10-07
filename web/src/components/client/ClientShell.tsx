"use client";

import { AppPrompt } from "@/components/AppPrompt";
import { BrandLogo } from "@/components/BrandLogo";
import { InAppBrowserBar } from "@/components/InAppBrowser";
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
          <BrandLogo src={tenant.logo_url} name={tenant.name} />
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
          <InAppBrowserBar />
          <AppHeader />
          {children}
        </div>
        <BottomNav onAssistant={() => open()} />
        <AssistantSheet slug={slug} audience="client" autoAsk={seed} isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
        <AppPrompt audience="client" />
      </BookingProvider>
    </AssistantCtx.Provider>
  );
}

export function TopBar() {
  return <AppHeader />;
}
