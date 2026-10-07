"use client";

import { useEffect, useRef, useState } from "react";

/** Studio logo for headers: a round badge for square logos, a dark pill showing the whole logo for wide ones. */
export function BrandLogo({ src, name }: { src: string | null; name: string }) {
  const [wide, setWide] = useState(false);
  const ref = useRef<HTMLImageElement>(null);
  const check = (img: HTMLImageElement) => { if (img.naturalWidth) setWide(img.naturalWidth / img.naturalHeight > 1.6); };
  // the image is often already loaded (cache, server render) before React attaches onLoad
  useEffect(() => { if (ref.current?.complete) check(ref.current); }, [src]);
  return (
    <span className={`brand-logo${wide ? " wide" : ""}`}>
      {src
        ? /* eslint-disable-next-line @next/next/no-img-element */
          <img ref={ref} src={src} alt={wide ? name : ""} onLoad={(e) => check(e.currentTarget)} />
        : name.slice(0, 1)}
    </span>
  );
}
