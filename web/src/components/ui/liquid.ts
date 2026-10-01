/**
 * Real refracting glass through liquid-gl (WebGPU -> WebGL2 -> WebGL1 -> CSS backdrop-filter).
 *
 * - Only the hero call-to-action gets a lens. liquid-gl ignores position:fixed elements, so the bottom
 *   navigation keeps the CSS glass (backdrop-filter), which is real blur/saturation glass in every browser.
 * - The lens snapshots #hero only, so text from neighbouring sections can never show through the button.
 * - `content: false` keeps the button label as ordinary DOM text on top of the lens: it stays sharp.
 * - Enabled with NEXT_PUBLIC_LIQUID_GL=1 (see below). Skipped for reduced-transparency / data-saver users, and any failure falls back to the CSS glass.
 */
interface Lens {
  destroy?: () => void;
}

const LENS_IDS = new Set(["hero-cta"]);

export function attachLens(el: HTMLElement, _opts: { radius: number }): (() => void) | undefined {
  // Opt-in: NEXT_PUBLIC_LIQUID_GL=1. In headless software WebGL the lens rendered as a black box and no real
  // device was available to verify it, so the verified CSS glass is the default.
  if (process.env.NEXT_PUBLIC_LIQUID_GL !== "1") return undefined;
  const id = el.dataset.glass;
  if (!id || !LENS_IDS.has(id)) return undefined;
  const conn = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  if (window.matchMedia("(prefers-reduced-transparency: reduce)").matches || conn?.saveData) return undefined;
  const hero = document.getElementById("hero");
  if (!hero) return undefined;

  let lens: Lens | undefined;
  let disposed = false;
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--studio-accent").trim() || "#4690FF";
  const start = async () => {
    try {
      const mod = (await import("liquid-gl")) as unknown as { default: (o: Record<string, unknown>) => Lens | Lens[] };
      if (disposed) return;
      el.classList.add("liquidGL");
      const made = mod.default({
        target: `[data-glass="${id}"]`,
        snapshot: "#hero",
        resolution: 1.5,
        refraction: 0.02,
        bevelDepth: 0.12,
        bevelWidth: 0.22,
        frost: 1.2,
        shadow: false,
        specular: true,
        reveal: "fade",
        content: false,
        tint: `${accent}55`,
      });
      lens = Array.isArray(made) ? { destroy: () => made.forEach((l) => l.destroy?.()) } : made;
    } catch {
      el.classList.remove("liquidGL"); // CSS glass stays
    }
  };
  // wait for the hero photo so the snapshot contains the picture, not a black box
  const img = hero.querySelector("img");
  if (img && !img.complete) img.addEventListener("load", start, { once: true });
  else void start();
  return () => {
    disposed = true;
    lens?.destroy?.();
    el.classList.remove("liquidGL");
  };
}
