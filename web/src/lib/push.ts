/** Honest push capability: never promise a notification the device cannot receive. */
export type PushSupport =
  | { state: "ready" } // can subscribe now
  | { state: "denied" } // permission blocked in the browser
  | { state: "ios-install" } // iPhone/iPad Safari tab: only works after "Add to Home Screen"
  | { state: "unsupported" }
  | { state: "insecure" } // opened over plain http (e.g. a local address): browsers allow push only on https
  | { state: "server-off" }; // VAPID keys not configured on the server / preview studio

export const isStandalone = (): boolean =>
  window.matchMedia("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;

export const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

export function detectPush(serverEnabled: boolean): PushSupport {
  if (!serverEnabled) return { state: "server-off" };
  if (!window.isSecureContext) return { state: "insecure" };
  if (isIos() && !isStandalone()) return { state: "ios-install" };
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return { state: "unsupported" };
  if (Notification.permission === "denied") return { state: "denied" };
  return { state: "ready" };
}

const b64ToBytes = (b64: string) => {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

const sameBytes = (a: Uint8Array, b: Uint8Array) => a.length === b.length && a.every((v, i) => v === b[i]);

/** Readable reason when the browser refuses to subscribe (same cases nook handles). */
function subscribeError(e: unknown): Error {
  const name = e instanceof DOMException ? e.name : "";
  const msg = e instanceof Error ? e.message : String(e);
  if (name === "NotAllowedError") return new Error("permission_denied");
  if (name === "AbortError" || /push service/i.test(msg))
    return new Error("Браузер не смог подключиться к сервису уведомлений. В Brave включите «Использовать сервисы Google для push-сообщений». Во встроенных браузерах (Telegram, Instagram) уведомления не работают — откройте ссылку в Chrome или Safari.");
  return new Error(`Не удалось включить уведомления: ${msg}`);
}

export async function subscribePush(slug: string, publicKey: string): Promise<PushSubscriptionJSON> {
  // asking first, right after the tap: iOS shows the prompt only from a user gesture
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("permission_denied");
  const reg = await navigator.serviceWorker.ready;
  const key = b64ToBytes(publicKey);
  try {
    const existing = await reg.pushManager.getSubscription();
    if (existing) {
      const old = existing.options.applicationServerKey;
      if (old && sameBytes(new Uint8Array(old), key)) return existing.toJSON();
      await existing.unsubscribe(); // made with another server key: subscribe again
    }
    return (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key as BufferSource })).toJSON();
  } catch (e) {
    throw subscribeError(e);
  } finally {
    void slug;
  }
}

export async function currentEndpoint(): Promise<string | null> {
  if (!("serviceWorker" in navigator)) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  return (await reg?.pushManager.getSubscription())?.endpoint ?? null;
}

/** Where to turn notifications back on: the site cannot ask again once they are blocked. */
export function deniedHelp(): string {
  const ua = navigator.userAgent;
  if (/android/i.test(ua)) {
    return isStandalone()
      ? "Уведомления выключены. Откройте Настройки Android → Приложения → это приложение → Уведомления и включите их, затем вернитесь сюда."
      : "Уведомления для сайта запрещены. Нажмите значок слева от адреса → Разрешения → Уведомления → Разрешить. Если пункта нет: Настройки Android → Приложения → Chrome → Уведомления. Затем вернитесь сюда.";
  }
  if (/iphone|ipad|ipod/i.test(ua)) return "Уведомления выключены. Откройте Настройки iPhone → Уведомления → это приложение и включите их, затем вернитесь сюда.";
  return "Уведомления для сайта запрещены. Нажмите значок слева от адреса → Уведомления → Разрешить, затем вернитесь на эту страницу.";
}

/** Re-run a check when the user comes back from the system settings (permission may have changed). */
export function onPermissionMaybeChanged(cb: () => void): () => void {
  const vis = () => { if (document.visibilityState === "visible") cb(); };
  document.addEventListener("visibilitychange", vis);
  window.addEventListener("focus", cb);
  let status: PermissionStatus | null = null;
  navigator.permissions?.query({ name: "notifications" as PermissionName }).then((s) => { status = s; s.onchange = cb; }).catch(() => undefined);
  return () => {
    document.removeEventListener("visibilitychange", vis);
    window.removeEventListener("focus", cb);
    if (status) status.onchange = null;
  };
}
