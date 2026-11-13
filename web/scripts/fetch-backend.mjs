// Saves Rahul's real API responses into web/public/data/nasa/, exactly as the service
// returned them (Phase 12). The site loads these files so it works with no network, and
// src/api/adapt.ts turns them into what the screens read, the same way it does for live calls.
//
// Run the backend first (backend branch):  FIELDSHIFT_OFFLINE=1 uvicorn fieldshift.api.app:app
// Then:                                      npm run data            (or FIELDSHIFT_API=https://… npm run data)
//
// Nothing is computed here. The one assembled file, wetness.json, only collects the
// `wetness` block each season's replay already carries, so the past-springs page can show
// modeled soil wetness for every year without loading 45 replays.
import { mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const API = (process.env.FIELDSHIFT_API ?? "http://localhost:8000").replace(/\/$/, "");
const OUT = join(dirname(fileURLToPath(import.meta.url)), "../public/data/nasa");
const ROTATIONS = ["current_practice", "winter_cover", "add_grain_crop"];

async function call(path, body) {
  const res = await fetch(API + path, body ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const text = await res.text();
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status} ${text.slice(0, 200)}`);
  return { text, json: JSON.parse(text) };
}
async function save(name, text) {
  const file = join(OUT, name);
  await mkdir(dirname(file), { recursive: true });
  await writeFile(file, text.endsWith("\n") ? text : text + "\n");
}

await rm(OUT, { recursive: true, force: true });
const health = await call("/health");
const compare = await call("/v1/plans/compare", { rotation_ids: ROTATIONS });
await save("compare.json", compare.text);
await save("rotations.json", (await call("/v1/rotations")).text);

const plans = compare.json.plans.filter((p) => p.status !== "unavailable" && p.plan);
const years = plans.flatMap((p) => p.seasons.map((s) => s.year)).filter((y, i, a) => a.indexOf(y) === i).sort();
const wetness = {};
let replays = 0;
for (const p of plans) {
  await save(`years/${p.plan_id}.json`, (await call(`/v1/years?plan=${encodeURIComponent(p.plan_id)}`)).text);
  wetness[p.plan_id] = {};
  for (const y of years) {
    const r = await call(`/v1/seasons/${y}/replay?plan=${encodeURIComponent(p.plan_id)}`);
    await save(`replay/${p.plan_id}/${y}.json`, r.text);
    wetness[p.plan_id][y] = r.json.wetness ?? null;
    replays++;
  }
}
await save("wetness.json", JSON.stringify(wetness));

const rye = plans.find((p) => p.plan.winter?.kind === "cover" && p.leg === 1);
if (rye) await save("sensitivity.json", (await call("/v1/plans/sensitivity", { plan_id: rye.plan_id })).text);

await save(
  "manifest.json",
  JSON.stringify(
    {
      what: "Responses from the Field Shift backend, saved exactly as returned. wetness.json collects each replay's own wetness block.",
      saved_at: new Date().toISOString(),
      api: API,
      snapshot_hash: compare.json.meta.snapshot_hash,
      catalog_version: compare.json.meta.catalog_version,
      weather: health.json.weather ?? null,
      plans: plans.map((p) => p.plan_id),
      years: [years[0], years[years.length - 1]],
      replays,
    },
    null,
    2,
  ),
);
console.log(`Saved ${plans.length} plans, ${replays} replays, snapshot ${compare.json.meta.snapshot_hash.slice(0, 12)} → ${OUT}`);
