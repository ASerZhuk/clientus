"use client";

import { useEffect, useRef } from "react";

interface Props extends React.HTMLAttributes<HTMLElement> {
  as?: "div" | "button";
  type?: "button" | "submit";
  radius?: number;
  id: string;
}

/** CSS glass (backdrop-filter) everywhere; upgraded to a real refracting lens by ./liquid.ts when the device can do it. */
export function GlassSurface({ as: Tag = "div", radius = 20, id, className = "", style, children, ...rest }: Props) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let dispose: (() => void) | undefined;
    let cancelled = false;
    import("./liquid").then(({ attachLens }) => {
      if (!cancelled) dispose = attachLens(el, { radius });
    });
    return () => {
      cancelled = true;
      dispose?.();
    };
  }, [radius]);
  const Component = Tag as React.ElementType;
  return (
    <Component ref={ref} data-glass={id} className={`glass ${className}`} style={{ borderRadius: radius, ...style }} {...rest}>
      {children}
    </Component>
  );
}
