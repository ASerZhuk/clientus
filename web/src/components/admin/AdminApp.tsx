"use client";

import { ArrowUpRight, MagnifyingGlass, SignOut, X } from "@phosphor-icons/react";
import { Banner } from "@astryxdesign/core/Banner";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Input } from "@/components/ui/Input";
import { NativeSelect } from "@/components/ui/Native";
import { Button } from "@/components/ui/Pill";
import { api, ApiError, setCsrf } from "@/lib/api";
import { formatMoney, plural } from "@/lib/format";
import type { AdminDomain, AdminOverview, AdminPlan, AdminTenant, DnsCheck } from "./types";

const STATE: Record<string, { label: string; color: string }> = {
  preview: { label: "образец", color: "#8a8a93" },
  trial: { label: "пробный", color: "#6ea8ff" },
  active: { label: "боевая", color: "#3ddc84" },
  past_due: { label: "ждём оплату", color: "#ffc857" },
  suspended: { label: "приостановлена", color: "#ff6b6b" },
  disabled: { label: "отключена", color: "#555" },
};
const TYPE: Record<string, string> = { auto: "автосервис", wash: "мойка", beauty_master: "мастер красоты", beauty_studio: "студия красоты" };
const fmtDate = (s: number | null) => (s ? new Date(s * 1000).toLocaleDateString("ru-RU") : "—");

interface Me { email: string; csrf_token: string; plans: AdminPlan[] }

function Login({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ email: "", password: "" });
  const login = useMutation({
    mutationFn: () => api<{ csrf_token: string }>("/api/admin/login", { method: "POST", body: f }),
    onSuccess: (r) => { setCsrf(r.csrf_token); onDone(); },
  });
  return (
    <main className="page stack" style={{ paddingTop: 56, gap: 22, maxWidth: 440 }}>
      <div>
        <h1 className="owner-title" style={{ marginTop: 0 }}>Панель оператора</h1>
        <p className="owner-sub">Вход только для владельца платформы</p>
      </div>
      <form className="stack" noValidate onSubmit={(e) => { e.preventDefault(); login.mutate(); }}>
        <Input label="Почта" type="email" inputMode="email" autoComplete="username" value={f.email} onChange={(v) => setF({ ...f, email: v })} />
        <Input label="Пароль" type="password" autoComplete="current-password" value={f.password} onChange={(v) => setF({ ...f, password: v })} onEnter={() => login.mutate()} />
        {login.isError && <Banner status="error" title="Не удалось войти" description={(login.error as ApiError).message} />}
        <Button label="Войти" type="submit" variant="primary" size="lg" width="100%" isLoading={login.isPending} />
      </form>
    </main>
  );
}

function StateDot({ state }: { state: string }) {
  const s = STATE[state] ?? STATE.preview;
  return <span className="row" style={{ gap: 8, fontSize: 14 }}><i className="status-dot" style={{ background: s.color }} />{s.label}</span>;
}

function Tile({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return <div className="kpi"><small>{label}</small><b>{value}</b>{note && <em>{note}</em>}</div>;
}

function TenantPanel({ slug, plans, onClose }: { slug: string | null; plans: AdminPlan[]; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-tenant", slug], queryFn: () => api<AdminTenant>(`/api/admin/tenants/${slug}`), enabled: slug !== null });
  const t = q.data;
  const [notes, setNotes] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [secret, setSecret] = useState<{ email: string; password: string } | null>(null);
  const [host, setHost] = useState("");
  const [dns, setDns] = useState<DnsCheck | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (t) { setNotes(t.notes); setOwnerEmail(t.owners[0] ?? ""); setSecret(null); setDns(null); setError(""); } }, [t?.slug, t?.notes]); // eslint-disable-line react-hooks/exhaustive-deps
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin-tenant", slug] }); qc.invalidateQueries({ queryKey: ["admin-overview"] }); };
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Не удалось выполнить.");
  const patch = useMutation({ mutationFn: (body: Record<string, unknown>) => api<AdminTenant>(`/api/admin/tenants/${slug}/subscription`, { method: "PATCH", body }), onSuccess: () => { setError(""); refresh(); }, onError: fail });
  const status = useMutation({ mutationFn: (s: string) => api(`/api/admin/tenants/${slug}/status`, { method: "POST", body: { status: s } }), onSuccess: () => { setError(""); refresh(); }, onError: (e) => setError(e instanceof ApiError && e.code === "no_owner" ? "Сначала создайте владельца." : e instanceof ApiError ? e.message : "Ошибка.") });
  const owner = useMutation({ mutationFn: () => api<{ email: string; password: string }>(`/api/admin/tenants/${slug}/owner`, { method: "POST", body: { email: ownerEmail } }), onSuccess: (r) => { setSecret(r); refresh(); }, onError: fail });
  const addDomain = useMutation({
    mutationFn: () => api<{ dns: DnsCheck }>(`/api/admin/tenants/${slug}/domains`, { method: "POST", body: { host, force: false } }),
    onSuccess: (r) => { setHost(""); setDns(r.dns); setError(""); refresh(); },
    onError: (e) => setError(e instanceof ApiError && e.code === "plan_no_custom_domain" ? "Тариф не включает свой домен. Смените тариф." : e instanceof ApiError ? e.message : "Ошибка."),
  });
  const verify = useMutation({ mutationFn: (v: { id: number; force: boolean }) => api<{ dns: DnsCheck; status: string }>(`/api/admin/domains/${v.id}/verify`, { method: "POST", body: { force: v.force } }), onSuccess: (r) => { setDns(r.dns); refresh(); }, onError: fail });
  const removeDomain = useMutation({ mutationFn: (id: number) => api(`/api/admin/domains/${id}`, { method: "DELETE" }), onSuccess: refresh, onError: fail });
  const impersonate = useMutation({ mutationFn: () => api(`/api/admin/tenants/${slug}/impersonate`, { method: "POST" }), onSuccess: () => window.open(`/s/${slug}/owner`, "_blank"), onError: fail });

  if (slug === null) return <aside className="adm-detail adm-empty" aria-label="Студия">Выберите студию в таблице, чтобы управлять пакетом, владельцем и доменами.</aside>;
  return (
    <aside className="adm-detail stack" aria-label="Студия">
      <div className="row-between">
        <h2 className="adm-detail-title">{t?.name ?? "Студия"}</h2>
        <Button label="Закрыть" size="sm" variant="ghost" icon={<X />} onClick={onClose} />
      </div>
      {q.isPending && <Skeleton height={200} />}
      {t && (
        <>
          <p className="muted row" style={{ margin: 0, fontSize: 14, flexWrap: "wrap", gap: 6 }}>{t.slug} · {TYPE[t.business_type] ?? t.business_type} · <StateDot state={t.state} /></p>
          {error && <Banner status="error" title={error} />}

          <section className="panel stack" aria-label="Тариф">
            <b>Пакет</b>
            <dl className="summary" style={{ margin: 0 }}>
              <div><dt>Состояние</dt><dd><StateDot state={t.state} /></dd></div>
              <div><dt>Действует</dt><dd>{t.ends_at ? `до ${fmtDate(t.ends_at)}${t.days_left !== null ? ` (${plural(t.days_left, ["день", "дня", "дней"])})` : ""}` : "бессрочно"}</dd></div>
              <div><dt>Записей в месяце</dt><dd>{t.usage.bookings_month}</dd></div>
              <div><dt>Ресурсов</dt><dd>{t.usage.resources}</dd></div>
              <div><dt>Последняя запись</dt><dd>{fmtDate(t.last_booking_at)}</dd></div>
            </dl>
            <NativeSelect label="Пакет" value={t.plan} onChange={(v) => patch.mutate({ plan: v })} options={plans.map((p) => ({ value: p.key, label: `${p.label} · ${formatMoney(p.price_minor)}` }))} />
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              <Button label={t.suspended ? "Возобновить" : "Приостановить"} size="sm" variant={t.suspended ? "primary" : "destructive"} isLoading={patch.isPending} onClick={() => patch.mutate({ suspended: !t.suspended })} />
            </div>
            <NativeSelect label="Публикация" value={t.status} onChange={(v) => status.mutate(v)} options={[{ value: "preview", label: "Образец (не индексируется, без уведомлений)" }, { value: "active", label: "Боевая (бессрочно)" }, { value: "disabled", label: "Отключена (404)" }]} />
            <Input label="Заметки" isOptional value={notes} onChange={setNotes} placeholder="счёт, договорённости, контакты" />
            <Button label="Сохранить заметки" size="sm" variant="secondary" isDisabled={notes === t.notes} isLoading={patch.isPending} onClick={() => patch.mutate({ notes })} />
          </section>

          <section className="panel stack" aria-label="Владелец">
            <b>Владелец</b>
            <span className="muted" style={{ fontSize: 14 }}>{t.owners.length ? t.owners.join(", ") : "владельца ещё нет"}</span>
            <Input label="Почта владельца" type="email" inputMode="email" value={ownerEmail} onChange={setOwnerEmail} />
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              <Button label={t.owners.length ? "Сбросить пароль" : "Создать владельца"} size="sm" variant="secondary" isDisabled={!ownerEmail.includes("@")} isLoading={owner.isPending} onClick={() => owner.mutate()} />
              <Button label="Войти в кабинет" size="sm" variant="secondary" icon={<ArrowUpRight />} isDisabled={!t.owners.length} isLoading={impersonate.isPending} onClick={() => impersonate.mutate()} />
            </div>
            {secret && (
              <Banner status="success" title="Пароль показан один раз" description={`${secret.email} — ${secret.password}`} endContent={<Button label="Копировать" size="sm" onClick={() => navigator.clipboard?.writeText(secret.password)} />} />
            )}
          </section>

          <section className="panel stack" aria-label="Домены">
            <b>Свои домены</b>
            {t.domains.map((d: AdminDomain) => (
              <div key={d.id} className="row-between">
                <span>{d.host} · <span className="muted">{d.status === "active" ? "активен" : "ждёт DNS"}</span></span>
                <span className="row" style={{ gap: 6 }}>
                  {d.status !== "active" && <Button label="Проверить" size="sm" variant="secondary" isLoading={verify.isPending} onClick={() => verify.mutate({ id: d.id, force: false })} />}
                  {d.status !== "active" && <Button label="Принудительно" size="sm" variant="ghost" onClick={() => verify.mutate({ id: d.id, force: true })} />}
                  <Button label="Удалить" size="sm" variant="ghost" onClick={() => removeDomain.mutate(d.id)} />
                </span>
              </div>
            ))}
            <Input label="Новый домен" value={host} onChange={setHost} placeholder="book.example.ru" />
            <Button label="Добавить домен" size="sm" variant="secondary" isDisabled={host.trim().length < 4} isLoading={addDomain.isPending} onClick={() => addDomain.mutate()} />
            {dns && (
              <span className="muted" style={{ fontSize: 14 }}>
                {dns.host}: сейчас указывает на {dns.resolved.join(", ") || "ничего"}; нужно {dns.expected.join(", ") || "(PLATFORM_IPS не задан)"} — {dns.ok ? "всё верно" : "пока не совпадает"}.
              </span>
            )}
          </section>

          {!!t.audit?.length && (
            <section className="panel stack" aria-label="Журнал">
              <b>Журнал действий</b>
              {t.audit.slice(0, 8).map((a, i) => (
                <span key={i} className="muted" style={{ fontSize: 14 }}>{new Date(a.at * 1000).toLocaleString("ru-RU")} · {a.actor} · {a.action}</span>
              ))}
            </section>
          )}
        </>
      )}
    </aside>
  );
}

function Dashboard({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const q = useQuery({ queryKey: ["admin-overview"], queryFn: () => api<AdminOverview>("/api/admin/overview"), refetchInterval: 60_000 });
  const d = q.data;
  const needle = search.trim().toLowerCase();
  const rows = (d?.tenants ?? []).filter((t) => (filter === "all" || t.state === filter) && (!needle || [t.name, t.slug, ...t.owners, ...t.domains.map((x) => x.host)].some((v) => v.toLowerCase().includes(needle))));
  return (
    <main className="adm">
      <header className="adm-head">
        <div><h1 className="adm-title">Студии</h1><p className="muted" style={{ margin: "2px 0 0", fontSize: 14 }}>Оператор: {me.email}</p></div>
        <Button label="Выйти" size="sm" variant="secondary" icon={<SignOut />} onClick={onLogout} />
      </header>
      {q.isError && <Banner status="error" title="Не удалось загрузить" description={(q.error as ApiError).message} />}
      <div className="kpis" aria-busy={q.isPending}>
        <Tile label="Всего студий" value={d?.tenants_total ?? "—"} />
        <Tile label="Боевых" value={d?.live_total ?? "—"} note="проданных студий" />
        <Tile label="Записей за 30 дней" value={d?.bookings_30d ?? "—"} note="без демо" />
        <Tile label="Продано на" value={d ? formatMoney(d.sales_total_minor) : "—"} note="по цене пакетов боевых студий" />
      </div>
      <div className="adm-main">
        <section className="stack" aria-label="Список студий" style={{ minWidth: 0 }}>
          <div className="adm-toolbar">
            <div className="chips" role="group" aria-label="Фильтр">
              {[["all", "Все"], ["active", "Боевые"], ["preview", "Образцы"], ["suspended", "Приостановлены"], ["disabled", "Отключены"]].map(([k, label]) => (
                <button key={k} type="button" className="chip-btn" aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}{d && k !== "all" ? ` · ${d.by_state[k] ?? 0}` : ""}</button>
              ))}
            </div>
            <label className="adm-search">
              <MagnifyingGlass size={16} aria-hidden />
              <input type="search" aria-label="Поиск студии" placeholder="Название, slug, почта, домен" value={search} onChange={(e) => setSearch(e.target.value)} />
            </label>
          </div>
          {q.isPending && <Skeleton height={320} />}
          {d && (
            <div className="adm-table-wrap">
              <table className="adm-table">
                <thead>
                  <tr><th>Студия</th><th>Тип</th><th>Пакет</th><th>Состояние</th><th>Владелец</th><th>Домен</th><th className="num">Записей / мес</th><th className="num">Последняя запись</th></tr>
                </thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.slug} data-selected={open === t.slug} onClick={() => setOpen(t.slug)}>
                      <td><button type="button" className="adm-name" onClick={(e) => { e.stopPropagation(); setOpen(t.slug); }}>{t.name}</button><span className="adm-sub">{t.slug}</span></td>
                      <td>{TYPE[t.business_type] ?? t.business_type}</td>
                      <td>{t.plan_label}</td>
                      <td><StateDot state={t.state} /></td>
                      <td>{t.owners[0] ?? <span className="muted">нет</span>}</td>
                      <td>{t.domains.find((x) => x.status === "active")?.host ?? (t.domains.length ? <span className="muted">ждёт DNS</span> : <span className="muted">—</span>)}</td>
                      <td className="num">{t.usage.bookings_month}</td>
                      <td className="num">{fmtDate(t.last_booking_at)}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && <tr><td colSpan={8} className="muted" style={{ textAlign: "center", padding: 32 }}>Ничего не найдено. Измените фильтр или запрос.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <TenantPanel slug={open} plans={me.plans} onClose={() => setOpen(null)} />
      </div>
    </main>
  );
}

export function AdminApp() {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ["admin-me"],
    queryFn: async () => {
      const r = await api<Me>("/api/admin/me");
      setCsrf(r.csrf_token);
      return r;
    },
    retry: false,
    staleTime: 5 * 60_000,
  });
  const logout = async () => {
    try { await api("/api/admin/logout", { method: "POST" }); } catch { /* already gone */ }
    setCsrf(null);
    qc.clear();
    qc.invalidateQueries({ queryKey: ["admin-me"] });
  };
  if (me.isPending) return <main className="page" style={{ paddingTop: 80 }}><Skeleton height={200} /></main>;
  if (me.isError) {
    if (me.error instanceof ApiError && me.error.status === 401) return <Login onDone={() => qc.invalidateQueries({ queryKey: ["admin-me"] })} />;
    return <main className="page" style={{ paddingTop: 60 }}><Banner status="error" title="Панель недоступна" description={(me.error as ApiError).message} /></main>;
  }
  return <Dashboard me={me.data} onLogout={logout} />;
}
