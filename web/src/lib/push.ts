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

const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

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

export async function subscribePush(slug: string, publicKey: string): Promise<PushSubscriptionJSON> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("permission_denied");
  const reg = await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(publicKey) as BufferSource }));
  void slug;
  return sub.toJSON();
}

export async function currentEndpoint(): Promise<string | null> {
  if (!("serviceWorker" in navigator)) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  return (await reg?.pushManager.getSubscription())?.endpoint ?? null;
}

export async function unsubscribePush(): Promise<string | null> {
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  if (!sub) return null;
  const endpoint = sub.endpoint;
  await sub.unsubscribe();
  return endpoint;
}
