"use client";

import { Button } from "@/components/ui/Pill";
import { LinkSimple, Phone } from "@phosphor-icons/react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Banner } from "@astryxdesign/core/Banner";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useStudio, useVocab } from "@/components/StudioProviders";
import { AppSheet } from "@/components/ui/AppSheet";
import { NativeField } from "@/components/ui/Native";
import { api, ApiError, ownerApi } from "@/lib/api";
import { dateKeyOf, formatDuration, formatMoney, formatPrice, formatPhone, localToMinute, longDayLabel, shownStatus, telHref, timeOf } from "@/lib/format";
import type { OwnerBooking } from "@/lib/types";
import { refreshSchedule } from "./invalidate";

const STATUS_BASE: Record<string, string> = { booked: "Записан", cancelled: "Запись отменена" };

export function BookingSheet({ bookingId, onClose }: { bookingId: number | null; onClose: () => void }) {
  const { slug, tenant, href } = useStudio();
  const vocab = useVocab();
  const qc = useQueryClient();
  const tz = tenant.timezone;
  const base = ownerApi(slug);
  const q = useQuery({ queryKey: ["owner-booking", slug, bookingId], queryFn: () => api<OwnerBooking>(`${base}/bookings/${bookingId}`), enabled: bookingId !== null });
  const b = q.data;

  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [link, setLink] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!b) return;
    setDate(dateKeyOf(b.start_min, tz));
    setTime(timeOf(b.start_min, tz));
    setLink("");
    setMsg(null);
  }, [b?.id, b?.start_min, tz]); // eslint-disable-line react-hooks/exhaustive-deps

  const done = (next: OwnerBooking) => {
    qc.setQueryData(["owner-booking", slug, next.id], next);
    refreshSchedule(qc, slug);
  };
  const fail = (e: unknown) => setMsg({ ok: false, text: e instanceof ApiError ? e.message : "Не удалось выполнить." });

  const move = useMutation({
    mutationFn: () => api<OwnerBooking>(`${base}/bookings/${bookingId}/reschedule`, { method: "POST", body: { start_min: localToMinute(date, time, tz) } }),
    onSuccess: (n) => { setMsg({ ok: true, text: "Запись перенесена." }); done(n); },
    onError: (e) => fail(e instanceof ApiError && e.code === "slot_unavailable" ? new ApiError(409, "slot_unavailable") : e),
  });
  const cancel = useMutation({ mutationFn: () => api<OwnerBooking>(`${base}/bookings/${bookingId}/cancel`, { method: "POST" }), onSuccess: (n) => { setConfirmCancel(false); done(n); }, onError: (e) => { setConfirmCancel(false); fail(e); } });
  const getLink = useMutation({
    mutationFn: () => api<{ access_token: string }>(`${base}/bookings/${bookingId}/access-link`, { method: "POST" }),
    onSuccess: async (r) => {
      const url = `${location.origin}${href("/my")}#t=${r.access_token}`;
      try { await navigator.clipboard.writeText(url); setLink(""); setMsg({ ok: true, text: "Ссылка скопирована — отправьте её клиенту." }); }
      catch { setLink(url); } // no clipboard access: show the link to copy by hand
    },
    onError: fail,
  });

  const active = b && b.status !== "cancelled";
  return (
    <AppSheet isOpen={bookingId !== null} onClose={onClose} label="Запись" title={b ? b.service_name : "Запись"}>
      {q.isPending && <Skeleton height={200} radius={4} />}
      {q.isError && <Banner status="error" title="Запись не загрузилась" description={(q.error as ApiError).message} />}
      {b && (
        <>
          <div className="row-between"><b>{STATUS_BASE[shownStatus(b)] ?? vocab("status_ready")}</b><span className={`status-dot status-${shownStatus(b)}`} /></div>
          <dl className="summary panel" style={{ margin: 0 }}>
            <div><dt>Когда</dt><dd>{longDayLabel(b.start_min, tz)}, {timeOf(b.start_min, tz)}</dd></div>
            <div><dt>Длительность</dt><dd>{formatDuration(b.end_min - b.start_min)}</dd></div>
            <div><dt>{vocab("resource_one").replace(/^./, (c) => c.toUpperCase())}</dt><dd>{b.post_name}</dd></div>
            <div><dt>Клиент</dt><dd>{b.client_name}</dd></div>
            <div><dt>Телефон</dt><dd><a href={telHref(b.client_phone)}>{formatPhone(b.client_phone)}</a></dd></div>
            {(b.car || tenant.profile.contact.car !== "hidden") && <div><dt>Автомобиль</dt><dd>{b.car || "—"}{b.plate ? ` · ${b.plate}` : ""}</dd></div>}
            {b.note && <div><dt>Комментарий</dt><dd>{b.note}</dd></div>}
            <div><dt>Цена (на момент записи)</dt><dd>{formatPrice(b.price_minor, tenant.currency, b.price_kind)}</dd></div>
          </dl>
          {b.client_phone && <Button label="Позвонить клиенту" icon={<Phone weight="fill" />} href={telHref(b.client_phone)} variant="secondary" width="100%" />}
          {msg && <Banner status={msg.ok ? "success" : "error"} title={msg.text} />}

          {active && (
            <>
              <section className="stack panel" aria-label="Перенос">
                <b>Перенести</b>
                <div className="two">
                  <NativeField label="Дата" type="date" value={date} onChange={setDate} />
                  <NativeField label="Время" type="time" step={900} value={time} onChange={setTime} />
                </div>
                <Button label="Перенести запись" variant="secondary" isLoading={move.isPending} isDisabled={!date || !time} onClick={() => move.mutate()} />
                <span className="muted" style={{ fontSize: 12.5 }}>Если время занято, запись останется на прежнем месте.</span>
              </section>

              <Button label="Ссылка для клиента" icon={<LinkSimple />} variant="secondary" width="100%" isLoading={getLink.isPending} onClick={() => getLink.mutate()} />
              {link && <NativeField label="Ссылка для клиента" value={link} onChange={() => undefined} readOnly autoFocus onFocus={(e) => e.currentTarget.select()} />}
              <Button label="Отменить запись" variant="destructive" onClick={() => setConfirmCancel(true)} />
            </>
          )}
          <AlertDialog isOpen={confirmCancel} onOpenChange={setConfirmCancel} title="Отменить запись?" description="Время освободится. Клиент получит уведомление, если включил их." actionLabel="Отменить запись" cancelLabel="Оставить" actionVariant="destructive" onAction={() => cancel.mutate()} isActionLoading={cancel.isPending} />
        </>
      )}
    </AppSheet>
  );
}
