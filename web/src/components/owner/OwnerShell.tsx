"use client";

import { Button } from "@/components/ui/Pill";
import { ArrowSquareOut, CalendarBlank, ChatCircleDots, Storefront, Wrench } from "@phosphor-icons/react";
import { Banner } from "@astryxdesign/core/Banner";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { AssistantSheet } from "@/components/client/AssistantSheet";
import { AppPrompt, OwnerPushBanner } from "@/components/AppPrompt";
import { isIos, isStandalone } from "@/lib/push";
import { useStudio } from "@/components/StudioProviders";
import { Input } from "@/components/ui/Input";
import { api, ApiError, ownerApi, setCsrf } from "@/lib/api";
import { fieldErrors, loginSchema } from "@/lib/schemas";
import { SubscriptionBanner, type SubscriptionInfo } from "./Subscription";

interface Me { email: string; csrf_token: string; tenant: { slug: string; status: string }; subscription: SubscriptionInfo }
const OwnerCtx = createContext<{ email: string; logout: () => void; subscription: SubscriptionInfo } | null>(null);
export const useOwner = () => {
  const c = useContext(OwnerCtx);
  if (!c) throw new Error("outside owner shell");
  return c;
};

export function OwnerHeader() {
  const { tenant, href } = useStudio();
  return (
    <header className="app-header">
      <div className="app-header-inner">
        <span className="brand">
          <span className="brand-logo">{tenant.logo_url ? /* eslint-disable-next-line @next/next/no-img-element */ <img src={tenant.logo_url} alt="" /> : tenant.name.slice(0, 1)}</span>
          <span className="brand-text"><small>Кабинет</small><span>{tenant.name}</span></span>
        </span>
        <span className="grow" />
        <Link href={href()} className="glass-round" aria-label="Открыть сайт студии" title="Открыть сайт студии"><ArrowSquareOut size={20} /></Link>
      </div>
    </header>
  );
}

function LoginForm({ onDone }: { onDone: () => void }) {
  const { slug, tenant } = useStudio();
  const [form, setForm] = useState({ email: "", password: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const login = useMutation({
    mutationFn: () => api<{ csrf_token: string }>(`${ownerApi(slug)}/login`, { method: "POST", body: form }),
    onSuccess: (r) => { setCsrf(r.csrf_token); onDone(); },
  });
  const submit = () => {
    const parsed = loginSchema.safeParse(form);
    if (!parsed.success) return setErrors(fieldErrors(parsed.error));
    setErrors({});
    login.mutate();
  };
  return (
    <main className="studio">
      <OwnerHeader />
      <div className="page stack" style={{ gap: 22, paddingTop: 12 }}>
        <div>
          <h1 className="owner-title">Вход в кабинет</h1>
          <p className="owner-sub">{tenant.name}</p>
        </div>
        <form className="stack" noValidate onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <Input label="Почта" name="email" type="email" inputMode="email" autoComplete="username" value={form.email} onChange={(v) => setForm({ ...form, email: v })} error={errors.email} />
          <Input label="Пароль" name="password" type="password" autoComplete="current-password" value={form.password} onChange={(v) => setForm({ ...form, password: v })} error={errors.password} onEnter={submit} />
          {login.isError && <Banner status="error" title="Не удалось войти" description={(login.error as ApiError).message} />}
          <Button label="Войти" type="submit" variant="primary" size="lg" width="100%" isLoading={login.isPending} />
        </form>
        <p className="muted" style={{ fontSize: 13 }}>Доступ выдаёт администратор сервиса. Регистрации нет.</p>
      </div>
    </main>
  );
}

export function OwnerShell({ children }: { children: React.ReactNode }) {
  const { slug, href } = useStudio();
  const qc = useQueryClient();
  const path = usePathname();
  const [assistant, setAssistant] = useState(false);
  const me = useQuery({
    queryKey: ["owner-me", slug],
    queryFn: async () => {
      // first launch of the iPhone home-screen app: its start URL carries a one-time sign-in code (?k=)
      const k = new URLSearchParams(window.location.search).get("k");
      try {
        let r: Me;
        try {
          r = await api<Me>(`${ownerApi(slug)}/me`);
        } catch (e) {
          if (!(k && e instanceof ApiError && e.status === 401)) throw e;
          const s = await api<{ csrf_token: string }>(`${ownerApi(slug)}/login-code`, { method: "POST", body: { code: k } });
          setCsrf(s.csrf_token);
          r = await api<Me>(`${ownerApi(slug)}/me`);
        }
        setCsrf(r.csrf_token);
        return r;
      } finally {
        if (k) { const u = new URL(window.location.href); u.searchParams.delete("k"); history.replaceState(history.state, "", u); }
      }
    },
    retry: false,
    staleTime: 5 * 60_000,
  });

  // Safari on iPhone: put a sign-in code into the icon "Add to Home Screen" will create, so the installed app opens signed in
  const [installCode, setInstallCode] = useState<string | null>(null);
  useEffect(() => {
    if (!me.data || installCode || isStandalone() || !isIos()) return;
    api<{ code: string }>(`${ownerApi(slug)}/install-code`, { method: "POST" }).then((r) => setInstallCode(r.code)).catch(() => undefined);
  }, [me.data, installCode, slug]);
  useEffect(() => {
    if (!installCode) return;
    const u = new URL(window.location.href);
    if (u.searchParams.get("k") !== installCode) { u.searchParams.set("k", installCode); history.replaceState(history.state, "", u); }
    document.querySelector('link[rel="manifest"]')?.setAttribute("href", `${href("/manifest.webmanifest")}?app=owner&k=${encodeURIComponent(installCode)}`);
  }, [installCode, path, href]);

  const logout = async () => {
    try { await api(`${ownerApi(slug)}/logout`, { method: "POST" }); } catch { /* session already gone */ }
    setCsrf(null);
    qc.clear(); // private data must not survive logout in memory
    if ("caches" in window) (await caches.keys()).filter((k) => k.includes(`studio-${slug}`) && /owner|private/.test(k)).forEach((k) => caches.delete(k));
    window.location.replace(href("/owner")); // full reload: nothing of the session stays on screen or in memory
  };

  if (me.isPending) return <main className="page" style={{ paddingTop: 80 }}><Skeleton height={200} radius={4} /></main>;
  if (me.isError) {
    const unauth = me.error instanceof ApiError && (me.error.status === 401 || me.error.status === 403);
    if (unauth) return <LoginForm onDone={() => qc.invalidateQueries({ queryKey: ["owner-me", slug] })} />;
    return <main className="page" style={{ paddingTop: 60 }}><Banner status="error" title="Кабинет недоступен" description={(me.error as ApiError).message} endContent={<Button label="Повторить" size="sm" onClick={() => me.refetch()} />} /></main>;
  }
  const base = href("/owner");
  const items = [
    { href: base, label: "Расписание", Icon: CalendarBlank, active: path === base },
    { href: `${base}/services`, label: "Услуги", Icon: Wrench, active: path.startsWith(`${base}/services`) },
    { href: `${base}/studio`, label: "Студия", Icon: Storefront, active: path.startsWith(`${base}/studio`) },
  ];
  return (
    <OwnerCtx.Provider value={{ email: me.data.email, logout, subscription: me.data.subscription }}>
      <div className="studio-owner">
        <OwnerHeader />
        <div className="page notice"><SubscriptionBanner sub={me.data.subscription} /><OwnerPushBanner /></div>
        {children}
      </div>
      <nav className="dock-wrap" aria-label="Кабинет">
        <div className="dock dock-labeled" id="owner-nav">
          {items.map(({ href, label, Icon, active }) => (
            <Link key={href} href={href} className="dock-tab" aria-current={active ? "page" : undefined}>
              <Icon size={22} weight={active ? "fill" : "regular"} aria-hidden />
              <span>{label}</span>
            </Link>
          ))}
          <button type="button" className="dock-tab" onClick={() => setAssistant(true)}>
            <ChatCircleDots size={22} aria-hidden />
            <span>Помощник</span>
          </button>
        </div>
      </nav>
      <AssistantSheet slug={slug} audience="owner" isOpen={assistant} onClose={() => setAssistant(false)} />
      <AppPrompt audience="owner" />
    </OwnerCtx.Provider>
  );
}
