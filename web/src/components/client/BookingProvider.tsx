"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useStudio } from "@/components/StudioProviders";
import { BookingSheet, type BookingPreset } from "./BookingSheet";

const Ctx = createContext<{ open: (preset?: BookingPreset) => void } | null>(null);
export const useBooking = () => useContext(Ctx) ?? { open: () => undefined };

/** One booking sheet for the whole client app. ?book=1 or ?service=ID[&start=MINUTE] opens it on load. */
export function BookingProvider({ children }: { children: React.ReactNode }) {
  const { tenant } = useStudio();
  const [isOpen, setOpen] = useState(false);
  const [preset, setPreset] = useState<BookingPreset | null>(null);
  const open = useCallback((p?: BookingPreset) => {
    setPreset(p ?? null);
    setOpen(true);
  }, []);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const serviceId = Number(q.get("service")) || undefined;
    if (q.has("book") || serviceId) {
      open({ serviceId, start: Number(q.get("start")) || undefined });
      history.replaceState(null, "", window.location.pathname);
    }
  }, [open]);

  return (
    <Ctx.Provider value={{ open }}>
      {children}
      <BookingSheet isOpen={isOpen} onClose={() => setOpen(false)} preset={preset} key={tenant.slug} />
    </Ctx.Provider>
  );
}
