"use client";

import { Button, IconButton } from "@/components/ui/Pill";
import { ArrowUpRight, X } from "@phosphor-icons/react";
import { Banner } from "@astryxdesign/core/Banner";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useProfile, useStudio, useVocab } from "@/components/StudioProviders";
import { AppSheet } from "@/components/ui/AppSheet";
import { Input } from "@/components/ui/Input";
import { api, ApiError, studioApi } from "@/lib/api";
import { navigateFromSheet } from "@/lib/hooks";
import { saveBooking } from "@/lib/booking-store";
import { dateKeyOf, dayNumber, newKey, formatDuration, formatDurationShort, formatMoney, formatPrice, fullDateLabel, longDayLabel, monthShort, timeOf, weekdayShort } from "@/lib/format";
import { contactSchemaFor, fieldErrors } from "@/lib/schemas";
import type { CreatedBooking, SlotsResponse } from "@/lib/types";
import { BookingDetails } from "./BookingDetails";

type StepKey = "service" | "master" | "date" | "time" | "details";
const TITLES: Record<StepKey, string> = { service: "Выберите услугу", master: "Выберите мастера", date: "Выберите дату", time: "Выберите время", details: "Ваши данные" };

export interface BookingPreset {
  serviceId?: number;
  start?: number;
}

export function BookingSheet({ isOpen, onClose, preset }: { isOpen: boolean; onClose: () => void; preset: BookingPreset | null }) {
  const { slug, tenant, href } = useStudio();
  const qc = useQueryClient();
  const router = useRouter();
  const tz = tenant.timezone;
  const profile = useProfile();
  const vocab = useVocab();
  const services = tenant.services.filter((s) => s.bookable);
  const steps: StepKey[] = profile.features.choose_resource ? ["service", "master", "date", "time", "details"] : ["service", "date", "time", "details"];
  const [stepKey, setStepKey] = useState<StepKey>("service");
  const step = steps.indexOf(stepKey) + 1;
  const go = (k: StepKey) => setStepKey(k);
  const back = () => setStepKey(steps[Math.max(0, steps.indexOf(stepKey) - 1)]);
  const [resourceId, setResourceId] = useState<number | null>(null); // null = any free master
  const [serviceId, setServiceId] = useState<number | null>(null);
  const [dateKey, setDateKey] = useState<string | null>(null);
  const [slot, setSlot] = useState<number | null>(null);
  const [form, setForm] = useState({ name: "", phone: "", car: "", plate: "", note: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState("");
  const [done, setDone] = useState<CreatedBooking | null>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const keyRef = useRef<{ payload: string; key: string } | null>(null);
  const pendingStart = useRef<number | null>(null);

  // (Re)open: start fresh, or jump ahead when the assistant / a service link pre-selected something
  useEffect(() => {
    if (!isOpen) return;
    setDone(null);
    setServerError("");
    setErrors({});
    setSlot(null);
    setResourceId(null);
    if (preset?.serviceId && services.some((s) => s.id === preset.serviceId)) {
      setServiceId(preset.serviceId);
      if (preset.start && !profile.features.choose_resource) {
        pendingStart.current = preset.start;
        setDateKey(dateKeyOf(preset.start, tz));
        setStepKey("time");
      } else {
        setDateKey(null);
        setStepKey(profile.features.choose_resource ? "master" : "date");
      }
    } else {
      setServiceId(null);
      setDateKey(null);
      setStepKey("service");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, preset]);

  useEffect(() => { titleRef.current?.focus({ preventScroll: true }); }, [stepKey, done, isOpen]);

  const service = services.find((s) => s.id === serviceId) ?? null;
  const offers = service?.offers ?? [];
  const masters = tenant.resources.filter((r) => offers.some((o) => o.resource_id === r.id));
  const chosenOffer = resourceId !== null ? offers.find((o) => o.resource_id === resourceId) : undefined;
  const price = chosenOffer?.price_minor ?? service?.price_minor ?? 0;
  const slotsQ = useQuery({
    queryKey: ["slots", slug, serviceId, resourceId],
    queryFn: () => api<SlotsResponse>(`${studioApi(slug)}/slots?service_id=${serviceId}&days=21${resourceId !== null ? `&resource_id=${resourceId}` : ""}`),
    enabled: isOpen && serviceId !== null,
    staleTime: 15_000,
  });
  const days = useMemo(() => Object.entries(slotsQ.data?.days ?? {}), [slotsQ.data]);
  const daySlots = dateKey ? (slotsQ.data?.days[dateKey] ?? []) : [];

  useEffect(() => {
    if (pendingStart.current && slotsQ.data) {
      const start = pendingStart.current;
      pendingStart.current = null;
      const item = slotsQ.data.days[dateKeyOf(start, tz)]?.find((s) => s.start_min === start);
      if (item?.available) {
        setSlot(start);
        setStepKey("details");
      } else setStepKey("date");
    }
  }, [slotsQ.data, tz]);

  const submit = useMutation({
    mutationFn: async () => {
      const parsed = contactSchemaFor(profile.contact).safeParse(form);
      if (!parsed.success) throw new ApiError(422, "validation_error", fieldErrors(parsed.error));
      const body = { ...parsed.data, car: parsed.data.car ?? "", plate: parsed.data.plate ?? "", note: parsed.data.note ?? "", service_id: serviceId!, start_min: slot!, ...(resourceId !== null ? { resource_id: resourceId } : {}) };
      const payload = JSON.stringify(body);
      // same input = same Idempotency-Key: a double tap or a retry can never create a second booking
      if (keyRef.current?.payload !== payload) keyRef.current = { payload, key: newKey() };
      return api<CreatedBooking>(`${studioApi(slug)}/bookings`, { method: "POST", body, idempotencyKey: keyRef.current.key });
    },
    onSuccess: (r) => {
      saveBooking(slug, { id: r.booking.id, token: r.access_token, service_name: r.booking.service_name, start_min: r.booking.start_min });
      qc.invalidateQueries({ queryKey: ["slots", slug] });
      setDone(r);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "validation_error" && e.detail && !Array.isArray(e.detail)) return setErrors(e.detail as Record<string, string>);
      setServerError(e instanceof ApiError ? e.message : "Не удалось записаться.");
      if (e instanceof ApiError && ["slot_unavailable", "too_soon", "outside_working_hours"].includes(e.code)) {
        setSlot(null);
        qc.invalidateQueries({ queryKey: ["slots", slug] });
        setStepKey("time");
      }
    },
  });

  const confirm = () => {
    setServerError("");
    const parsed = contactSchemaFor(profile.contact).safeParse(form);
    if (!parsed.success) return setErrors(fieldErrors(parsed.error));
    setErrors({});
    submit.mutate();
  };

  const enabled = tenant.booking_enabled;
  const title = done ? "Вы записаны" : enabled ? TITLES[stepKey] : "Запись недоступна";
  return (
    <AppSheet isOpen={isOpen} onClose={onClose} label={title} bare>
      <div className="sheet-head">
        <h2 className="sheet-title" tabIndex={-1} ref={titleRef}>{title}</h2>
        <IconButton label="Закрыть" icon={<X size={26} />} variant="ghost" onClick={onClose} />
      </div>
      {!done && !tenant.booking_enabled && (
        <div className="stack" style={{ marginTop: 16 }}>
          <Banner status="warning" title="Онлайн-запись временно недоступна" description="Свяжитесь со студией по телефону — вам подберут время." />
          {tenant.phone && <Button label={tenant.phone} href={`tel:${tenant.phone.replace(/[^\d+]/g, "")}`} variant="primary" size="lg" width="100%" />}
        </div>
      )}
      {!done && tenant.booking_enabled && (
        <>
          <p className="sheet-step">Шаг {step} из {steps.length}</p>
          <div className="steps" aria-hidden>
            {steps.map((k, i) => <i key={k} className={i < step ? "done" : ""} />)}
          </div>
        </>
      )}

      {done && (
        <div className="stack" style={{ marginTop: 16 }}>
          <Banner status="success" title="Запись создана" description="Сохраните её в календарь или включите напоминание. Ссылка хранится в разделе «Моя запись»." />
          <BookingDetails booking={done.booking} token={done.access_token} onChanged={(b) => setDone({ ...done, booking: b })} />
          <div className="form-actions">
            <Button label="Моя запись" variant="secondary" onClick={() => navigateFromSheet(router.push, href("/my"))} />
            <Button label="Закрыть" variant="ghost" onClick={onClose} />
          </div>
        </div>
      )}

      {!done && enabled && stepKey === "service" && (
        <div className="svc-panel" role="radiogroup" aria-label="Услуга">
          {services.map((s) => (
            <button key={s.id} type="button" role="radio" aria-checked={serviceId === s.id} className="svc-row"
              onClick={() => { if (serviceId !== s.id) { setServiceId(s.id); setDateKey(null); setSlot(null); setResourceId(null); } go(profile.features.choose_resource ? "master" : "date"); }}>
              <span className="grow"><div className="name">{s.name}</div><div className="meta">{formatDurationShort(s.duration_min)}</div></span>
              <span className="side"><div className="price">{s.price_varies && s.price_minor ? "от " : ""}{formatPrice(s.price_minor, tenant.currency)}</div><div className="choose">Выбрать</div></span>
              <ArrowUpRight size={22} aria-hidden />
            </button>
          ))}
          {services.length === 0 && <p className="muted" style={{ padding: 16 }}>Онлайн-запись пока недоступна. Позвоните в студию.</p>}
        </div>
      )}

      {!done && enabled && stepKey === "master" && service && (
        <div className="svc-panel" role="radiogroup" aria-label={vocab("resource_one")}>
          <button type="button" role="radio" aria-checked={resourceId === null} className="svc-row" onClick={() => { setResourceId(null); setDateKey(null); setSlot(null); go("date"); }}>
            <span className="grow"><div className="name">Любой свободный</div><div className="meta">Подберём ближайшее время</div></span>
            <span className="side"><div className="price">{service.price_varies && service.price_minor ? "от " : ""}{formatPrice(service.price_minor, tenant.currency)}</div></span>
            <ArrowUpRight size={22} aria-hidden />
          </button>
          {masters.map((m) => {
            const o = offers.find((x) => x.resource_id === m.id)!;
            return (
              <button key={m.id} type="button" role="radio" aria-checked={resourceId === m.id} className="svc-row" onClick={() => { setResourceId(m.id); setDateKey(null); setSlot(null); go("date"); }}>
                <span className="avatar">{m.photo_url ? /* eslint-disable-next-line @next/next/no-img-element */ <img src={m.photo_url} alt="" /> : m.name.slice(0, 1)}</span>
                <span className="grow"><div className="name">{m.name}</div><div className="meta">{m.description || formatDurationShort(o.duration_min)}</div></span>
                <span className="side"><div className="price">{formatPrice(o.price_minor, tenant.currency)}</div><div className="choose">{formatDurationShort(o.duration_min)}</div></span>
                <ArrowUpRight size={22} aria-hidden />
              </button>
            );
          })}
        </div>
      )}

      {!done && enabled && (stepKey === "date" || stepKey === "time") && (
        <>
          {slotsQ.isPending && <div className="stack"><Skeleton height={72} /><Skeleton height={140} /></div>}
          {slotsQ.isError && (
            <Banner status="error" title="Не удалось загрузить время" description={(slotsQ.error as ApiError).message} endContent={<Button label="Повторить" size="sm" onClick={() => slotsQ.refetch()} />} />
          )}
          {slotsQ.data && (
            <>
              {service && <p className="muted" style={{ margin: "0 0 12px" }}>{service.name} · {formatDuration(chosenOffer?.duration_min ?? service.duration_min)}{resourceId !== null ? ` · ${tenant.resources.find((r) => r.id === resourceId)?.name}` : ""}</p>}
              <div className="date-strip" role="group" aria-label="Дата">
                {days.map(([key, items]) => {
                  const free = items.some((s) => s.available);
                  return (
                    <button key={key} type="button" className="date-chip" aria-pressed={dateKey === key} disabled={!free}
                      aria-label={`${fullDateLabel(key)}${free ? "" : ", нет свободного времени"}`}
                      onClick={() => { setDateKey(key); setSlot(null); go("time"); }}>
                      <small>{weekdayShort(key)}</small><b>{dayNumber(key)}</b><small>{monthShort(key)}</small>
                    </button>
                  );
                })}
              </div>
              {days.every(([, items]) => !items.some((s) => s.available)) && <p className="muted">Ближайшие три недели свободного времени нет — позвоните в студию.</p>}
            </>
          )}
          {stepKey === "time" && dateKey && slotsQ.data && (
            <div className="stack" style={{ marginTop: 8 }}>
              {daySlots.length === 0 ? <p className="muted">В этот день студия закрыта.</p> : (
                <div className="slot-grid" role="group" aria-label="Время">
                  {daySlots.map((s) => (
                    <button key={s.start_min} type="button" className="slot" disabled={!s.available} aria-pressed={slot === s.start_min}
                      aria-label={`${timeOf(s.start_min, tz)}${s.available ? "" : ", занято"}`} onClick={() => { setSlot(s.start_min); go("details"); }}>
                      {timeOf(s.start_min, tz)}
                    </button>
                  ))}
                </div>
              )}
              <div className="legend"><span>свободно</span><span className="busy">занято</span><span className="sel">выбрано</span></div>
              {service && (chosenOffer?.duration_min ?? service.duration_min) >= 1440 && <p className="muted" style={{ fontSize: 14 }}>Автомобиль останется в студии на {formatDuration(service.duration_min)}: эти дни будут заняты.</p>}
            </div>
          )}
        </>
      )}

      {!done && enabled && stepKey === "details" && service && slot && (
        <form className="stack" noValidate onSubmit={(e) => { e.preventDefault(); confirm(); }}>
          <dl className="summary panel" style={{ margin: 0 }}>
            <div><dt>Услуга</dt><dd>{service.name}</dd></div>
            {profile.features.choose_resource && <div><dt>Мастер</dt><dd>{resourceId !== null ? tenant.resources.find((r) => r.id === resourceId)?.name : "любой свободный"}</dd></div>}
            <div><dt>Когда</dt><dd>{longDayLabel(slot, tz)}, {timeOf(slot, tz)}</dd></div>
            <div><dt>Стоимость</dt><dd>{formatPrice(price, tenant.currency)}</dd></div>
          </dl>
          <Input label="Имя" name="name" autoComplete="name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} error={errors.name} />
          <Input label="Телефон" name="tel" inputMode="tel" autoComplete="tel" placeholder="+7 900 123-45-67" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} error={errors.phone} />
          {profile.contact.car !== "hidden" && <Input label="Автомобиль" name="car" placeholder="Например, BMW X5" value={form.car} onChange={(v) => setForm({ ...form, car: v })} error={errors.car} isOptional={profile.contact.car === "optional"} />}
          {profile.contact.plate !== "hidden" && <Input label="Госномер" name="plate" isOptional value={form.plate} onChange={(v) => setForm({ ...form, plate: v })} error={errors.plate} />}
          {profile.contact.note !== "hidden" && <Input label="Комментарий" name="note" isOptional value={form.note} onChange={(v) => setForm({ ...form, note: v })} error={errors.note} placeholder="Например: пожелания к услуге" />}
          <p className="muted" style={{ fontSize: 14, margin: 0 }}>Бесплатная отмена — не позднее чем за {tenant.rules.cancel_before_hours} ч до начала.</p>
          {serverError && <Banner status="error" title="Запись не создана" description={serverError} />}
          <button className="pill pill-primary" type="submit" disabled={submit.isPending}>{submit.isPending ? "Записываем…" : "Подтвердить запись"}</button>
        </form>
      )}

      {!done && enabled && step > 1 && (
        <div className="form-actions">
          <Button label="Назад" variant="ghost" onClick={back} />
        </div>
      )}
    </AppSheet>
  );
}
