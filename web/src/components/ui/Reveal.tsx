"use client";

import { useEffect, useRef } from "react";

/** Fades a section in when it scrolls into view. Disabled by prefers-reduced-motion (see CSS). */
export function Reveal({ children, as: Tag = "section", className = "", ...rest }: React.HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "article" }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.classList.add("in");
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries)
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const Component = Tag as React.ElementType;
  return (
    <Component ref={ref} className={`reveal ${className}`} {...rest}>
      {children}
    </Component>
  );
}
