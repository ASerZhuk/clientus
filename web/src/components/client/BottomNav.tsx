"use client";

import { CalendarCheck, House, Plus, Sparkle, SquaresFour } from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useStudio } from "@/components/StudioProviders";
import { useBooking } from "./BookingProvider";

/** Floating dock: round icon buttons with the glowing book button in the middle. The page reserves its height. */
export function BottomNav({ onAssistant }: { onAssistant: () => void }) {
  const path = usePathname();
  const { href, base } = useStudio();
  const booking = useBooking();
  const items = [
    { href: href(), label: "Главная", Icon: House, active: path === (base || "/") || path === `${base}/` },
    { href: href("/services"), label: "Услуги", Icon: SquaresFour, active: path.startsWith(`${base}/services`) },
  ];
  const link = ({ href: to, label, Icon, active }: (typeof items)[number]) => (
    <Link key={to} href={to} className="dock-item" aria-label={label} aria-current={active ? "page" : undefined}>
      <Icon size={24} weight={active ? "fill" : "regular"} aria-hidden />
    </Link>
  );
  const my = { href: href("/my"), label: "Моя запись", Icon: CalendarCheck, active: path.startsWith(`${base}/my`) };
  return (
    <nav className="dock-wrap" aria-label="Основная навигация">
      <div className="dock">
        {items.map(link)}
        <button type="button" className="dock-main" aria-label="Записаться онлайн" onClick={() => booking.open()}><Plus size={28} weight="bold" aria-hidden /></button>
        {link(my)}
        <button type="button" className="dock-item" id="ai-fab" aria-label="Помощник" onClick={onAssistant}><Sparkle size={24} aria-hidden /></button>
      </div>
    </nav>
  );
}
