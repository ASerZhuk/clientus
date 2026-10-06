"use client";

import { ArrowSquareOut } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

/** Browsers built into messengers and social apps: no "Add to Home Screen", no push, often no saved booking. */
const IN_APP = /Telegram|Instagram|FBAN|FBAV|FB_IAB|FBIOS|VKClient|vkontakte|WhatsApp|OKApp|MicroMessenger|Line\/|LinkedInApp|Snapchat|; wv\)/i;

type Kind = "ios" | "android";

function detect(): Kind | null {
  const ua = navigator.userAgent;
  if (!IN_APP.test(ua)) return null;
  if (/iphone|ipad|ipod/i.test(ua)) return "ios";
  if (/android/i.test(ua)) return "android";
  return null;
}

/** Opens the current page in the real browser: Chrome via an Android intent, Safari via x-safari-https (iOS 17+). */
function openOutside(kind: Kind) {
  const url = new URL(window.location.href);
  if (kind === "android") {
    window.location.href = `intent://${url.host}${url.pathname}${url.search}${url.hash}#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=${encodeURIComponent(url.href)};end`;
  } else {
    window.location.href = `x-safari-${url.href}`;
  }
}

export function InAppBrowserBar() {
  const [kind, setKind] = useState<Kind | null>(null);
  useEffect(() => setKind(detect()), []);
  if (!kind) return null;
  const name = kind === "ios" ? "Safari" : "Chrome";
  return (
    <div className="inapp-bar" role="region" aria-label="Открыть в браузере">
      <span>Откройте в {name}, чтобы записаться и получать напоминания</span>
      <button type="button" onClick={() => openOutside(kind)}><ArrowSquareOut weight="bold" aria-hidden /> {name}</button>
    </div>
  );
}
