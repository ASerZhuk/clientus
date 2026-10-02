"use client";

import { BellRinging, DownloadSimple } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useStudio } from "@/components/StudioProviders";
import { AppSheet } from "@/components/ui/AppSheet";
import { Button } from "@/components/ui/Pill";
import { api, ApiError, ownerApi, studioApi } from "@/lib/api";
import { useInstall } from "@/lib/install";
import { currentEndpoint, detectPush, subscribePush, type PushSupport } from "@/lib/push";
import type { PushConfig } from "@/lib/types";

const SNOOZE_DAYS = 7;
const isPhone = () => window.matchMedia("(pointer: coarse)").matches && window.innerWidth < 900;

function snoozed(key: string): boolean {
  try { return Date.now() - Number(localStorage.getItem(key) || 0) < SNOOZE_DAYS * 86_400_000; } catch { return false; }
}
function snooze(key: string) {
  try { localStorage.setItem(key, String(Date.now())); } catch { /* private mode */ }
}

/**
 * First visit from a phone: offer to install the app and, in the owner cabinet, to turn on notifications.
 * Browsers allow both only from a tap, so this is a sheet with buttons, shown once a week at most.
 */
export function AppPrompt({ audience }: { audience: "client" | "owner" }) {
  const { slug, tenant } = useStudio();
  const { state, install } = useInstall();
  const key = `app-prompt:${slug}:${audience}`;
  const cfg = useQuery({ queryKey: ["push-config", slug], queryFn: () => api<PushConfig>(`${studioApi(slug)}/push/config`), enabled: audience === "owner", staleTime: 60_000 });
  const [open, setOpen] = useState(false);
  const [push, setPush] = useState<PushSupport | null>(null);
  const [pushOn, setPushOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (audience !== "owner" || !cfg.data) return;
    const support = cfg.data.preview ? ({ state: "server-off" } as PushSupport) : detectPush(cfg.data.enabled);
    setPush(support);
    if (support.state === "ready" && Notification.permission === "granted")
      currentEndpoint().then((e) => (e ? api<{ on: boolean }>(`${ownerApi(slug)}/push?endpoint=${encodeURIComponent(e)}`).then((r) => setPushOn(r.on)) : undefined)).catch(() => undefined);
  }, [audience, cfg.data, slug]);

  const canInstall = state !== "installed";
  const canPush = audience === "owner" && (push?.state === "ready" || push?.state === "ios-install") && !pushOn;
  useEffect(() => {
    if (!isPhone() || snoozed(key) || (!canInstall && !canPush)) return;
    if (audience === "owner" && !push) return; // wait until we know whether notifications are possible
    const t = setTimeout(() => setOpen(true), 1200);
    return () => clearTimeout(t);
  }, [key, canInstall, canPush, audience, push]);

  const close = () => { snooze(key); setOpen(false); };
  const enablePush = async () => {
    setBusy(true); setError("");
    try {
      const sub = await subscribePush(slug, cfg.data?.public_key ?? "");
      await api(`${ownerApi(slug)}/push`, { method: "POST", body: { endpoint: sub.endpoint, keys: sub.keys } });
      setPushOn(true);
      if (!canInstall) close();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message === "permission_denied" ? "Вы не разрешили уведомления. Их можно включить позже в разделе «Студия»." : (e as Error).message);
    } finally { setBusy(false); }
  };
  const doInstall = async () => { if (await install() && !canPush) close(); };

  const ios = state === "ios";
  return (
    <AppSheet isOpen={open} onClose={close} label="Приложение" height="hug" bare>
      <div className="app-prompt stack">
        <div className="row" style={{ gap: 14 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={tenant.pwa.icon192} alt="" width={56} height={56} style={{ borderRadius: 14 }} />
          <div><b style={{ fontSize: 19 }}>{tenant.name}</b><div className="muted" style={{ fontSize: 14 }}>{audience === "owner" ? "Кабинет владельца" : "Приложение студии"}</div></div>
        </div>
        {canInstall && (
          <section className="stack" style={{ gap: 8 }}>
            <b>Установите приложение</b>
            <span className="muted" style={{ fontSize: 14 }}>
              {audience === "owner" ? "Кабинет откроется с иконки на экране, как обычное приложение." : "Иконка студии на экране: запись и ваша запись в одно касание."}
            </span>
            {state === "prompt" && <Button label="Установить" icon={<DownloadSimple weight="bold" />} variant="primary" width="100%" onClick={doInstall} />}
            {ios && <ol className="app-prompt-steps"><li>Нажмите «Поделиться» внизу Safari</li><li>Выберите «На экран Домой»</li><li>Нажмите «Добавить»</li></ol>}
            {state === "manual" && <span style={{ fontSize: 14 }}>Откройте меню браузера «⋮» и выберите «Установить приложение» или «Добавить на главный экран».</span>}
          </section>
        )}
        {canPush && (
          <section className="stack" style={{ gap: 8 }}>
            <b>Уведомления о записях</b>
            {push?.state === "ios-install"
              ? <span className="muted" style={{ fontSize: 14 }}>На iPhone уведомления включаются после установки: откройте кабинет с иконки на экране — предложим снова.</span>
              : <>
                  <span className="muted" style={{ fontSize: 14 }}>Сообщим о новой записи, переносе и отмене, даже когда кабинет закрыт.</span>
                  <Button label="Включить уведомления" icon={<BellRinging weight="fill" />} variant={state === "prompt" ? "secondary" : "primary"} width="100%" isLoading={busy} onClick={enablePush} />
                </>}
            {error && <span className="error-text" role="alert">{error}</span>}
          </section>
        )}
        {pushOn && audience === "owner" && <span style={{ color: "#3ddc84", fontSize: 14 }} role="status">Уведомления включены</span>}
        <Button label="Не сейчас" variant="ghost" width="100%" onClick={close} />
      </div>
    </AppSheet>
  );
}
