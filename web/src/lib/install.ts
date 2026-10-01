"use client";

import { useSyncExternalStore } from "react";
import { isStandalone } from "./push";

/** Chrome/Edge/Samsung Internet hand the page an install prompt once per load; keep it app-wide so any button can use it. */
interface InstallEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: InstallEvent | null = null;
let installed = false;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // keep it for our own button instead of the browser's mini-bar
    deferred = e as InstallEvent;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    installed = true;
    deferred = null;
    emit();
  });
}

export type InstallState = "installed" | "prompt" | "ios" | "manual";

function snapshot(): InstallState {
  if (installed || isStandalone()) return "installed";
  if (deferred) return "prompt";
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  return ios ? "ios" : "manual";
}

/** "prompt": one tap opens the system install dialog; "ios": Apple allows only Share → Add to Home Screen; "manual": browser menu. */
export function useInstall(): { state: InstallState; install: () => Promise<boolean> } {
  const state = useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    snapshot,
    () => "manual" as InstallState,
  );
  const install = async () => {
    if (!deferred) return false;
    const e = deferred;
    deferred = null; // a prompt can be shown only once
    await e.prompt();
    const { outcome } = await e.userChoice;
    if (outcome === "accepted") installed = true;
    emit();
    return outcome === "accepted";
  };
  return { state, install };
}
