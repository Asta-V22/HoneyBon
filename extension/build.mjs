// Bundles the extension into dist/, ready for chrome://extensions → "Load unpacked".
import { cp, mkdir, rm } from "node:fs/promises";
import * as esbuild from "esbuild";

const watch = process.argv.includes("--watch");

await rm("dist", { recursive: true, force: true });
await mkdir("dist");
await cp("static", "dist", { recursive: true });

const options = {
  entryPoints: ["src/background.ts", "src/bridge.ts", "src/content.ts", "src/page-hook.ts", "src/popup.ts"],
  outdir: "dist",
  bundle: true,
  format: "iife",
  target: "chrome120",
  logLevel: "info",
};

if (watch) {
  await (await esbuild.context(options)).watch();
} else {
  await esbuild.build(options);
}
