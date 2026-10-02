import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/** Makes the browser/OS Back button close an open sheet instead of leaving the page. */
export function useBackClose(isOpen: boolean, onClose: () => void) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!isOpen) return;
    history.pushState({ sheet: true }, "");
    const onPop = () => closeRef.current();
    window.addEventListener("popstate", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
      if ((history.state as { sheet?: boolean } | null)?.sheet) history.back();
    };
  }, [isOpen]);
}

/** true once the component is mounted in the browser (avoids SSR/CSR clock mismatches). */
export function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

/** One-shot `?do=…` request from the owner assistant: returns it once, then drops it from the URL. */
export function useDoParam(ready = true): URLSearchParams | null {
  const [req, setReq] = useState<URLSearchParams | null>(null);
  const params = useSearchParams();
  const want = params.get("do");
  useEffect(() => {
    if (!ready || !want) return;
    setReq(new URLSearchParams(params.toString()));
    history.replaceState(history.state, "", window.location.pathname);
  }, [ready, want]); // eslint-disable-line react-hooks/exhaustive-deps
  return req;
}

/**
 * Navigate away from an open sheet without racing its history entry: pop the sheet's entry first
 * (the sheet closes itself on popstate), then push the destination.
 */
export function navigateFromSheet(push: (href: string) => void, href: string): void {
  if ((history.state as { sheet?: boolean } | null)?.sheet) {
    window.addEventListener("popstate", () => push(href), { once: true });
    history.back();
  } else push(href);
}
