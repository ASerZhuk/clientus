"use client";

import { Theme } from "@astryxdesign/core";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import ru from "@astryxdesign/core/locales/ru-RU.json";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, studioApi } from "@/lib/api";
import "@/lib/install"; // catches the browser install prompt as early as possible
import { studioTheme } from "@/lib/theme";
import type { TenantPublic } from "@/lib/types";

const StudioContext = createContext<{ slug: string; tenant: TenantPublic; base: string; href: (path?: string) => string } | null>(null);

export function useProfile() {
  const { tenant } = useStudio();
  return tenant.profile;
}

/** A word of the business type ("место" / "бокс" / "мастер" ...); falls back to the key so nothing renders blank. */
export function useVocab() {
  const { vocab } = useProfile();
  return (key: string) => vocab[key] ?? key;
}

export function useStudio() {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error("useStudio must be used inside StudioProviders");
  return ctx;
}

function TenantData({ initial, base, children }: { initial: TenantPublic; base: string; children: React.ReactNode }) {
  const { data } = useQuery({
    queryKey: ["tenant", initial.slug],
    queryFn: () => api<TenantPublic>(studioApi(initial.slug)),
    initialData: initial,
    staleTime: 30_000,
  });
  const href = (path = "") => (base + path) || "/";
  return <StudioContext.Provider value={{ slug: initial.slug, tenant: data, base, href }}>{children}</StudioContext.Provider>;
}

/** Registers the studio-scoped service worker (production only, so dev hot reload is never cached). */
function ServiceWorker({ slug, base }: { slug: string; base: string }) {
  useEffect(() => {
    if (!("serviceWorker" in navigator) || process.env.NODE_ENV !== "production") return;
    // the worker learns its studio and base path from its own URL, so one source serves every studio and domain
    navigator.serviceWorker.register(`${base}/sw.js?s=${slug}&b=${encodeURIComponent(base)}`, { scope: `${base}/` }).catch(() => undefined);
  }, [slug, base]);
  return null;
}

export function StudioProviders({ tenant, base, children }: { tenant: TenantPublic; base: string; children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } }));
  const theme = useMemo(() => studioTheme(tenant.slug, tenant.accent), [tenant.slug, tenant.accent]);
  return (
    <QueryClientProvider client={client}>
      <InternationalizationProvider locale="ru-RU" messages={{ "ru-RU": ru }}>
      <Theme theme={theme} mode="dark">
        <TenantData initial={tenant} base={base}>
          <ServiceWorker slug={tenant.slug} base={base} />
          {children}
        </TenantData>
      </Theme>
      </InternationalizationProvider>
    </QueryClientProvider>
  );
}
