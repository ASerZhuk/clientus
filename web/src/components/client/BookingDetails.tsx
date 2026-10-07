"use client";

import { Button } from "@/components/ui/Pill";
import { BellRinging, CalendarPlus, Phone } from "@phosphor-icons/react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Banner } from "@astryxdesign/core/Banner";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useStudio, useVocab } from "@/components/StudioProviders";
import { api, ApiError, studioApi } from "@/lib/api";
import { formatDuration, formatMoney, formatPrice, longDayLabel, shownStatus, telHref, timeOf } from "@/lib/format";
import { addToCalendar } from "@/lib/ics";
import { detectPush, deniedHelp, onPermissionMaybeChanged, subscribePush, currentEndpoint, type PushSupport } from "@/lib/push";
import type { ClientBooking, PushConfig } from "@/lib/types";

const STATUS_BASE: Record<string, string> = { booked: "Запись подтверждена", cancelled: "Запись отменена" };

function Reminder({ token }: { token: string }) {
  const { slug, tenant } = useStudio();
  const cfg = useQuery({ queryKey: ["push-config", slug], queryFn: () => api<PushConfig>(`${studioApi(slug)}/push/config`), staleTime: 60_000 });
  const [support, setSupport] = useState<PushSupport | null>(null);
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!cfg.data) return;
    const check = () => {
      setSupport(cfg.data!.preview ? { state: "server-off" } : detectPush(cfg.data!.enabled));
      // the device may be subscribed for something else (e.g. the owner's cabinet): ask the server about THIS booking
      currentEndpoint()
        .then((e) => (e && Notification.permission === "granted" ? api<{ on: boolean }>(`${studioApi(slug)}/my/push?endpoint=${encodeURIComponent(e)}`, { bookingToken: token }).then((r) => r.on) : false))
        .then(setOn)
        .catch(() => setOn(false));
    };
    check();
    return onPermissionMaybeChanged(check);
  }, [cfg.data]);

  if (!support || !cfg.data) return null;
  const hours = tenant.rules.reminder_hours;
  const toggle = async () => {
    setBusy(true);
    setError("");
    try {
      if (on) {
        // only this booking's reminder: the device subscription may serve other bookings or the owner's cabinet
        const endpoint = await currentEndpoint();
        if (endpoint) await api(`${studioApi(slug)}/my/push?endpoint=${encodeURIComponent(endpoint)}`, { method: "DELETE", bookingToken: token });
        setOn(false);
      } else {
        const sub = await subscribePush(slug, cfg.data!.public_key ?? "");
        await api(`${studioApi(slug)}/my/push`, { method: "POST", body: { endpoint: sub.endpoint, keys: sub.keys }, bookingToken: token });
        setOn(true);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message === "permission_denied" ? "Вы не разрешили уведомления." : (e as Error).message || "Не удалось включить напоминание.");
    } finally {
      setBusy(false);
    }
  };

  if (support.state === "ready")
    return (
      <div className="stack" style={{ gap: 8 }}>
        <Button label={on ? `Напоминание включено — выключить` : `Напомнить за ${hours} ч`} icon={<BellRinging weight="fill" />} variant={on ? "secondary" : "primary"} isLoading={busy} onClick={toggle} width="100%" />
        {error && <span className="error-text">{error}</span>}
      </div>
    );
  const note: Record<string, string> = {
    "ios-install": "На iPhone напоминания работают после установки: нажмите «Поделиться» → «На экран Домой», затем откройте студию с иконки и включите напоминание. Пока добавьте запись в календарь.",
    denied: `${deniedHelp()} Или добавьте запись в календарь — он напомнит сам.`,
    unsupported: "Этот браузер не поддерживает уведомления. Добавьте запись в календарь.",
    insecure: "Уведомления работают только на защищённом адресе (https). Добавьте запись в календарь.",
    "server-off": "Уведомления сейчас недоступны. Добавьте запись в календарь.",
  };
  return <Banner status="info" title="Напоминание" description={note[support.state]} />;
}

export function BookingDetails({ booking, token, onChanged }: { booking: ClientBooking; token: string; onChanged: (b: ClientBooking) => void }) {
  const { slug, tenant } = useStudio();
  const vocab = useVocab();
  const qc = useQueryClient();
  const tz = tenant.timezone;
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");
  const cancelled = booking.status === "cancelled";
  const days = Math.ceil((booking.end_min - booking.start_min) / 1440);
  const cancel = async () => {
    try {
      const b = await api<ClientBooking>(`${studioApi(slug)}/my/cancel`, { method: "POST", bookingToken: token });
      qc.invalidateQueries({ queryKey: ["my", slug] });
      onChanged(b);
      setConfirm(false);
    } catch (e) {
      setConfirm(false);
      setError(e instanceof ApiError ? e.message : "Не удалось отменить.");
    }
  };
  return (
    <div className="stack">
      <div className="panel stack">
        <div className="row-between">
          <b style={{ fontSize: 17 }}>{STATUS_BASE[shownStatus(booking)] ?? vocab("status_ready")}</b>
          <span className={`status-dot status-${shownStatus(booking)}`} aria-hidden />
        </div>
        <dl className="summary" style={{ margin: 0 }}>
          <div><dt>Услуга</dt><dd>{booking.service_name}</dd></div>
          <div><dt>Когда</dt><dd>{longDayLabel(booking.start_min, tz)}, {timeOf(booking.start_min, tz)}</dd></div>
          {days > 1 && <div><dt>Готово</dt><dd>{longDayLabel(booking.end_min, tz)}, {timeOf(booking.end_min, tz)}</dd></div>}
          <div><dt>Длительность</dt><dd>{formatDuration(booking.end_min - booking.start_min)}</dd></div>
          {booking.post_name && <div><dt>{vocab("resource_one").replace(/^./, (c) => c.toUpperCase())}</dt><dd>{booking.post_name}</dd></div>}
          {booking.car && <div><dt>Автомобиль</dt><dd>{booking.car}{booking.plate ? ` · ${booking.plate}` : ""}</dd></div>}
          <div><dt>Стоимость</dt><dd>{formatPrice(booking.price_minor, tenant.currency, booking.price_kind)}</dd></div>
        </dl>
      </div>
      {!cancelled && (
        <>
          <Reminder token={token} />
          <Button label="Добавить в календарь" icon={<CalendarPlus weight="fill" />} variant="secondary" width="100%" onClick={() => addToCalendar(booking, { name: tenant.name, address: tenant.address, phone: tenant.phone, slug }, studioApi(slug))} />
          {booking.status === "booked" && (booking.can_cancel ? (
            <Button label="Отменить запись" variant="ghost" width="100%" onClick={() => setConfirm(true)} />
          ) : (
            <Banner status="warning" title="Онлайн-отмена закрыта" description={`Отменить можно не позднее чем за ${booking.cancel_before_hours} ч до начала. Позвоните в студию.`} endContent={tenant.phone ? <Button label="Позвонить" size="sm" icon={<Phone />} href={telHref(tenant.phone)} /> : undefined} />
          ))}
          {error && <span className="error-text" role="alert">{error}</span>}
        </>
      )}
      <AlertDialog
        isOpen={confirm}
        onOpenChange={setConfirm}
        title="Отменить запись?"
        description={`${booking.service_name}, ${longDayLabel(booking.start_min, tz)} в ${timeOf(booking.start_min, tz)}. Время освободится для других клиентов.`}
        actionLabel="Да, отменить"
        cancelLabel="Оставить"
        actionVariant="destructive"
        onAction={cancel}
      />
    </div>
  );
}
