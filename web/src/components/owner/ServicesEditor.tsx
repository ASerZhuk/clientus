"use client";

import { Camera, PencilSimple, Plus } from "@phosphor-icons/react";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Switch } from "@astryxdesign/core/Switch";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Pill";
import { useStudio, useVocab } from "@/components/StudioProviders";
import { AppSheet } from "@/components/ui/AppSheet";
import { Input } from "@/components/ui/Input";
import { NativeField } from "@/components/ui/Native";
import { api, ApiError, ownerApi } from "@/lib/api";
import { WEEKDAYS_SHORT, formatDurationShort, formatMoney, hhmmToMin, minToHhmm, toMajor, toMinor } from "@/lib/format";
import { fieldErrors, serviceSchema } from "@/lib/schemas";
import type { DayEdit, ExceptionEdit, OwnerCatalog, OwnerResource, OwnerService } from "@/lib/types";

const cap = (w: string) => w.replace(/^./, (c) => c.toUpperCase());

interface OfferState {
  on: boolean;
  price: string;
  duration: string;
}

const emptyForm = (resources: OwnerResource[]) => ({
  id: 0,
  name: "",
  description: "",
  price: "",
  duration_min: "60",
  buffer_min: "0",
  is_active: true,
  offers: Object.fromEntries(resources.filter((r) => r.is_active).map((r) => [r.id, { on: true, price: "", duration: "" }])) as Record<number, OfferState>,
});

function ServiceSheet({ target, catalog, onClose }: { target: OwnerService | "new" | null; catalog: OwnerCatalog | undefined; onClose: () => void }) {
  const { slug, tenant } = useStudio();
  const vocab = useVocab();
  const qc = useQueryClient();
  const resources = (catalog?.resources ?? []).filter((r) => r.is_active);
  const perResourcePrices = catalog?.profile.features.per_resource_prices ?? false;
  const [f, setF] = useState(emptyForm(resources));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState("");

  useEffect(() => {
    if (target === null) return;
    setErrors({});
    setServerError("");
    if (target === "new") return setF(emptyForm(resources));
    const offers: Record<number, OfferState> = {};
    for (const r of resources) {
      const o = target.offers.find((x) => x.resource_id === r.id);
      offers[r.id] = { on: Boolean(o), price: o?.price_minor != null ? String(toMajor(o.price_minor)) : "", duration: o?.duration_min != null ? String(o.duration_min) : "" };
    }
    setF({ id: target.id, name: target.name, description: target.description, price: String(toMajor(target.price_minor)), duration_min: String(target.duration_min), buffer_min: String(target.buffer_min), is_active: target.is_active, offers });
  }, [target]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: () => {
      const chosen = resources.filter((r) => f.offers[r.id]?.on).map((r) => r.id);
      const parsed = serviceSchema.safeParse({ name: f.name, description: f.description, price: Number(f.price.replace(",", ".")), duration_min: Number(f.duration_min), buffer_min: Number(f.buffer_min), resource_ids: chosen, is_active: f.is_active });
      if (!parsed.success) throw new ApiError(422, "validation_error", fieldErrors(parsed.error));
      const { price, resource_ids, ...rest } = parsed.data;
      const offers = chosen.map((id) => {
        const o = f.offers[id];
        return { resource_id: id, price_minor: perResourcePrices && o.price.trim() ? toMinor(Number(o.price.replace(",", "."))) : null, duration_min: perResourcePrices && o.duration.trim() ? Number(o.duration) : null };
      });
      const body = { ...rest, price_minor: toMinor(price), keywords: [] as string[], resource_ids, offers };
      return target === "new" ? api(`${ownerApi(slug)}/services`, { method: "POST", body }) : api(`${ownerApi(slug)}/services/${f.id}`, { method: "PUT", body });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["owner-services", slug] }); qc.invalidateQueries({ queryKey: ["tenant", slug] }); onClose(); },
    onError: (e) => (e instanceof ApiError && e.code === "validation_error" && e.detail && !Array.isArray(e.detail) ? setErrors(e.detail as Record<string, string>) : setServerError(e instanceof ApiError ? e.message : "Не удалось сохранить.")),
  });
  const setOffer = (id: number, patch: Partial<OfferState>) => setF({ ...f, offers: { ...f.offers, [id]: { ...f.offers[id], ...patch } } });
  return (
    <AppSheet isOpen={target !== null} onClose={onClose} label="Услуга" title={target === "new" ? "Новая услуга" : "Услуга"}>
      <Input label="Название" value={f.name} onChange={(v) => setF({ ...f, name: v })} error={errors.name} />
      <Input label="Описание" isOptional value={f.description} onChange={(v) => setF({ ...f, description: v })} />
      <div className="two">
        <NativeField label={`Цена, ${tenant.currency}`} inputMode="decimal" value={f.price} onChange={(v) => setF({ ...f, price: v })} error={errors.price} />
        <NativeField label="Длительность, мин" inputMode="numeric" value={f.duration_min} onChange={(v) => setF({ ...f, duration_min: v })} error={errors.duration_min} />
      </div>
      {tenant.profile.features.multi_day && <p className="muted" style={{ margin: 0, fontSize: 14 }}>Длительность идёт подряд, в том числе по нескольким дням: 2880 мин = 2 дня. {cap(vocab("resource_one"))} занят всё это время.</p>}
      <NativeField label="Подготовка между клиентами, мин" inputMode="numeric" value={f.buffer_min} onChange={(v) => setF({ ...f, buffer_min: v })} error={errors.buffer_min} />
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="muted" style={{ fontSize: 15, marginBottom: 8 }}>{cap(vocab("resource_many"))}, которые оказывают услугу</legend>
        <div className="stack" style={{ gap: 10 }}>
          {resources.map((r) => (
            <div key={r.id} className="stack" style={{ gap: 8 }}>
              <label className="check-row"><input type="checkbox" checked={Boolean(f.offers[r.id]?.on)} onChange={(e) => setOffer(r.id, { on: e.target.checked })} />{r.name}</label>
              {perResourcePrices && f.offers[r.id]?.on && (
                <div className="two">
                  <NativeField label="Своя цена" inputMode="decimal" placeholder={f.price || "как у услуги"} value={f.offers[r.id].price} onChange={(v) => setOffer(r.id, { price: v })} />
                  <NativeField label="Своя длительность, мин" inputMode="numeric" placeholder={f.duration_min} value={f.offers[r.id].duration} onChange={(v) => setOffer(r.id, { duration: v })} />
                </div>
              )}
            </div>
          ))}
        </div>
        {errors.resource_ids && <span className="error-text">{errors.resource_ids}</span>}
      </fieldset>
      <Switch label="Показывать клиентам" value={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} />
      <p className="muted" style={{ margin: 0, fontSize: 14 }}>Новая цена и длительность действуют для будущих записей: уже созданные сохраняют прежние.</p>
      {serverError && <Banner status="error" title={serverError} />}
      <Button label="Сохранить" variant="primary" size="lg" width="100%" isLoading={save.isPending} onClick={() => save.mutate()} />
    </AppSheet>
  );
}

/** A master's own weekly hours and days off. */
function ScheduleSheet({ resource, onClose }: { resource: OwnerResource | null; onClose: () => void }) {
  const { slug } = useStudio();
  const qc = useQueryClient();
  const [own, setOwn] = useState(false);
  const [days, setDays] = useState<DayEdit[]>([]);
  const [exc, setExc] = useState<ExceptionEdit[]>([]);
  const [nx, setNx] = useState({ date: "", note: "" });
  useEffect(() => {
    if (!resource) return;
    setOwn(resource.has_own_hours);
    setDays(resource.hours_edit.map((d) => ({ ...d })));
    setExc(resource.exceptions.map((e) => ({ ...e })));
  }, [resource]);
  const save = useMutation({
    mutationFn: () => api(`${ownerApi(slug)}/resources/${resource!.id}/schedule`, { method: "PUT", body: { use_studio_hours: !own, days: own ? days : [], exceptions: exc } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["owner-services", slug] }); qc.invalidateQueries({ queryKey: ["slots", slug] }); onClose(); },
  });
  const set = (i: number, patch: Partial<DayEdit>) => setDays(days.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  return (
    <AppSheet isOpen={resource !== null} onClose={onClose} label="Расписание" title={resource ? `Расписание: ${resource.name}` : "Расписание"}>
      <Switch label="Свой график (иначе — общий график студии)" value={own} onChange={setOwn} />
      {own && days.map((d, i) => (
        <div key={d.weekday} className="stack" style={{ gap: 6 }}>
          <div className="row-between"><b>{WEEKDAYS_SHORT[d.weekday]}</b><Switch label="Выходной" labelPosition="start" value={d.is_closed} onChange={(v) => set(i, { is_closed: v })} /></div>
          {!d.is_closed && (
            <div className="two">
              <NativeField label="С" type="time" step={900} value={minToHhmm(d.open_min)} onChange={(v) => v && set(i, { open_min: hhmmToMin(v) })} />
              <NativeField label="До" type="time" step={900} value={minToHhmm(d.close_min)} onChange={(v) => v && set(i, { close_min: hhmmToMin(v) })} />
            </div>
          )}
        </div>
      ))}
      <b style={{ marginTop: 8 }}>Отпуск и выходные дни</b>
      {exc.map((e) => (
        <div key={e.date} className="row-between panel">
          <span>{e.date}{e.note ? ` · ${e.note}` : ""}</span>
          <Button label="Убрать" size="sm" variant="ghost" onClick={() => setExc(exc.filter((x) => x.date !== e.date))} />
        </div>
      ))}
      <div className="two" style={{ alignItems: "end" }}>
        <NativeField label="Дата" type="date" value={nx.date} onChange={(v) => setNx({ ...nx, date: v })} />
        <Input label="Комментарий" isOptional value={nx.note} onChange={(v) => setNx({ ...nx, note: v })} />
      </div>
      <Button label="Добавить выходной" variant="secondary" isDisabled={!nx.date || exc.some((e) => e.date === nx.date)} onClick={() => { setExc([...exc, { date: nx.date, is_closed: true, open_min: null, close_min: null, note: nx.note }].sort((a, b) => a.date.localeCompare(b.date))); setNx({ date: "", note: "" }); }} />
      {save.isError && <span className="error-text" role="alert">{(save.error as ApiError).message}</span>}
      <Button label="Сохранить расписание" variant="primary" size="lg" width="100%" isLoading={save.isPending} onClick={() => save.mutate()} />
    </AppSheet>
  );
}

function ResourceCard({ r, catalog, onSchedule }: { r: OwnerResource; catalog: OwnerCatalog; onSchedule: (r: OwnerResource) => void }) {
  const { slug } = useStudio();
  const qc = useQueryClient();
  const [name, setName] = useState(r.name);
  const [description, setDescription] = useState(r.description);
  const fileRef = useRef<HTMLInputElement>(null);
  const features = catalog.profile.features;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["owner-services", slug] }); qc.invalidateQueries({ queryKey: ["tenant", slug] }); };
  const upd = useMutation({ mutationFn: (body: { name: string; description: string; is_active: boolean }) => api(`${ownerApi(slug)}/resources/${r.id}`, { method: "PUT", body }), onSuccess: refresh });
  const photo = useMutation({ mutationFn: (file: File) => { const form = new FormData(); form.append("file", file); return api(`${ownerApi(slug)}/resources/${r.id}/photo`, { method: "POST", form }); }, onSuccess: refresh });
  const dirty = name.trim() !== "" && (name !== r.name || description !== r.description);
  return (
    <div className="panel stack">
      <div className="row" style={{ alignItems: "flex-start" }}>
        {features.resource_profiles && (
          <span className="avatar avatar-lg" style={{ width: 72, height: 72 }}>{r.photo_url ? /* eslint-disable-next-line @next/next/no-img-element */ <img src={r.photo_url} alt="" /> : r.name.slice(0, 1)}</span>
        )}
        <div className="grow stack" style={{ gap: 8 }}>
          <Input label="Название" value={name} onChange={setName} />
          {features.resource_profiles && <Input label="Специализация" isOptional value={description} onChange={setDescription} />}
        </div>
      </div>
      <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
        <Button label="Сохранить" size="sm" variant="secondary" isDisabled={!dirty} isLoading={upd.isPending} onClick={() => upd.mutate({ name, description, is_active: r.is_active })} />
        {features.resource_profiles && (
          <>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) photo.mutate(f); }} />
            <Button label="Фото" size="sm" variant="secondary" icon={<Camera />} isLoading={photo.isPending} onClick={() => fileRef.current?.click()} />
          </>
        )}
        {features.per_resource_hours && <Button label={r.has_own_hours ? "Свой график" : "График студии"} size="sm" variant="secondary" onClick={() => onSchedule(r)} />}
        <Switch label={r.is_active ? "Принимает записи" : "Не принимает записи"} value={r.is_active} onChange={(v) => upd.mutate({ name: r.name, description: r.description, is_active: v })} />
      </div>
      {(upd.isError || photo.isError) && <span className="error-text" role="alert">{((upd.error ?? photo.error) as ApiError).message}</span>}
    </div>
  );
}

export function ServicesEditor() {
  const { slug, tenant } = useStudio();
  const vocab = useVocab();
  const qc = useQueryClient();
  const [target, setTarget] = useState<OwnerService | "new" | null>(null);
  const [scheduleFor, setScheduleFor] = useState<OwnerResource | null>(null);
  const [newName, setNewName] = useState("");
  const q = useQuery({ queryKey: ["owner-services", slug], queryFn: () => api<OwnerCatalog>(`${ownerApi(slug)}/services`) });
  const add = useMutation({
    mutationFn: () => api(`${ownerApi(slug)}/resources`, { method: "POST", body: { name: newName.trim(), description: "", is_active: true } }),
    onSuccess: () => { setNewName(""); qc.invalidateQueries({ queryKey: ["owner-services", slug] }); },
  });
  const atLimit = tenant.profile.type === "beauty_master";
  return (
    <div className="page stack" style={{ gap: 18 }}>
      <div className="row-between"><h1 className="owner-title" style={{ marginTop: 24 }}>Услуги</h1><Button label="Добавить" icon={<Plus weight="bold" />} variant="primary" size="sm" onClick={() => setTarget("new")} /></div>
      {q.isPending && <Skeleton height={220} />}
      {q.isError && <Banner status="error" title="Услуги не загрузились" description={(q.error as ApiError).message} endContent={<Button size="sm" label="Повторить" onClick={() => q.refetch()} />} />}
      {q.data && q.data.services.length === 0 && <EmptyState title="Услуг пока нет" description="Добавьте первую услугу, чтобы клиенты могли записаться." actions={<Button label="Добавить услугу" onClick={() => setTarget("new")} />} />}
      {q.data && q.data.services.length > 0 && (
        <div className="svc-panel">
          {q.data.services.map((s) => (
            <button key={s.id} type="button" className="service-row" onClick={() => setTarget(s)} style={s.is_active ? undefined : { opacity: 0.5 }}>
              <span className="grow"><div className="service-name">{s.name}{s.is_active ? "" : " · скрыта"}</div><div className="service-desc">{formatDurationShort(s.duration_min)}{s.buffer_min ? ` · подготовка ${s.buffer_min} мин` : ""}{tenant.profile.features.choose_resource ? ` · ${s.offers.length} мастеров` : ""}</div></span>
              <span className="price">{formatMoney(s.price_minor, tenant.currency)}</span>
              <PencilSimple size={18} aria-hidden />
            </button>
          ))}
        </div>
      )}
      <h2 className="section-title" style={{ marginTop: 18 }}>{vocab("resource_section")}</h2>
      {q.data?.resources.map((r) => <ResourceCard key={`${r.id}-${r.name}-${r.description}-${r.is_active}-${r.photo_url}`} r={r} catalog={q.data} onSchedule={setScheduleFor} />)}
      {!atLimit && (
        <div className="panel stack">
          <Input label={vocab("resource_new")} value={newName} onChange={setNewName} placeholder={tenant.profile.kind === "person" ? "Имя мастера" : "Например: Подъёмник 2"} />
          <Button label="Добавить" variant="secondary" isDisabled={!newName.trim()} isLoading={add.isPending} onClick={() => add.mutate()} />
          {add.isError && <span className="error-text" role="alert">{(add.error as ApiError).message}</span>}
        </div>
      )}
      <ServiceSheet target={target} catalog={q.data} onClose={() => setTarget(null)} />
      <ScheduleSheet resource={scheduleFor} onClose={() => setScheduleFor(null)} />
    </div>
  );
}
