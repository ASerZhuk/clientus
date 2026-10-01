"use client";

import { Button } from "@/components/ui/Pill";
import { Banner } from "@astryxdesign/core/Banner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useStudio, useVocab } from "@/components/StudioProviders";
import { AppSheet } from "@/components/ui/AppSheet";
import { Input } from "@/components/ui/Input";
import { NativeField, NativeSelect } from "@/components/ui/Native";
import { api, ApiError, ownerApi } from "@/lib/api";
import { formatMoney, localToMinute } from "@/lib/format";
import { fieldErrors, ownerBookingSchema } from "@/lib/schemas";
import type { OwnerResource, OwnerService } from "@/lib/types";
import { refreshSchedule } from "./invalidate";

const SOFT_ERRORS = ["outside_working_hours", "too_soon", "in_the_past", "too_far"];

export function QuickBookingSheet({ isOpen, onClose, defaultDate }: { isOpen: boolean; onClose: () => void; defaultDate: string }) {
  const { slug, tenant } = useStudio();
  const vocab = useVocab();
  const contact = tenant.profile.contact;
  const qc = useQueryClient();
  const base = ownerApi(slug);
  const cat = useQuery({ queryKey: ["owner-services", slug], queryFn: () => api<{ services: OwnerService[]; resources: OwnerResource[] }>(`${base}/services`), enabled: isOpen });
  const services = (cat.data?.services ?? []).filter((s) => s.is_active);
  const [f, setF] = useState({ service_id: "", date: defaultDate, time: "10:00", resource_id: "", name: "", phone: "", car: "", plate: "", note: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ code?: string; text: string } | null>(null);
  useEffect(() => { if (isOpen) { setF((p) => ({ ...p, date: defaultDate })); setMsg(null); setErrors({}); } }, [isOpen, defaultDate]);
  useEffect(() => { if (!f.service_id && services[0]) setF((p) => ({ ...p, service_id: String(services[0].id) })); }, [services, f.service_id]);

  const create = useMutation({
    mutationFn: (outside: boolean) => {
      const parsed = ownerBookingSchema.safeParse({ name: f.name, phone: f.phone, car: f.car, plate: f.plate, note: f.note, service_id: Number(f.service_id) });
      if (!parsed.success) throw new ApiError(422, "validation_error", fieldErrors(parsed.error));
      return api(`${base}/bookings`, { method: "POST", body: { ...parsed.data, car: parsed.data.car ?? "", plate: parsed.data.plate ?? "", note: parsed.data.note ?? "", start_min: localToMinute(f.date, f.time, tenant.timezone), resource_id: f.resource_id ? Number(f.resource_id) : null, outside_hours: outside } });
    },
    onSuccess: () => { refreshSchedule(qc, slug); setF((p) => ({ ...p, name: "", phone: "", car: "", plate: "", note: "" })); onClose(); },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "validation_error" && e.detail && !Array.isArray(e.detail)) return setErrors(e.detail as Record<string, string>);
      setErrors({});
      setMsg({ code: e instanceof ApiError ? e.code : undefined, text: e instanceof ApiError ? e.message : "Не удалось создать запись." });
    },
  });
  const svc = services.find((s) => String(s.id) === f.service_id);
  return (
    <AppSheet isOpen={isOpen} onClose={onClose} label="Новая запись" title="Новая запись">
      {cat.isPending && isOpen && <span className="muted">Загрузка услуг…</span>}
      <NativeSelect label="Услуга" value={f.service_id} onChange={(v) => setF({ ...f, service_id: v })} options={services.map((s) => ({ value: String(s.id), label: `${s.name} — ${formatMoney(s.price_minor, tenant.currency)}` }))} error={errors.service_id} />
      <div className="two">
        <NativeField label="Дата" type="date" value={f.date} onChange={(v) => setF({ ...f, date: v })} />
        <NativeField label="Время" type="time" step={900} value={f.time} onChange={(v) => setF({ ...f, time: v })} />
      </div>
      <NativeSelect label={vocab("resource_one").replace(/^./, (c) => c.toUpperCase())} value={f.resource_id} onChange={(v) => setF({ ...f, resource_id: v })} options={[{ value: "", label: "Любой свободный" }, ...(cat.data?.resources ?? []).filter((r) => r.is_active && (!svc || svc.resource_ids.includes(r.id))).map((r) => ({ value: String(r.id), label: r.name }))]} />
      <Input label="Имя клиента" value={f.name} onChange={(v) => setF({ ...f, name: v })} error={errors.name} autoComplete="off" />
      <Input label="Телефон" inputMode="tel" value={f.phone} onChange={(v) => setF({ ...f, phone: v })} error={errors.phone} autoComplete="off" />
      {contact.car !== "hidden" && <Input label="Автомобиль" isOptional value={f.car} onChange={(v) => setF({ ...f, car: v })} />}
      {contact.plate !== "hidden" && <Input label="Госномер" isOptional value={f.plate} onChange={(v) => setF({ ...f, plate: v })} />}
      {contact.note !== "hidden" && <Input label="Комментарий" isOptional value={f.note} onChange={(v) => setF({ ...f, note: v })} />}
      {msg && <Banner status="error" title={msg.text} endContent={msg.code && SOFT_ERRORS.includes(msg.code) ? <Button size="sm" label="Всё равно записать" onClick={() => create.mutate(true)} /> : undefined} />}
      <Button label="Создать запись" variant="primary" size="lg" isLoading={create.isPending} onClick={() => { setMsg(null); create.mutate(false); }} />
    </AppSheet>
  );
}
