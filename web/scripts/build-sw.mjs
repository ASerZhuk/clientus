// Bundles src/sw/sw.ts (with Serwist) into public/_sw.js. The route /s/<slug>/sw.js serves it.
import { build } from "esbuild";

await build({
  entryPoints: ["src/sw/sw.ts"],
  outfile: "public/_sw.js",
  bundle: true,
  minify: true,
  format: "iife",
  target: "es2020",
  define: { __BUILD__: JSON.stringify(String(Date.now())), "process.env.NODE_ENV": '"production"' },
  logLevel: "info",
});
