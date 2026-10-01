import { headers } from "next/headers";
import { cache } from "react";
import type { TenantPublic } from "./types";

const API = process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8000";

/** Server-side read of a studio's public config (deduplicated per request). null = unknown studio. */
export const getTenant = cache(async (slug: string): Promise<TenantPublic | null> => {
  if (!/^[a-z0-9][a-z0-9-]{1,40}$/.test(slug)) return null;
  const res = await fetch(`${API}/api/s/${slug}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API answered ${res.status} for studio config`);
  return (await res.json()) as TenantPublic;
});

/** "" on a customer's own domain (the studio lives at the root), "/s/<slug>" on the platform host. */
export async function getBase(slug: string): Promise<string> {
  return (await headers()).get("x-studio-custom") === "1" ? "" : `/s/${slug}`;
}
