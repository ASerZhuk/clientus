"use client";

import { Button } from "@/components/ui/Pill";
import { BellRinging, Camera, Copy, SignOut, Trash } from "@phosphor-icons/react";
import { Banner } from "@astryxdesign/core/Banner";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Switch } from "@astryxdesign/core/Switch";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useStudio } from "@/components/StudioProviders";
import { AppSheet } from "@/components/ui/AppSheet";
import { Input } from "@/components/ui/Input";
import { NativeField } from "@/components/ui/Native";
import { api, ApiError, ownerApi } from "@/lib/api";
import { WEEKDAYS_SHORT, formatDuration, hhmmToMin, minToHhmm } from "@/lib/format";
import { detectPush, subscribePush, unsubscribePush, currentEndpoint, type PushSupport } from "@/lib/push";
import { fieldErrors, settingsSchema } from "@/lib/schemas";
import type { GalleryItem, OwnerSettings, PushConfig } from "@/lib/types";
import { useOwner } from "./OwnerShell";
import { TariffCard } from "./Subscription";

const key = (slug: string) => ["owner-settings", slug];
function useSettings() {
  const { slug } = useStudio();
  return useQuery({ queryKey: key(slug), queryFn: () => api<OwnerSettings>(`${ownerApi(slug)}/settings`) });
}
function useAfterSave() {
  const { slug } = useStudio();
  const qc = useQueryClient();
  return () => { qc.invalidateQueries({ queryKey: key(slug) }); qc.invalidateQueries({ queryKey: ["tenant", slug] }); };
}

function Save({ mutation, label = "Сохранить" }: { mutation: { isPending: boolean; isSuccess: boolean; isError: boolean; error: unknown; mutate: () => void }; label?: string }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      {mutation.isError && <span className="error-text" role="alert">{mutation.error instanceof ApiError ? mutation.error.message : "Не удалось сохранить."}</span>}
      {mutation.isSuccess && <span style={{ color: "#3ddc84", fontSize: 14 }} role="status">Сохранено</span>}
      <Button label={label} variant="primary" isLoading={mutation.isPending} onClick={() => mutation.mutate()} />
    </div>
  );
}

function Basics({ s }: { s: OwnerSettings }) {
  const { slug } = useStudio();
  const after = useAfterSave();
  const [f, setF] = useState({ name: s.name, tagline: s.tagline, description: s.description, phone: s.phone, address: s.address, map_url: s.map_url, info_cards: s.info_cards.map((c) => ({ ...c })) });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () => {
      const parsed = settingsSchema.safeParse(f);
      if (!parsed.success) { setErrors(fieldErrors(parsed.error)); throw new ApiError(422, "validation_error"); }
      setErrors({});
      return api(`${ownerApi(slug)}/settings`, { method: "PATCH", body: parsed.data });
    },
    onSuccess: after,
  });
  const card = (i: number, patch: Partial<{ title: string; text: string }>) => setF({ ...f, info_cards: f.info_cards.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Основное</h2>
      <Input label="Название" value={f.name} onChange={(v) => setF({ ...f, name: v })} error={errors.name} />
      <Input label="Краткое описание" isOptional value={f.tagline} onChange={(v) => setF({ ...f, tagline: v })} error={errors.tagline} />
      <Input label="Телефон" inputMode="tel" value={f.phone} onChange={(v) => setF({ ...f, phone: v })} error={errors.phone} />
      <Input label="Адрес" value={f.address} onChange={(v) => setF({ ...f, address: v })} error={errors.address} />
      <Input label="Ссылка на карту" isOptional value={f.map_url} onChange={(v) => setF({ ...f, map_url: v })} error={errors.map_url} placeholder="https://…" />
      <b style={{ marginTop: 8 }}>Три карточки на главной</b>
      {f.info_cards.map((c, i) => (
        <div className="stack" key={i} style={{ gap: 8 }}>
          <Input label={`Карточка ${i + 1}: заголовок`} value={c.title} onChange={(v) => card(i, { title: v })} error={errors[`info_cards.${i}.title`]} />
          <Input label={`Карточка ${i + 1}: текст`} value={c.text} onChange={(v) => card(i, { text: v })} error={errors[`info_cards.${i}.text`]} />
        </div>
      ))}
      <Save mutation={save} />
    </div>
  );
}

function Pictures({ s }: { s: OwnerSettings }) {
  const { slug } = useStudio();
  const after = useAfterSave();
  const logoRef = useRef<HTMLInputElement>(null);
  const heroRef = useRef<HTMLInputElement>(null);
  const up = useMutation({
    mutationFn: ({ kind, file }: { kind: "logo" | "hero"; file: File }) => { const form = new FormData(); form.append("file", file); return api(`${ownerApi(slug)}/${kind}`, { method: "POST", form }); },
    onSuccess: after,
  });
  const pick = (kind: "logo" | "hero") => (e: React.ChangeEvent<HTMLInputElement>) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) up.mutate({ kind, file }); };
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Логотип и главное фото</h2>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="photo-thumb" style={{ background: "#111" }}>{s.logo_url && <Image src={s.logo_url} alt="Логотип" fill unoptimized style={{ objectFit: "contain" }} />}</div>
        <div className="photo-thumb" style={{ width: 150 }}>{s.hero_url && <Image src={s.hero_url} alt="Главное фото" fill unoptimized />}</div>
      </div>
      <input ref={logoRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={pick("logo")} />
      <input ref={heroRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={pick("hero")} />
      <div className="stack">
        <Button label="Сменить логотип" icon={<Camera />} variant="secondary" isLoading={up.isPending && up.variables?.kind === "logo"} onClick={() => logoRef.current?.click()} />
        <Button label="Сменить главное фото" icon={<Camera />} variant="secondary" isLoading={up.isPending && up.variables?.kind === "hero"} onClick={() => heroRef.current?.click()} />
      </div>
      {up.isError && <span className="error-text" role="alert">{(up.error as ApiError).message}</span>}
      <span className="muted" style={{ fontSize: 13 }}>Иконка установки на телефон обновится вместе с логотипом.</span>
    </div>
  );
}

function GalleryManager({ items }: { items: GalleryItem[] }) {
  const { slug } = useStudio();
  const after = useAfterSave();
  const addRef = useRef<HTMLInputElement>(null);
  const replaceRef = useRef<HTMLInputElement>(null);
  const [replaceId, setReplaceId] = useState<number | null>(null);
  const [captionFor, setCaptionFor] = useState<GalleryItem | null>(null);
  const [caption, setCaption] = useState("");
  const [newCaption, setNewCaption] = useState("");
  const add = useMutation({ mutationFn: (file: File) => { const form = new FormData(); form.append("file", file); form.append("caption", newCaption); return api(`${ownerApi(slug)}/gallery`, { method: "POST", form }); }, onSuccess: () => { setNewCaption(""); after(); } });
  const replace = useMutation({ mutationFn: ({ id, file }: { id: number; file: File }) => { const form = new FormData(); form.append("file", file); return api(`${ownerApi(slug)}/gallery/${id}/photo`, { method: "PUT", form }); }, onSuccess: after });
  const rename = useMutation({ mutationFn: () => api(`${ownerApi(slug)}/gallery/${captionFor!.id}`, { method: "PATCH", body: { caption } }), onSuccess: () => { setCaptionFor(null); after(); } });
  const del = useMutation({ mutationFn: (id: number) => api(`${ownerApi(slug)}/gallery/${id}`, { method: "DELETE" }), onSuccess: after });
  const err = [add, replace, rename, del].find((m) => m.isError)?.error as ApiError | undefined;
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Фото работ</h2>
      <input ref={addRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) add.mutate(f); }} />
      <input ref={replaceRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f && replaceId !== null) replace.mutate({ id: replaceId, file: f }); }} />
      {items.map((g) => (
        <div key={g.id} className="row" style={{ alignItems: "flex-start" }}>
          <div className="photo-thumb"><Image src={g.url} alt={g.caption || "Работа"} fill unoptimized /></div>
          <div className="grow stack" style={{ gap: 8 }}>
            <span style={{ fontSize: 14 }}>{g.caption || <span className="muted">Без подписи</span>}</span>
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              <Button label="Заменить фото" size="sm" variant="secondary" isLoading={replace.isPending && replace.variables?.id === g.id} onClick={() => { setReplaceId(g.id); replaceRef.current?.click(); }} />
              <Button label="Подпись" size="sm" variant="secondary" onClick={() => { setCaptionFor(g); setCaption(g.caption); }} />
              <Button label="Удалить" size="sm" variant="ghost" icon={<Trash />} isLoading={del.isPending && del.variables === g.id} onClick={() => del.mutate(g.id)} />
            </div>
          </div>
        </div>
      ))}
      {items.length === 0 && <span className="muted">Фотографий пока нет.</span>}
      <div className="stack panel" style={{ background: "transparent" }}>
        <Input label="Подпись новой карточки" isOptional value={newCaption} onChange={setNewCaption} />
        <Button label="Добавить новую карточку" variant="primary" isLoading={add.isPending} onClick={() => addRef.current?.click()} />
      </div>
      {err && <span className="error-text" role="alert">{err.message}</span>}
      <AppSheet isOpen={captionFor !== null} onClose={() => setCaptionFor(null)} label="Подпись к фото" title="Подпись к фото" height="capped">
        <Input label="Подпись" value={caption} onChange={setCaption} />
        <Button label="Сохранить подпись" variant="primary" isLoading={rename.isPending} onClick={() => rename.mutate()} />
      </AppSheet>
    </div>
  );
}

function HoursEditor({ s }: { s: OwnerSettings }) {
  const { slug } = useStudio();
  const after = useAfterSave();
  const [days, setDays] = useState(s.hours_edit);
  const [exc, setExc] = useState(s.exceptions);
  const [nx, setNx] = useState({ date: "", closed: true, open: "10:00", close: "15:00", note: "" });
  const save = useMutation({
    mutationFn: () => api(`${ownerApi(slug)}/hours`, { method: "PUT", body: { days, exceptions: exc } }),
    onSuccess: after,
  });
  const set = (i: number, patch: Partial<(typeof days)[number]>) => setDays(days.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Часы приёма и выходные</h2>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Это моменты, когда можно привезти машину. Долгие работы могут идти и после закрытия.</p>
      {days.map((d, i) => (
        <div key={d.weekday} className="stack" style={{ gap: 6 }}>
          <div className="row-between"><b>{WEEKDAYS_SHORT[d.weekday]}</b><Switch label={`${WEEKDAYS_SHORT[d.weekday]}: выходной`} isLabelHidden={false} labelPosition="start" value={d.is_closed} onChange={(v) => set(i, { is_closed: v })} /></div>
          {!d.is_closed && (
            <div className="two">
              <NativeField label="С" type="time" step={900} value={minToHhmm(d.open_min)} onChange={(v) => v && set(i, { open_min: hhmmToMin(v) })} />
              <NativeField label="До" type="time" step={900} value={minToHhmm(d.close_min)} onChange={(v) => v && set(i, { close_min: hhmmToMin(v) })} />
            </div>
          )}
        </div>
      ))}
      <b style={{ marginTop: 8 }}>Особые дни</b>
      {exc.map((e) => (
        <div key={e.date} className="row-between panel">
          <span>{e.date}: {e.is_closed ? "выходной" : `${minToHhmm(e.open_min ?? 0)}–${minToHhmm(e.close_min ?? 0)}`}{e.note ? ` · ${e.note}` : ""}</span>
          <Button label="Убрать" size="sm" variant="ghost" onClick={() => setExc(exc.filter((x) => x.date !== e.date))} />
        </div>
      ))}
      <div className="stack panel" style={{ background: "transparent" }}>
        <NativeField label="Дата" type="date" value={nx.date} onChange={(v) => setNx({ ...nx, date: v })} />
        <Switch label="Выходной" value={nx.closed} onChange={(v) => setNx({ ...nx, closed: v })} />
        {!nx.closed && <div className="two"><NativeField label="С" type="time" step={900} value={nx.open} onChange={(v) => setNx({ ...nx, open: v })} /><NativeField label="До" type="time" step={900} value={nx.close} onChange={(v) => setNx({ ...nx, close: v })} /></div>}
        <Input label="Комментарий" isOptional value={nx.note} onChange={(v) => setNx({ ...nx, note: v })} />
        <Button label="Добавить особый день" variant="secondary" isDisabled={!nx.date || exc.some((e) => e.date === nx.date)} onClick={() => { setExc([...exc, { date: nx.date, is_closed: nx.closed, open_min: nx.closed ? null : hhmmToMin(nx.open), close_min: nx.closed ? null : hhmmToMin(nx.close), note: nx.note }].sort((a, b) => a.date.localeCompare(b.date))); setNx({ ...nx, date: "", note: "" }); }} />
      </div>
      <Save mutation={save} label="Сохранить график" />
    </div>
  );
}

function Rules({ s }: { s: OwnerSettings }) {
  const { slug } = useStudio();
  const after = useAfterSave();
  const [cancel, setCancel] = useState(String(s.rules.cancel_before_hours));
  const [lead, setLead] = useState(String(s.rules.lead_time_min));
  const [remind, setRemind] = useState(String(s.rules.reminder_hours));
  const save = useMutation({ mutationFn: () => api(`${ownerApi(slug)}/settings`, { method: "PATCH", body: { cancel_before_hours: Number(cancel), lead_time_min: Number(lead), reminder_hours: Number(remind) } }), onSuccess: after });
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Правила записи</h2>
      <NativeField label="Клиент может отменить не позднее, чем за (часов)" inputMode="numeric" value={cancel} onChange={setCancel} />
      <NativeField label="Записываться не раньше, чем через (минут)" inputMode="numeric" value={lead} onChange={setLead} />
      <NativeField label="Напоминание клиенту за (часов)" inputMode="numeric" value={remind} onChange={setRemind} />
      <span className="muted" style={{ fontSize: 13 }}>Сейчас: отмена за {formatDuration(Number(cancel) * 60 || 0)}, запись минимум за {formatDuration(Number(lead) || 0)}.</span>
      <Save mutation={save} />
    </div>
  );
}

function OwnerPush() {
  const { slug } = useStudio();
  const cfg = useQuery({ queryKey: ["push-config", slug], queryFn: () => api<PushConfig>(`/api/s/${slug}/push/config`) });
  const [support, setSupport] = useState<PushSupport | null>(null);
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { if (cfg.data) { setSupport(cfg.data.preview ? { state: "server-off" } : detectPush(cfg.data.enabled)); currentEndpoint().then((e) => setOn(Boolean(e) && Notification.permission === "granted")).catch(() => undefined); } }, [cfg.data]);
  if (!support || !cfg.data) return null;
  const toggle = async () => {
    setBusy(true); setError("");
    try {
      if (on) { const ep = await unsubscribePush(); if (ep) await api(`${ownerApi(slug)}/push?endpoint=${encodeURIComponent(ep)}`, { method: "DELETE" }); setOn(false); }
      else { const sub = await subscribePush(slug, cfg.data!.public_key ?? ""); await api(`${ownerApi(slug)}/push`, { method: "POST", body: { endpoint: sub.endpoint, keys: sub.keys } }); setOn(true); }
    } catch (e) { setError(e instanceof ApiError ? e.message : "Не удалось изменить настройку уведомлений."); } finally { setBusy(false); }
  };
  const note: Record<string, string> = {
    "ios-install": "На iPhone уведомления приходят после установки: «Поделиться» → «На экран Домой», затем откройте кабинет с иконки.",
    denied: "Уведомления заблокированы в настройках браузера.",
    unsupported: "Этот браузер не поддерживает уведомления.",
    insecure: "Уведомления работают только на защищённом адресе (https).",
    "server-off": cfg.data.preview ? "В образце уведомления отключены." : "На сервере ещё не настроены ключи уведомлений.",
  };
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Уведомления о записях</h2>
      {support.state === "ready" ? (
        <>
          <Button label={on ? "Уведомления включены — выключить" : "Получать уведомления о новых записях"} icon={<BellRinging weight="fill" />} variant={on ? "secondary" : "primary"} isLoading={busy} onClick={toggle} />
          {error && <span className="error-text" role="alert">{error}</span>}
        </>
      ) : <Banner status="info" title="Уведомления недоступны" description={note[support.state]} />}
    </div>
  );
}

export function StudioSettings() {
  const { slug, href } = useStudio();
  const { email, logout, subscription } = useOwner();
  const q = useSettings();
  const [copied, setCopied] = useState(false);
  const url = typeof window === "undefined" ? "" : `${location.origin}${href()}`;
  return (
    <div className="page stack" style={{ gap: 18 }}>
      <h1 className="owner-title" style={{ marginTop: 24 }}>Студия</h1>
      {q.isPending && <Skeleton height={300} />}
      {q.isError && <Banner status="error" title="Настройки не загрузились" description={(q.error as ApiError).message} endContent={<Button size="sm" label="Повторить" onClick={() => q.refetch()} />} />}
      {q.data && (
        <>
          <div className="panel stack">
            <b>Ссылка для клиентов</b>
            <span style={{ wordBreak: "break-all" }}>{url}</span>
            <Button label={copied ? "Скопировано" : "Скопировать ссылку"} icon={<Copy />} variant="secondary" onClick={() => navigator.clipboard?.writeText(url).then(() => setCopied(true))} />
          </div>
          <TariffCard sub={subscription} />
          <Basics s={q.data} />
          <Pictures s={q.data} />
          <GalleryManager items={q.data.gallery} />
          <HoursEditor s={q.data} />
          <Rules s={q.data} />
          <OwnerPush />
        </>
      )}
      <div className="panel stack">
        <span className="muted">Вы вошли как {email}</span>
        <Button label="Выйти" icon={<SignOut />} variant="secondary" onClick={logout} />
      </div>
    </div>
  );
}
