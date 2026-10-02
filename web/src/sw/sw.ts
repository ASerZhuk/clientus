/// <reference lib="webworker" />
/**
 * One source, one worker per studio. The route /s/<slug>/sw.js serves this file, so every
 * studio gets its own scope (/s/<slug>/) and its own cache names (studio-<slug>-*).
 * Private data (cabinet, "my booking", any owner/my API call) is never cached.
 */
import { CacheFirst, ExpirationPlugin, NetworkFirst, NetworkOnly, Serwist, StaleWhileRevalidate } from "serwist";

declare const self: ServiceWorkerGlobalScope;
declare const __BUILD__: string;

const params = new URL(self.location.href).searchParams;
const slug = params.get("s") ?? new URL(self.location.href).pathname.split("/")[2] ?? "studio";
const base = params.get("b") ?? `/s/${slug}`; // "" on a customer's own domain
const scope = `${base}/`;
const id = `studio-${slug}`;

const isPrivateApi = (p: string) => p.startsWith(`/api/s/${slug}/owner`) || p.startsWith(`/api/s/${slug}/my/`);
const isPrivatePage = (p: string) => p.startsWith(`${scope}owner`) || p.startsWith(`${scope}my`);

const serwist = new Serwist({
  cacheId: id,
  precacheEntries: [{ url: `${scope}offline`, revision: __BUILD__ }],
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    // 1. private: always the network, nothing is stored
    { matcher: ({ url }) => isPrivateApi(url.pathname) || isPrivatePage(url.pathname), handler: new NetworkOnly() },
    // 2. the studio's public config: show the last known copy instantly, refresh in the background
    {
      matcher: ({ url, request }) => request.method === "GET" && url.pathname === `/api/s/${slug}`,
      handler: new StaleWhileRevalidate({ cacheName: `${id}-config`, plugins: [new ExpirationPlugin({ maxEntries: 4, maxAgeSeconds: 7 * 86400 })] }),
    },
    // 3. this studio's photos
    {
      matcher: ({ url }) => url.pathname.startsWith(`/api/media/${slug}/`),
      handler: new CacheFirst({ cacheName: `${id}-images`, plugins: [new ExpirationPlugin({ maxEntries: 80, maxAgeSeconds: 30 * 86400 })] }),
    },
    // 4. fingerprinted app code
    {
      matcher: ({ url }) => url.pathname.startsWith("/_next/static/"),
      handler: new CacheFirst({ cacheName: `${id}-static`, plugins: [new ExpirationPlugin({ maxEntries: 120, maxAgeSeconds: 30 * 86400 })] }),
    },
    // 5. public pages of this studio: network first, cached copy when offline
    {
      matcher: ({ request, url }) => request.mode === "navigate" && url.pathname.startsWith(scope),
      handler: new NetworkFirst({ cacheName: `${id}-pages`, networkTimeoutSeconds: 4, plugins: [new ExpirationPlugin({ maxEntries: 12 })] }),
    },
  ],
  fallbacks: {
    entries: [{ url: `${scope}offline`, matcher: ({ request }) => request.destination === "document" }],
  },
});
serwist.addEventListeners();

// ---- Web Push ---------------------------------------------------------------------------
interface PushPayload {
  title: string;
  body: string;
  url?: string;
  tag?: string;
  kind?: string; // new | cancelled | moved | reminder
  badge?: number; // owner: client bookings not seen yet
}

type BadgeNavigator = WorkerNavigator & { setAppBadge?: (n?: number) => Promise<void>; clearAppBadge?: () => Promise<void> };

self.addEventListener("push", (event) => {
  let data: PushPayload = { title: "Уведомление", body: "" };
  try {
    const raw = event.data?.json() as (PushPayload & { web_push?: number; notification?: { title: string; body?: string; navigate?: string; tag?: string; app_badge?: number } }) | null;
    if (raw?.web_push === 8030 && raw.notification) {
      // Declarative Web Push: the same message Safari can display on its own; here we display it ourselves
      const n = raw.notification;
      data = { title: n.title, body: n.body ?? "", url: n.navigate, tag: n.tag, kind: raw.kind, badge: n.app_badge };
    } else if (raw) {
      data = { ...data, ...raw };
    }
  } catch {
    /* plain-text payload */
  }
  const nav = self.navigator as BadgeNavigator;
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(data.title, {
        body: data.body,
        tag: data.tag,
        icon: `/api/media/${slug}/pwa/icon-192.png`,
        badge: `/api/media/${slug}/pwa/badge-96.png`, // Android status bar: white silhouette on transparency
        data: { url: data.url ?? scope },
      }),
      // number on the app icon (Android, installed iPhone app); the cabinet clears it when the schedule is opened
      typeof data.badge === "number" && nav.setAppBadge ? (data.badge > 0 ? nav.setAppBadge(data.badge) : nav.clearAppBadge?.()).catch(() => undefined) : undefined,
      // an open app refreshes its data right away (schedule, "my booking") instead of waiting for the next poll
      self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => list.forEach((c) => c.postMessage({ type: "push", kind: data.kind ?? null }))),
    ]),
  );
});

// The browser may replace a subscription (expiry, key rotation): subscribe again and move the server records,
// otherwise notifications would silently stop until the person switches them on again.
self.addEventListener("pushsubscriptionchange", ((event: Event & { oldSubscription?: PushSubscription | null; newSubscription?: PushSubscription | null }) => {
  const old = event.oldSubscription;
  if (!old) return; // nothing to map from: the app re-subscribes when it is opened
  (event as ExtendableEvent).waitUntil(
    (async () => {
      const fresh = event.newSubscription ?? (await self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: old.options.applicationServerKey }));
      const json = fresh.toJSON();
      await fetch(`/api/s/${slug}/push/rotate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_endpoint: old.endpoint, subscription: { endpoint: json.endpoint, keys: json.keys } }),
      });
    })().catch(() => undefined),
  );
}) as EventListener);

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const raw = (event.notification.data as { url?: string } | undefined)?.url ?? scope;
  const local = base === "" ? raw.replace(new RegExp(`^/s/${slug}`), "") || "/" : raw; // server URLs are platform paths
  const target = new URL(local, self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      const open = list.find((c) => c.url.startsWith(self.location.origin + scope));
      return open ? open.focus().then(() => ("navigate" in open ? (open as WindowClient).navigate(target) : undefined)) : self.clients.openWindow(target);
    }),
  );
});
