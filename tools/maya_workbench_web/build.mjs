import { build } from "esbuild"
import { spawnSync } from "node:child_process"
import { readFile, writeFile, mkdir, readdir } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import path from "node:path"

const source = path.dirname(fileURLToPath(import.meta.url))
const output = path.resolve(source, "../../Plugins/AssetForge/Resources/Workbench/web")
await mkdir(output, { recursive: true })
const tailwind = path.join(source, "node_modules/tailwindcss/lib/cli.js")
const css = spawnSync(process.execPath, [tailwind, "-c", "tailwind.config.cjs", "-i", "styles.css", "-o", path.join(output,"app.css"), "--minify"], {cwd: source, stdio: "inherit"})
if (css.status !== 0) process.exit(css.status || 1)
await build({
  absWorkingDir: source, entryPoints: ["main.tsx"], outfile: path.join(output,"app.js"),
  alias: { "@/lib/utils": path.join(source, "lib/utils.ts") },
  bundle: true, minify: true, format: "iife", target: "chrome69",
  jsx: "automatic", define: { globalThis: "window", "process.env.NODE_ENV": '"production"' }, legalComments: "none",
})
const upstream = JSON.parse(await readFile(path.join(source,"upstream.json"),"utf8"))
const notices = ["shadcn/ui (" + upstream.repository + ", commit " + upstream.commit + ")",
  await readFile(path.join(source,"components/LICENSE"),"utf8")]
const lock = JSON.parse(await readFile(path.join(source,"package-lock.json"),"utf8"))
for (const [dir, entry] of Object.entries(lock.packages)) {
  if (!dir || (entry.dev && !["node_modules/tailwindcss", "node_modules/esbuild"].includes(dir))) continue
  const pkg = path.join(source,dir)
  const meta = JSON.parse(await readFile(path.join(pkg,"package.json"),"utf8"))
  let files = (await readdir(pkg)).filter(name => /^(licen[sc]e|copying|notice)(\..*)?$/i.test(name))
  if (!files.length && meta.name.startsWith("@radix-ui/") && meta.license === "MIT") {
    files = [path.join(source, "components/RADIX-LICENSE")]
  }
  if (!files.length && meta.name === "react-remove-scroll-bar") {
    files = [path.join(source, "components/SCROLL-BAR-LICENSE")]
  }
  if (!files.length) throw Error("No distribution license for " + meta.name)
  notices.push(meta.name + " " + meta.version + " — " + meta.license)
  for (const f of files) notices.push(await readFile(path.resolve(pkg,f),"utf8"))
}
await writeFile(path.join(output,"THIRD-PARTY.txt"),notices.join("\n\n") + "\n")
