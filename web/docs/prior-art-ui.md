# Prior art: the playbook's GitHub repos, read for UI (Nov 13, 2026)

The playbook's "GitHub & prior art" chapter (pp. 79–89) links 32 repositories. This note records what each looks like, its stack and license, and what A.C.R.E takes from it. Live sites were opened in a browser on Nov 13; the rest were read from their README and package files.

**Rule we follow** (playbook p.79, citing the Space Apps Navigator on code reuse): other teams' Field Shift repos are reading material. We take ideas and patterns, never their code or art. Reusing code from anyone needs license permission and a recorded notice; a repo with no license cannot be reused at all.

## Not all Python

Only the libraries and two Streamlit prototypes are Python. The playbook's main build route was Python (Streamlit + Altair), which is why its tool list reads that way. Most competing prototypes ship React or Next.js frontends with Tailwind, Leaflet or MapLibre maps and Recharts charts, often over a Python or Node backend.

## Competing Field Shift prototypes (2026)

| Repo | Live | Stack | License | What it looks like |
| --- | --- | --- | --- | --- |
| padmakarpimpale/agrishift | agrishift-two.vercel.app | Vanilla JS + Node API | none | Cream and evergreen, serif display with italic accent ("Make room for *uncertainty*"), numbered section eyebrows ("FIELD ANALYSIS / 02"), sidebar form, "Climate time machine" rainfall-stress slider, "Your Plan B", "Every number has a source" with Verify / Export JSON / Print report. Closest to A.C.R.E in tone. |
| Zul-Qarnain/field-shift | field-shift-tan.vercel.app | Next.js, MapLibre, Recharts | Apache-2.0 | Dark dashboard with sidebar nav, satellite map, KPI tiles, "Quick answer: three ranked plans on one screen", "See why" arithmetic, "two eras compared" onset chart, leave-one-out backtest, Bangla, installable app. The most complete competitor. |
| tejaswi-raghav/field-shift | field-shift.vercel.app | Next.js, shadcn/Radix, Recharts | none | Cream grid paper, big serif headline, 4-step wizard card ("01 / 04 Location") with region preset tiles and a map, "Demo-safe" badge, dark footer strip "Regional evidence, clearly labelled" with source chips. |
| Ridwanulkarim/field-shift (Aboho) | field-shift-agrinomy.vercel.app | Node + frontend | Apache-2.0 | Marketing hero in deep green with a field-diagram illustration, then feature cards. |
| tanvir-piyal-codehub/TeraCrop-AI | terra-crop.vercel.app | React 19, Leaflet, Phaser, Gemini | Apache-2.0 | Misty photo hero, "Powered by" data chips, an AI chat guide and a pixel-art farm game for children. |
| ASHIK311/agrisense-fusion | adspro.online (blocked) | JavaScript | MIT | "Digital twin" of a Bangladesh tract from Sentinel-2. |
| rzprince/NASA-SPACE-APPS-Challenge-2026 (BoponX) | — | React, MapLibre, three.js | NOASSERTION | 3D globe "Earth twin" with NASA GIBS satellite layers; neon-on-black styling. The only other 3D. |
| Spongly/FarmShift | — | React, Leaflet, Recharts, Tailwind | MIT | Photo-led editorial home, farm workspace with map pin, GIBS map layers, advisories. |
| yunusarfat/…GreenOrbit | — | React, Leaflet, Recharts | none | Click-the-map location, quick-pick cities, monthly charts, top-three ranking. |
| Nilkamal21/Field-Shift | — | React, Leaflet, Recharts + FastAPI | none | Satellite map, GPS, draw-the-field "connect 4 dots". |
| Hamidcodedot/FieldShift | — | React, Tailwind, Leaflet, Capacitor | none | Android app with voice input and read-aloud; 12-month agroclimate dashboard. |
| XtremeseOISHEE/RotaShift | — | single HTML file | none | Local evidence-transparent MVP with descriptive rainfall charts. |
| ScriptySphere/Krishi-Bondhu, moshiour0/krishiNexus4 | — | Python + web UI | none | API-first, mobile demo page. |
| sagar25446-prog/FieldShift-NASA | — | Streamlit | MIT | The playbook's Streamlit example. |
| INNOVATRIX-2026/Smart-Crop-Decision-Assistant | — | Streamlit | Apache-2.0 | Streamlit forms and tables. |
| anirban-islam/farmstack | — | README only | none | Plan, no code. |
| giorgosmelas2/Crop-Rotation-Website | — | TypeScript | none | 2025 rotation planner UI. |

## Real farm tools and libraries

| Repo | License | Use for us |
| --- | --- | --- |
| precision-sustainable-ag/dst-selector (covercrop-selector.org) | MIT | A real cover-crop tool farmers use: map or state picker, "Get a recommendation" guided path next to "Browse", photo of the crop. Pattern reference; not a competitor. |
| farmOS | GPL-2.0 | Farm records. Copyleft: never copy into A.C.R.E. |
| streamlit, vega/altair, requests, pytest | Apache / BSD / MIT | Python route; not used by our React frontend. |
| pynasapower (GPL-3.0), ropensci/nasapower, earthaccess (MIT), soilDB (GPL-3.0), USDA crop-sequence-boundaries | various | Data access, Rahul's side. |
| AquaCrop-OSPy, APSIM, DSSAT | Apache / custom / BSD | Crop models; out of scope (no yield claims). |

## What the field looks like, and where A.C.R.E stands apart

- **Same look everywhere.** Three of the strongest entries use cream paper, evergreen and a serif headline. A.C.R.E's palette sits in that group, so palette alone will not set it apart.
- **Map-first.** Almost every entry opens on a map. A.C.R.E opens on the answer and the farm itself.
- **Charts are generic.** Recharts line and bar dashboards with KPI tiles.
- **No one shows the plan through the season in 3D.** BoponX has a 3D globe; nobody has the three fields side by side under the same rain. That is A.C.R.E's visual signature.

## Patterns to adopt (our own code, our own design)

1. **Quick answer on one screen** (Zul-Qarnain): keep the three plans and their numbers above the fold, which A.C.R.E already does; add a one-line plain verdict per plan.
2. **"See why" next to every number** (Zul-Qarnain, AgriShift): a small "how this was worked out" link on each card number opening the evidence at that row.
3. **Export the result as JSON** (AgriShift): one button in the evidence drawer, for judges who want to verify.
4. **Numbered wayfinding** (AgriShift, tejaswi): section eyebrows like "01 · Your farm", "02 · 45 springs", "03 · Three plans", "04 · Bring it to Extension".
5. **Point used, named plainly** (Zul-Qarnain): the place picker says which NASA grid cell it used and where its center is.
6. **Data-source strip** (tejaswi, TerraCrop): one footer band listing NASA POWER, NC State Extension and the farmer's dates, each a link.
7. **Guided path and browse path** (covercrop-selector.org): a "Walk me through it" button for first-time viewers, next to the full planner (feeds Phase 11 demo mode).
8. **Small NC map in the place picker** (most entries): an outline with the eight county points; clicking a point selects it. Uses public-domain US Census shapes, not another team's map.

## Patterns to avoid

- Marketing heroes before the tool (Aboho, TerraCrop): judges want the result in the first second.
- Dark neon dashboards and AI chat helpers: off-tone for an Extension conversation and hard to source.
- "AI", "smart" and accuracy claims in headings.
