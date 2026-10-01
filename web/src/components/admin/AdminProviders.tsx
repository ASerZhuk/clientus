"use client";

import { Theme } from "@astryxdesign/core";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import ru from "@astryxdesign/core/locales/ru-RU.json";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { studioTheme } from "@/lib/theme";

export function AdminProviders({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } }));
  const theme = useMemo(() => studioTheme("admin", "#4690FF"), []);
  return (
    <QueryClientProvider client={client}>
      <InternationalizationProvider locale="ru-RU" messages={{ "ru-RU": ru }}>
        <Theme theme={theme} mode="dark">
          <style dangerouslySetInnerHTML={{ __html: ":root{--studio-accent:#4690FF;--studio-on-accent:#000000}" }} />
          {children}
        </Theme>
      </InternationalizationProvider>
    </QueryClientProvider>
  );
}
