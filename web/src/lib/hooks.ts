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
