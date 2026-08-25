import { copyFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = join(root, "node_modules/@electric-sql/pglite/dist");
const destDir = join(root, ".vercel/output/functions/__server.func/_libs");
const files = ["pglite.data", "pglite.wasm", "initdb.wasm"];

if (!existsSync(destDir)) {
  console.log("[pglite-assets] no vercel server output — skip");
  process.exit(0);
}
mkdirSync(destDir, { recursive: true });
for (const f of files) {
  copyFileSync(join(srcDir, f), join(destDir, f));
}
console.log("[pglite-assets] copied wasm/data next to bundled PGLite for vite preview");
