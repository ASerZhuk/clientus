"use client";

import { Button, IconButton, SegmentedControl, SegmentedControlItem } from "@/components/ui/Pill";
import { CaretLeft, CaretRight, Plus, Prohibit } from "@phosphor-icons/react";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useStudio, useVocab } from "@/components/StudioProviders";
import { api, ApiError, ownerApi } from "@/lib/api";
import { useDoParam } from "@/lib/hooks";
import { dateKeyOf, formatMoney, fullDateLabel, shiftDateKey, shownStatus, timeOf, todayKey } from "@/lib/format";
import type { OwnerBooking, OwnerSchedule, OwnerStats } from "@/lib/types";
import { BlockSheet } from "./BlockSheet";
import { BookingSheet } from "./BookingSheet";
import { QuickBookingSheet } from "./QuickBookingSheet";

const statusLabel = (kind: string, st: string) => ({ booked: "Записан", cancelled: "Отменён", accepted: kind === "person" ? "Пришёл" : "Принят", ready: kind === "person" ? "Оказана" : "Готов" })[st] ?? st;

function Stats() {
  const { slug, tenant } = useStudio();
  const [period, setPeriod] = useState<"today" | "week" | "month">("today");
  const q = useQuery({ queryKey: ["owner-stats", slug, period], queryFn: () => api<OwnerStats>(`${ownerApi(slug)}/stats?period=${period}`) });
  const s = q.data;
  return (
    <div className="stack" style={{ gap: 10 }}>
      <SegmentedControl label="Период статистики" value={period} onChange={(v) => setPeriod(v as typeof period)} layout="fill">
        <SegmentedControlItem value="today" label="Сегодня" />
        <SegmentedControlItem value="week" label="Неделя" />
        <SegmentedControlItem value="month" label="Месяц" />
      </SegmentedControl>
      {q.isError && <Banner status="error" title="Статистика недоступна" description={(q.error as ApiError).message} />}
      <div className="kpis" aria-busy={q.isPending}>
        <div className="kpi"><small>Заезды</small><b>{s?.visits ?? "—"}</b><em>записано машин, без отмен</em></div>
        <div className="kpi"><small>Работ выполнено</small><b>{s?.completed ?? "—"}</b><em>статус «Готов»</em></div>
        <div className="kpi"><small>Получено денег</small><b>{s ? formatMoney(s.received_minor, tenant.currency) : "—"}</b><em>оплаты минус возвраты</em></div>
        <div className="kpi"><small>Ожидается</small><b>{s ? formatMoney(s.scheduled_value_minor, tenant.currency) : "—"}</b><em>по будущим записям, не выручка</em></div>
      </div>
    </div>
  );
}

export function Schedule() {
  const { slug, tenant } = useStudio();
  const vocab = useVocab();
  const tz = tenant.timezone;
  const [filter, setFilter] = useState<number | null>(null);
  const [view, setView] = useState<"day" | "week">("day");
  const [anchor, setAnchor] = useState(() => todayKey(tz));
  const [openId, setOpenId] = useState<number | null>(null);
  const [quick, setQuick] = useState(false);
  const [block, setBlock] = useState(false);
  const req = useDoParam();
  useEffect(() => { const what = req?.get("do"); if (what === "block") setBlock(true); else if (what === "new-booking") setQuick(true); }, [req]);
  const days = view === "day" ? 1 : 7;
  const from = view === "week" ? shiftDateKey(anchor, -((new Date(`${anchor}T12:00:00Z`).getUTCDay() + 6) % 7)) : anchor;

  const q = useQuery({
    queryKey: ["owner-schedule", slug, from, days],
    queryFn: () => api<OwnerSchedule>(`${ownerApi(slug)}/schedule?from=${from}&days=${days}`),
    refetchInterval: 60_000,
  });

  // the owner is looking at the schedule: new bookings are seen, the number on the app icon goes away
  const lastSeen = useRef(0);
  useEffect(() => {
    if (!q.dataUpdatedAt || document.visibilityState !== "visible" || Date.now() - lastSeen.current < 10_000) return;
    lastSeen.current = Date.now();
    api(`${ownerApi(slug)}/seen`, { method: "POST" }).catch(() => undefined);
    (navigator as Navigator & { clearAppBadge?: () => Promise<void> }).clearAppBadge?.().catch(() => undefined);
  }, [q.dataUpdatedAt, slug]);

  const grouped = useMemo(() => {
    const map = new Map<string, { bookings: OwnerBooking[]; blocks: OwnerSchedule["blocks"] }>();
    for (let i = 0; i < days; i++) map.set(shiftDateKey(from, i), { bookings: [], blocks: [] });
    for (const b of q.data?.bookings ?? []) if (filter === null || b.resource_id === filter) map.get(dateKeyOf(b.start_min, tz))?.bookings.push(b);
    for (const b of q.data?.blocks ?? []) if (filter === null || b.resource_id === filter) map.get(dateKeyOf(b.start_min, tz))?.blocks.push(b);
    return [...map.entries()];
  }, [q.data, from, days, tz, filter]);
  const empty = q.data && grouped.every(([, g]) => g.bookings.length === 0 && g.blocks.length === 0);

  return (
    <div className="page stack" style={{ gap: 18 }}>
      <h1 className="owner-title" style={{ marginTop: 24 }}>Расписание</h1>
      <Stats />
      <div className="day-nav">
        <IconButton label="Назад" icon={<CaretLeft size={22} />} variant="secondary" onClick={() => setAnchor(shiftDateKey(anchor, view === "day" ? -1 : -7))} />
        <div className="mid">
          <b>{view === "day" ? fullDateLabel(anchor) : `${fullDateLabel(from).split(",")[1]?.trim()} – ${fullDateLabel(shiftDateKey(from, 6)).split(",")[1]?.trim()}`}</b>
          <button type="button" onClick={() => setAnchor(todayKey(tz))}>Сегодня</button>
        </div>
        <IconButton label="Вперёд" icon={<CaretRight size={22} />} variant="secondary" onClick={() => setAnchor(shiftDateKey(anchor, view === "day" ? 1 : 7))} />
      </div>
      <SegmentedControl label="Вид" value={view} onChange={(v) => setView(v as "day" | "week")} layout="fill">
        <SegmentedControlItem value="day" label="День" />
        <SegmentedControlItem value="week" label="Неделя" />
      </SegmentedControl>

      {(q.data?.resources.length ?? 0) > 1 && (
        <div className="chips" role="group" aria-label={vocab("resource_section")}>
          <button type="button" className="chip-btn" aria-pressed={filter === null} onClick={() => setFilter(null)}>Все</button>
          {q.data!.resources.map((r) => (
            <button key={r.id} type="button" className="chip-btn" aria-pressed={filter === r.id} onClick={() => setFilter(r.id)}>{r.name}</button>
          ))}
        </div>
      )}
      {q.isPending && <div className="stack"><Skeleton height={70} /><Skeleton height={70} /></div>}
      {q.isError && <Banner status="error" title="Расписание не загрузилось" description={(q.error as ApiError).message} endContent={<Button label="Повторить" size="sm" onClick={() => q.refetch()} />} />}
      {empty && <EmptyState title="Записей нет" description="На этот период записей и блокировок нет." isCompact actions={<Button label="Добавить запись" onClick={() => setQuick(true)} />} />}
      {q.data && grouped.map(([key, g]) => {
        if (view === "week" && !g.bookings.length && !g.blocks.length) return null;
        const items = [...g.bookings.map((b) => ({ t: b.start_min, b })), ...g.blocks.map((k) => ({ t: k.start_min, k }))].sort((a, b) => a.t - b.t);
        return (
          <section key={key} aria-label={fullDateLabel(key)}>
            {view === "week" && <h2 className="owner-day-title">{fullDateLabel(key)}</h2>}
            {items.length > 0 && (
              <div className="svc-panel">
                {items.map((it) => "b" in it && it.b ? (
                  <button key={`b${it.b.id}`} className="booking-row" type="button" onClick={() => setOpenId(it.b!.id)} style={it.b.status === "cancelled" ? { opacity: 0.5 } : undefined}>
                    <span className="time-col">{timeOf(it.b.start_min, tz)}<small>{it.b.post_name}</small></span>
                    <span className="grow">
                      <div className="service-name">{it.b.service_name}{it.b.is_demo ? " · демо" : ""}</div>
                      <div className="service-desc">{it.b.client_name}{it.b.car ? ` · ${it.b.car}` : ""}</div>
                    </span>
                    <span className="stack" style={{ alignItems: "flex-end", gap: 4 }}>
                      <span className="row" style={{ gap: 8, fontSize: 15 }}><i className={`status-dot status-${shownStatus(it.b)}`} />{statusLabel(tenant.profile.kind, shownStatus(it.b))}</span>
                    </span>
                  </button>
                ) : "k" in it && it.k ? (
                  <div key={`k${it.k.id}`} className="booking-row block-row" style={{ cursor: "default" }}>
                    <span className="time-col">{timeOf(it.k.start_min, tz)}<small>{q.data.resources.find((r) => r.id === it.k!.resource_id)?.name}</small></span>
                    <span className="grow">Занято{it.k.note ? `: ${it.k.note}` : ""} до {timeOf(it.k.end_min, tz)}</span>
                  </div>
                ) : null)}
              </div>
            )}
          </section>
        );
      })}

      <div className="fab">
        <IconButton label={vocab("resource_block")} icon={<Prohibit size={26} weight="bold" />} variant="secondary" size="lg" onClick={() => setBlock(true)} />
        <IconButton label="Добавить запись" icon={<Plus size={28} weight="bold" />} variant="primary" size="lg" onClick={() => setQuick(true)} />
      </div>

      <BookingSheet bookingId={openId} onClose={() => setOpenId(null)} />
      <QuickBookingSheet isOpen={quick} onClose={() => setQuick(false)} defaultDate={anchor} />
      <BlockSheet isOpen={block} onClose={() => setBlock(false)} defaultDate={anchor} resources={q.data?.resources ?? []} blocks={q.data?.blocks ?? []} />
    </div>
  );
}
