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
import { useDoParam } from "@/lib/hooks";
import { WEEKDAYS_SHORT, hhmmToMin, minToHhmm } from "@/lib/format";
import { detectPush, deniedHelp, onPermissionMaybeChanged, subscribePush, currentEndpoint, type PushSupport } from "@/lib/push";
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
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Основное</h2>
      <Input label="Название" value={f.name} onChange={(v) => setF({ ...f, name: v })} error={errors.name} />
      <Input label="Краткое описание" isOptional value={f.tagline} onChange={(v) => setF({ ...f, tagline: v })} error={errors.tagline} />
      <Input label="Телефон" inputMode="tel" value={f.phone} onChange={(v) => setF({ ...f, phone: v })} error={errors.phone} />
      <Input label="Адрес" value={f.address} onChange={(v) => setF({ ...f, address: v })} error={errors.address} />
      <Input label="Ссылка на карту" isOptional value={f.map_url} onChange={(v) => setF({ ...f, map_url: v })} error={errors.map_url} placeholder="https://…" />
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
      <div className="hours-list">
        {days.map((d, i) => (
          <div key={d.weekday} className="hours-row" data-closed={d.is_closed}>
            <b>{WEEKDAYS_SHORT[d.weekday]}</b>
            {d.is_closed ? <span className="muted hours-off">выходной</span> : (
              <>
                <NativeField label="" aria-label={`${WEEKDAYS_SHORT[d.weekday]}: с`} type="time" step={900} value={minToHhmm(d.open_min)} onChange={(v) => v && set(i, { open_min: hhmmToMin(v) })} />
                <span className="muted">–</span>
                <NativeField label="" aria-label={`${WEEKDAYS_SHORT[d.weekday]}: до`} type="time" step={900} value={minToHhmm(d.close_min)} onChange={(v) => v && set(i, { close_min: hhmmToMin(v) })} />
              </>
            )}
            <Switch label={`${WEEKDAYS_SHORT[d.weekday]}: рабочий день`} isLabelHidden value={!d.is_closed} onChange={(v) => set(i, { is_closed: !v })} />
          </div>
        ))}
      </div>
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

function OwnerPush() {
  const { slug } = useStudio();
  const qc = useQueryClient();
  const refreshDevices = () => qc.invalidateQueries({ queryKey: ["owner-push-devices", slug] });
  const cfg = useQuery({ queryKey: ["push-config", slug], queryFn: () => api<PushConfig>(`/api/s/${slug}/push/config`) });
  const [support, setSupport] = useState<PushSupport | null>(null);
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [testing, setTesting] = useState(false);
  const [testMsg, setTestMsg] = useState("");
  useEffect(() => {
    if (!cfg.data) return;
    const check = () => {
      setSupport(cfg.data!.preview ? { state: "server-off" } : detectPush(cfg.data!.enabled));
      // the device may already be subscribed as a client: ask the server whether the OWNER is subscribed here
      currentEndpoint()
        .then((e) => (e && Notification.permission === "granted" ? api<{ on: boolean }>(`${ownerApi(slug)}/push?endpoint=${encodeURIComponent(e)}`).then((r) => r.on) : false))
        .then(setOn)
        .catch(() => setOn(false));
    };
    check();
    return onPermissionMaybeChanged(check); // coming back from the system settings
  }, [cfg.data]);
  if (!support || !cfg.data) return null;
  const toggle = async () => {
    setBusy(true); setError("");
    try {
      // off = only the owner's link to this device; the device subscription may still carry a client's reminder
      if (on) { const ep = await currentEndpoint(); if (ep) await api(`${ownerApi(slug)}/push?endpoint=${encodeURIComponent(ep)}`, { method: "DELETE" }); setOn(false); }
      else { const sub = await subscribePush(slug, cfg.data!.public_key ?? ""); await api(`${ownerApi(slug)}/push`, { method: "POST", body: { endpoint: sub.endpoint, keys: sub.keys } }); setOn(true); }
    } catch (e) { setError(e instanceof ApiError ? e.message : (e as Error).message === "permission_denied" ? "Вы не разрешили уведомления." : (e as Error).message || "Не удалось изменить настройку уведомлений."); } finally { setBusy(false); refreshDevices(); }
  };
  const note: Record<string, string> = {
    "ios-install": "На iPhone уведомления приходят после установки: «Поделиться» → «На экран Домой», затем откройте кабинет с иконки.",
    denied: deniedHelp(),
    unsupported: "Этот браузер не поддерживает уведомления.",
    insecure: "Уведомления работают только на защищённом адресе (https).",
    "server-off": cfg.data.preview ? "В образце уведомления отключены." : "На сервере ещё не настроены ключи уведомлений.",
  };
  const sendTest = async () => {
    setTesting(true);
    setError("");
    setTestMsg("");
    try {
      await api(`${ownerApi(slug)}/push/test`, { method: "POST" });
      setTestMsg("Отправили. Уведомление должно прийти в течение нескольких секунд.");
      refreshDevices();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось отправить.");
    } finally {
      setTesting(false);
    }
  };
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Уведомления о записях</h2>
      {support.state === "ready" ? (
        <>
          <Button label={on ? "Уведомления включены — выключить" : "Получать уведомления о новых записях"} icon={<BellRinging weight="fill" />} variant={on ? "secondary" : "primary"} isLoading={busy} onClick={toggle} />
          {on && <Button label="Проверить — прислать тестовое" variant="ghost" isLoading={testing} onClick={sendTest} />}
          {testMsg && <span className="muted" role="status">{testMsg}</span>}
          {error && <span className="error-text" role="alert">{error}</span>}
        </>
      ) : <Banner status="info" title="Уведомления недоступны" description={note[support.state]} />}
      <OwnerDevices on={on} />
    </div>
  );
}

interface OwnerDevice { id: number; device: string; created_at: number; last_success_at: number | null; failure_count: number; last_error: string | null; this_device: boolean }

/** Where notifications go, and whether they actually arrive there. */
function OwnerDevices({ on }: { on: boolean }) {
  const { slug, tenant } = useStudio();
  const qc = useQueryClient();
  const [endpoint, setEndpoint] = useState<string>("");
  useEffect(() => { currentEndpoint().then((e) => setEndpoint(e ?? "")).catch(() => undefined); }, [on]);
  const q = useQuery({
    queryKey: ["owner-push-devices", slug, endpoint, on],
    queryFn: () => api<{ devices: OwnerDevice[] }>(`${ownerApi(slug)}/push/devices?endpoint=${encodeURIComponent(endpoint)}`),
  });
  const off = useMutation({
    mutationFn: (id: number) => api(`${ownerApi(slug)}/push/devices/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["owner-push-devices", slug] }),
  });
  const when = (t: number) => new Date(t * 1000).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: tenant.timezone });
  const list = q.data?.devices ?? [];
  if (!list.length) return null;
  return (
    <div className="stack" style={{ gap: 0 }}>
      <h3 className="owner-day-title" style={{ margin: "6px 0 4px" }}>Куда приходят уведомления</h3>
      {list.map((d) => (
        <div key={d.id} className="row-between divider-row" style={{ padding: "12px 0", alignItems: "flex-start" }}>
          <div className="grow">
            <div className="service-name">{d.device}{d.this_device ? " — это устройство" : ""}</div>
            <div className="service-desc">
              {d.last_success_at ? `Последнее доставлено: ${when(d.last_success_at)}` : "Ещё ничего не отправляли"}
              {d.failure_count > 0 && <span className="error-text" style={{ display: "block" }}>Не доставлено подряд: {d.failure_count}{d.last_error ? ` (${d.last_error.slice(0, 80)})` : ""}</span>}
            </div>
          </div>
          <Button label="Отключить" size="sm" variant="ghost" isLoading={off.isPending && off.variables === d.id} onClick={() => off.mutate(d.id)} />
        </div>
      ))}
    </div>
  );
}

export function StudioSettings() {
  const { slug, href } = useStudio();
  const { email, logout, subscription } = useOwner();
  const q = useSettings();
  const [copied, setCopied] = useState(false);
  const url = typeof window === "undefined" ? "" : `${location.origin}${href()}`;
  const req = useDoParam(Boolean(q.data));
  useEffect(() => {
    const el = req && document.getElementById(req.get("do") ?? "");
    if (!el) return;
    el.scrollIntoView({ block: "start", behavior: "smooth" });
    el.classList.add("anchor-hit");
    setTimeout(() => el.classList.remove("anchor-hit"), 1600);
  }, [req]);
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
          <div id="basics" className="anchor"><Basics s={q.data} /></div>
          <div id="photos" className="anchor"><Pictures s={q.data} /></div>
          <GalleryManager items={q.data.gallery} />
          <div id="hours" className="anchor"><HoursEditor s={q.data} /></div>
          <div id="push" className="anchor"><OwnerPush /></div>
        </>
      )}
      <div id="password" className="anchor"><PasswordChange /></div>
      <div className="panel stack">
        <span className="muted">Вы вошли как {email}</span>
        <Button label="Выйти" icon={<SignOut />} variant="secondary" onClick={logout} />
      </div>
    </div>
  );
}

function PasswordChange() {
  const { slug } = useStudio();
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const mismatch = repeat.length > 0 && repeat !== next;
  const short = next.length > 0 && next.length < 10;
  const save = useMutation({
    mutationFn: () => api(`${ownerApi(slug)}/password`, { method: "POST", body: { new: next } }),
    onSuccess: () => { setNext(""); setRepeat(""); },
  });
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Пароль</h2>
      <Input label="Новый пароль" type="password" autoComplete="new-password" value={next} onChange={setNext} error={short ? "Минимум 10 символов" : undefined} />
      <Input label="Повторите новый пароль" type="password" autoComplete="new-password" value={repeat} onChange={setRepeat} error={mismatch ? "Пароли не совпадают" : undefined} />
      <span className="muted" style={{ fontSize: 13 }}>На других устройствах кабинет попросит войти заново.</span>
      {save.isError && <span className="error-text" role="alert">{save.error instanceof ApiError ? save.error.message : "Не удалось сменить пароль."}</span>}
      {save.isSuccess && <span style={{ color: "#3ddc84", fontSize: 14 }} role="status">Пароль изменён</span>}
      <Button label="Сменить пароль" variant="primary" isDisabled={next.length < 10 || next !== repeat} isLoading={save.isPending} onClick={() => save.mutate()} />
    </div>
  );
}
