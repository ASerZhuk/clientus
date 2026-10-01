import { readFile } from "node:fs/promises";
import path from "node:path";
import { getBase, getTenant } from "@/lib/server";

let cached: string | null = null;

/** The same worker source for every studio; the URL (/s/<slug>/sw.js) fixes its scope and cache names. */
export async function GET(_req: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!(await getTenant(slug))) return new Response("Not found", { status: 404 });
  cached ??= await readFile(path.join(process.cwd(), "public", "_sw.js"), "utf8");
  return new Response(cached, {
    headers: {
      "Content-Type": "text/javascript; charset=utf-8",
      "Service-Worker-Allowed": `${await getBase(slug)}/`,
      "Cache-Control": "no-cache, no-store, must-revalidate",
    },
  });
}
