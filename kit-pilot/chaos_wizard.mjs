// Chaos for the in-app wizard's engine (app/frontend/src/components/installEngine.ts): the same fake
// kit, faults and laws as chaos.py, applied to the TypeScript engine running headless in Node.
// Run (from kit-pilot/): node chaos_wizard.mjs <chaos_server port> [random-runs]
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import fs from "node:fs";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "..", "app", "frontend");
const require = createRequire(path.join(frontend, "package.json"));
const esbuild = require("esbuild");
const port = Number(process.argv[2]);
const runs = Number(process.argv[3] ?? 3000);
const base = `http://127.0.0.1:${port}`;

// --- bundle the engine with its real imports (api.ts, storageInstall.ts) for Node
const out = path.join(here, ".chaos-install-engine.mjs");
await esbuild.build({
  entryPoints: [path.join(frontend, "src", "components", "installEngine.ts")], bundle: true, format: "esm", platform: "node", outfile: out,
  jsx: "automatic", define: { "import.meta.env.VITE_API_BASE_URL": JSON.stringify(base) }, logLevel: "silent",
});
const realSetTimeout = globalThis.setTimeout;
globalThis.window = { setTimeout: realSetTimeout, clearTimeout, dispatchEvent() {}, addEventListener() {}, removeEventListener() {} };
// Waits of a second or more (power-off polling, retry pauses) pass instantly; request timeouts stay real.
globalThis.setTimeout = (fn, ms, ...rest) => realSetTimeout(fn, ms >= 1000 ? 0 : ms, ...rest);
globalThis.Event = globalThis.Event ?? class {};
const engine = await import(pathToFileURL(out).href);
const { runInstall, STAGES, NeedsYou, Paused } = engine;

// --- the fetch wrapper decides the fault for request N (lost/503 via header; pause/kill here)
class Killed extends Error {}
let faults = {}, n = 0, stop = false;
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, init = {}) => {
  n += 1;
  const fault = faults[n];
  if (fault === "kill") throw new Killed("killed");
  const headers = { ...(init.headers || {}) };
  if (fault === "lost" || fault === "503") headers["X-Chaos"] = fault;
  let response;
  try { response = await realFetch(url, { ...init, headers }); }
  finally { if (fault === "pause") { stop = true; await control("/__paused"); } }
  return response;
};
const control = (p, q = "") => realFetch(base + p + q, { method: p === "/__result" || p === "/__laws" ? "GET" : "POST" }).then(r => r.json());

const ctx = () => ({
  profileId: "fixture", servers: [{ deviceId: "srv", name: "Server" }], switches: [{ deviceId: "sw", name: "Switch" }],
  say() {}, warn() {},
  stopIf() { if (stop) throw new Paused(); },
  async sleep() { if (stop) throw new Paused(); },
});

async function fly(schedule) {
  faults = schedule; n = 0; stop = false;
  await control("/__reset");
  let start = 0, outcome = "unfinished";
  for (let attempt = 0; attempt < 6; attempt++) {
    let current = start;
    try {
      await runInstall(ctx(), start, (index) => { current = index; });
      outcome = "done"; break;
    } catch (err) {
      current = Math.max(current, start);
      if (process.env.CHAOS_ONLY) console.log(`attempt ${attempt} leg ${current}: ${err?.constructor?.name}: ${String(err?.message).slice(0, 120)} (requests so far ${n})`);
      if (err instanceof Paused) { stop = false; await control("/__unpause"); start = current; }
      else if (err instanceof Killed) { start = current; }
      else if (err instanceof NeedsYou || err instanceof Error) { start = current; }
      else throw err;
    }
  }
  const broken = await control("/__laws", `?outcome=${outcome}`);
  const result = await control("/__result");
  return { outcome, broken, requests: result.requests };
}

if (process.env.CHAOS_ONLY) {
  const [pos, fault] = process.env.CHAOS_ONLY.split(":");
  const timer = realSetTimeout(() => { console.log(`TIMEOUT after ${n} requests`); process.exit(3); }, 20000);
  console.log(await fly({ [Number(pos)]: fault }));
  clearTimeout(timer); fs.rmSync(out, { force: true }); process.exit(0);
}
const baseline = await fly({});
if (baseline.outcome !== "done" || baseline.broken.length) { console.log("baseline failed", baseline); process.exit(2); }
console.log(`wizard baseline: ${baseline.requests} requests, laws hold`);
const failures = [];
let scenarios = 0;
for (let position = 1; position <= baseline.requests; position++) {
  for (const fault of ["lost", "503", "pause", "kill"]) {
    if (process.env.CHAOS_TRACE) process.stdout.write(`${position}:${fault} `); const r = await fly({ [position]: fault }); scenarios++;
    if (r.broken.length) failures.push([{ [position]: fault }, r.broken]);
  }
}
console.log(`wizard single faults: ${scenarios} scenarios, ${failures.length} broke a law`);
let seed = 2026; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
let multi = 0;
for (let i = 0; i < runs; i++) {
  const schedule = {}; const count = 2 + Math.floor(rnd() * 3);
  for (let k = 0; k < count; k++) schedule[1 + Math.floor(rnd() * (baseline.requests + 40))] = ["lost", "503", "pause", "kill"][Math.floor(rnd() * 4)];
  const r = await fly(schedule);
  if (r.broken.length) { multi++; if (failures.length < 40) failures.push([schedule, r.broken]); }
}
console.log(`wizard random multi-fault: ${runs} flights, ${multi} broke a law`);
const seen = new Set();
for (const [schedule, broken] of failures) {
  const key = broken.map(b => b.split(" sent")[0].split(" ended")[0]).sort().join("|");
  if (!seen.has(key) || seen.size < 12) { seen.add(key); console.log("  " + JSON.stringify(schedule) + " -> " + JSON.stringify(broken).slice(0, 260)); }
}
fs.rmSync(out, { force: true });
process.exit(failures.length || multi ? 1 : 0);
