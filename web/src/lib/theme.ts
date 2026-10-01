import { defineTheme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";

/** Readable label colour on top of the accent fill. */
export function onAccent(hex: string): string {
  const v = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.179 ? "#000000" : "#FFFFFF"; // whichever of black/white contrasts more
}

/** Interface colours shared by every studio: warm dark surfaces, a cream action colour. The studio's own colour stays in its logo and photos. */
const CREAM = "#EFE5D3";
const ON_CREAM = "#15120E";

/** One theme per studio. The studio app is always dark. */
export function studioTheme(slug: string, _accent?: string) {
  return defineTheme({
    name: `studio-${slug}`,
    extends: neutralTheme,
    color: { accent: [CREAM, CREAM], neutralStyle: "neutral", contrast: "standard" },
    typography: { body: { family: "Inter Variable", fallbacks: "-apple-system, BlinkMacSystemFont, system-ui, sans-serif" } },
    radius: { base: 6, multiplier: 1.6 },
    tokens: {
      "--color-accent": [CREAM, CREAM],
      "--color-on-accent": [ON_CREAM, ON_CREAM],
      "--color-background-body": ["#0D0C0B", "#0D0C0B"],
      "--color-background-surface": ["#171513", "#171513"],
      "--color-background-card": ["#171513", "#171513"],
      "--color-background-popover": ["#1E1C19", "#1E1C19"],
      "--color-text-primary": ["#F2EDE5", "#F2EDE5"],
    },
  });
}

/** Same accent applied before hydration so the first paint is already on-brand. */
export function accentCss(slug: string, accent: string): string {
  const on = onAccent(accent);
  return `[data-studio="${slug}"]{--studio-accent:${accent};--studio-on-accent:${on};--color-accent:${CREAM};--color-on-accent:${ON_CREAM};--color-background-body:#0D0C0B;}`;
}
