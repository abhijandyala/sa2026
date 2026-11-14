// Saves Rahul's real API responses into web/public/data/nasa/, exactly as the service
// returned them (Phase 12). The site loads these files so it works with no network, and
// src/api/adapt.ts turns them into what the screens read, the same way it does for live calls.
//
// Run the backend first (backend branch):  FIELDSHIFT_OFFLINE=1 uvicorn fieldshift.api.app:app
// Then:                                      npm run data            (or FIELDSHIFT_API=https://… npm run data)
//
// Nothing is computed here: every file is one response, byte for byte.
//
// One folder per place the backend has a NASA record for (GET /health lists them), so every
// county in the place picker opens with no live service:
//   <place>/compare.json, <place>/sensitivity.json, <place>/years/<plan>.json,
//   <place>/replay/<plan>/<year>.json, and rotations.json (the same for every place).
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
await save("rotations.json", (await call("/v1/rotations")).text);

// The backend's own list of places with a committed NASA POWER snapshot.
const places = health.json.locations ?? [{ id: "union", name: "Union County" }];
const saved = [];
let replays = 0;
for (const place of places) {
  const at = `location_id=${encodeURIComponent(place.id)}`;
  const compare = await call("/v1/plans/compare", { rotation_ids: ROTATIONS, location_id: place.id });
  await save(`${place.id}/compare.json`, compare.text);

  const plans = compare.json.plans.filter((p) => p.status !== "unavailable" && p.plan);
  const years = plans.flatMap((p) => p.seasons.map((s) => s.year)).filter((y, i, a) => a.indexOf(y) === i).sort();
  for (const p of plans) {
    const plan = encodeURIComponent(p.plan_id);
    await save(`${place.id}/years/${p.plan_id}.json`, (await call(`/v1/years?plan=${plan}&${at}`)).text);
    for (const y of years) {
      await save(`${place.id}/replay/${p.plan_id}/${y}.json`, (await call(`/v1/seasons/${y}/replay?plan=${plan}&${at}`)).text);
      replays++;
    }
  }

  const rye = plans.find((p) => p.plan.winter?.kind === "cover" && p.leg === 1);
  if (rye) await save(`${place.id}/sensitivity.json`, (await call("/v1/plans/sensitivity", { plan_id: rye.plan_id, location_id: place.id })).text);

  saved.push({
    id: place.id,
    name: place.name ?? compare.json.weather_location?.name ?? place.id,
    snapshot_hash: compare.json.meta.snapshot_hash,
    region: compare.json.weather_location?.region ?? null,
    plans: plans.map((p) => p.plan_id),
    years: [years[0], years[years.length - 1]],
  });
  console.log(`  ${place.id}: ${plans.length} plans, snapshot ${String(compare.json.meta.snapshot_hash).slice(0, 12)}`);
}

await save(
  "manifest.json",
  JSON.stringify(
    {
      what: "Responses from the Field Shift backend, saved exactly as returned, one folder per place.",
      saved_at: new Date().toISOString(),
      api: API,
      catalog_version: health.json.meta?.catalog_version ?? null,
      weather: health.json.weather ?? null,
      places: saved,
      replays,
    },
    null,
    2,
  ),
);
console.log(`Saved ${saved.length} places, ${replays} replays → ${OUT}`);
