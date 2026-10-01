"use client";

import { Button, SegmentedControl, SegmentedControlItem } from "@/components/ui/Pill";
import { Phone } from "@phosphor-icons/react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Banner } from "@astryxdesign/core/Banner";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useStudio, useVocab } from "@/components/StudioProviders";
import { AppSheet } from "@/components/ui/AppSheet";
import { NativeField, NativeSelect } from "@/components/ui/Native";
import { api, ApiError, ownerApi } from "@/lib/api";
import { dateKeyOf, formatDuration, formatMoney, formatPhone, localToMinute, longDayLabel, telHref, timeOf, toMinor } from "@/lib/format";
import { paymentSchema, fieldErrors } from "@/lib/schemas";
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

  const [payKind, setPayKind] = useState<"payment" | "refund">("payment");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [payErrors, setPayErrors] = useState<Record<string, string>>({});
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [link, setLink] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!b) return;
    setDate(dateKeyOf(b.start_min, tz));
    setTime(timeOf(b.start_min, tz));
    setAmount(b.due_minor ? String(b.due_minor / 100) : "");
    setPayKind("payment");
    setLink("");
    setMsg(null);
  }, [b?.id, b?.start_min, tz]); // eslint-disable-line react-hooks/exhaustive-deps

  const done = (next: OwnerBooking) => {
    qc.setQueryData(["owner-booking", slug, next.id], next);
    refreshSchedule(qc, slug);
  };
  const fail = (e: unknown) => setMsg({ ok: false, text: e instanceof ApiError ? e.message : "Не удалось выполнить." });

  const status = useMutation({ mutationFn: (s: string) => api<OwnerBooking>(`${base}/bookings/${bookingId}/status`, { method: "PATCH", body: { status: s } }), onSuccess: done, onError: fail });
  const pay = useMutation({
    mutationFn: (kind: "payment" | "refund") => {
      const parsed = paymentSchema.safeParse({ kind, amount: Number(amount.replace(",", ".")), method });
      if (!parsed.success) throw new ApiError(422, "validation_error", fieldErrors(parsed.error));
      return api<OwnerBooking>(`${base}/bookings/${bookingId}/payments`, { method: "POST", body: { kind, amount_minor: toMinor(parsed.data.amount), method } });
    },
    onSuccess: (n, kind) => { setPayErrors({}); setMsg({ ok: true, text: kind === "payment" ? "Оплата внесена." : "Возврат внесён." }); setAmount(""); done(n); },
    onError: (e) => (e instanceof ApiError && e.code === "validation_error" && e.detail && !Array.isArray(e.detail) ? setPayErrors(e.detail as Record<string, string>) : fail(e)),
  });
  const move = useMutation({
    mutationFn: () => api<OwnerBooking>(`${base}/bookings/${bookingId}/reschedule`, { method: "POST", body: { start_min: localToMinute(date, time, tz) } }),
    onSuccess: (n) => { setMsg({ ok: true, text: "Запись перенесена." }); done(n); },
    onError: (e) => fail(e instanceof ApiError && e.code === "slot_unavailable" ? new ApiError(409, "slot_unavailable") : e),
  });
  const cancel = useMutation({ mutationFn: () => api<OwnerBooking>(`${base}/bookings/${bookingId}/cancel`, { method: "POST" }), onSuccess: (n) => { setConfirmCancel(false); done(n); }, onError: (e) => { setConfirmCancel(false); fail(e); } });
  const getLink = useMutation({
    mutationFn: () => api<{ access_token: string }>(`${base}/bookings/${bookingId}/access-link`, { method: "POST" }),
    onSuccess: (r) => setLink(`${location.origin}${href("/my")}#t=${r.access_token}`),
    onError: fail,
  });

  const active = b && b.status !== "cancelled";
  return (
    <AppSheet isOpen={bookingId !== null} onClose={onClose} label="Запись" title={b ? b.service_name : "Запись"}>
      {q.isPending && <Skeleton height={200} radius={4} />}
      {q.isError && <Banner status="error" title="Запись не загрузилась" description={(q.error as ApiError).message} />}
      {b && (
        <>
          <div className="row-between"><b>{STATUS_BASE[b.status] ?? vocab(b.status === "accepted" ? "status_accepted" : "status_ready")}</b><span className={`status-dot status-${b.status}`} /></div>
          <dl className="summary panel" style={{ margin: 0 }}>
            <div><dt>Когда</dt><dd>{longDayLabel(b.start_min, tz)}, {timeOf(b.start_min, tz)}</dd></div>
            <div><dt>Длительность</dt><dd>{formatDuration(b.end_min - b.start_min)}</dd></div>
            <div><dt>{vocab("resource_one").replace(/^./, (c) => c.toUpperCase())}</dt><dd>{b.post_name}</dd></div>
            <div><dt>Клиент</dt><dd>{b.client_name}</dd></div>
            <div><dt>Телефон</dt><dd><a href={telHref(b.client_phone)}>{formatPhone(b.client_phone)}</a></dd></div>
            {(b.car || tenant.profile.contact.car !== "hidden") && <div><dt>Автомобиль</dt><dd>{b.car || "—"}{b.plate ? ` · ${b.plate}` : ""}</dd></div>}
            {b.note && <div><dt>Комментарий</dt><dd>{b.note}</dd></div>}
            <div><dt>Цена (на момент записи)</dt><dd>{formatMoney(b.price_minor, tenant.currency)}</dd></div>
            <div><dt>Оплачено</dt><dd>{formatMoney(b.net_minor, tenant.currency)}</dd></div>
            <div><dt>Остаток</dt><dd>{formatMoney(b.due_minor, tenant.currency)}</dd></div>
          </dl>
          {b.client_phone && <Button label="Позвонить клиенту" icon={<Phone weight="fill" />} href={telHref(b.client_phone)} variant="secondary" width="100%" />}
          {msg && <Banner status={msg.ok ? "success" : "error"} title={msg.text} />}

          {active && (
            <>
              <div className="two">
                <Button label={vocab("action_accept")} variant={b.status === "accepted" ? "primary" : "secondary"} isLoading={status.isPending} isDisabled={b.status === "accepted"} onClick={() => status.mutate("accepted")} />
                <Button label={vocab("action_ready")} variant={b.status === "ready" ? "primary" : "secondary"} isLoading={status.isPending} isDisabled={b.status === "ready"} onClick={() => status.mutate("ready")} />
              </div>

              <section className="stack panel" aria-label="Оплата">
                <b>Оплата и возврат</b>
                <SegmentedControl label="Вид операции" value={payKind} onChange={(v) => setPayKind(v as typeof payKind)} layout="fill">
                  <SegmentedControlItem value="payment" label="Оплата" />
                  <SegmentedControlItem value="refund" label="Возврат" />
                </SegmentedControl>
                <div className="two">
                  <NativeField label="Сумма" inputMode="decimal" value={amount} onChange={setAmount} error={payErrors.amount} placeholder="0" />
                  <NativeSelect label="Способ" value={method} onChange={setMethod} options={[{ value: "cash", label: "Наличные" }, { value: "card", label: "Карта" }, { value: "transfer", label: "Перевод" }]} />
                </div>
                <Button label={payKind === "payment" ? "Внести оплату" : "Внести возврат"} variant="primary" isLoading={pay.isPending} onClick={() => pay.mutate(payKind)} />
              </section>

              <section className="stack panel" aria-label="Перенос">
                <b>Перенести</b>
                <div className="two">
                  <NativeField label="Дата" type="date" value={date} onChange={setDate} />
                  <NativeField label="Время" type="time" step={900} value={time} onChange={setTime} />
                </div>
                <Button label="Перенести запись" variant="secondary" isLoading={move.isPending} isDisabled={!date || !time} onClick={() => move.mutate()} />
                <span className="muted" style={{ fontSize: 12.5 }}>Если время занято, запись останется на прежнем месте.</span>
              </section>

              <section className="stack panel" aria-label="Ссылка клиента">
                <b>Ссылка для клиента</b>
                <span className="muted" style={{ fontSize: 13 }}>Открывает эту запись без регистрации. Новая ссылка отключает предыдущую.</span>
                {link ? (
                  <>
                    <NativeField label="Ссылка" value={link} onChange={() => undefined} readOnly onFocus={(e) => e.currentTarget.select()} />
                    <Button label="Скопировать" variant="secondary" onClick={() => navigator.clipboard?.writeText(link).then(() => setMsg({ ok: true, text: "Ссылка скопирована." }))} />
                  </>
                ) : <Button label="Создать ссылку" variant="secondary" isLoading={getLink.isPending} onClick={() => getLink.mutate()} />}
              </section>
              <Button label="Отменить запись" variant="destructive" onClick={() => setConfirmCancel(true)} />
            </>
          )}
          {!active && b.paid_minor > 0 && (
            <section className="stack panel"><b>Возврат</b>
              <div className="two"><NativeField label="Сумма" inputMode="decimal" value={amount} onChange={setAmount} error={payErrors.amount} /><Button label="Вернуть" variant="secondary" isLoading={pay.isPending} onClick={() => pay.mutate("refund")} /></div>
            </section>
          )}
          <AlertDialog isOpen={confirmCancel} onOpenChange={setConfirmCancel} title="Отменить запись?" description="Время освободится. Клиент получит уведомление, если включил их." actionLabel="Отменить запись" cancelLabel="Оставить" actionVariant="destructive" onAction={() => cancel.mutate()} isActionLoading={cancel.isPending} />
        </>
      )}
    </AppSheet>
  );
}
