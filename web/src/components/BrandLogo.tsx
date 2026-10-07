"use client";

import { useState } from "react";

/** Studio logo for headers: a round badge for square logos, a dark pill showing the whole logo for wide ones. */
export function BrandLogo({ src, name }: { src: string | null; name: string }) {
  const [wide, setWide] = useState(false);
  return (
    <span className={`brand-logo${wide ? " wide" : ""}`}>
      {src
        ? /* eslint-disable-next-line @next/next/no-img-element */
          <img src={src} alt={wide ? name : ""} onLoad={(e) => setWide(e.currentTarget.naturalWidth / e.currentTarget.naturalHeight > 1.6)} />
        : name.slice(0, 1)}
    </span>
  );
}
