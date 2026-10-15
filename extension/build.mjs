// Bundles the extension into dist/, ready for chrome://extensions → "Load unpacked".
// --release drops the local-development entries (localhost) from the manifest; releases on
// GitHub are built that way by .github/workflows/extension-release.yml.
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import * as esbuild from "esbuild";

const watch = process.argv.includes("--watch");
const release = process.argv.includes("--release");

await rm("dist", { recursive: true, force: true });
await mkdir("dist");
await cp("static", "dist", { recursive: true });

if (release) {
  const manifest = JSON.parse(await readFile("static/manifest.json", "utf8"));
  const local = (pattern) => /^https?:\/\/localhost[:/]/.test(pattern);
  manifest.host_permissions = manifest.host_permissions.filter((p) => !local(p));
  for (const script of manifest.content_scripts) script.matches = script.matches.filter((p) => !local(p));
  await writeFile("dist/manifest.json", `${JSON.stringify(manifest, null, 2)}\n`);
}

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
