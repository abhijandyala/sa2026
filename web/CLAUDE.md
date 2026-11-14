# Fieldback frontend: working rules

These rules cover everything in `web/`. The root `CLAUDE.md` covers the backend and does not apply here. Abhi owns the frontend; Rahul owns the backend, the data and every calculation.

## What the app is

Fieldback (NASA Space Apps 2026, Field Shift, Charlotte) compares three two-winter rotations for a Union County, NC corn and soybean farm against every past spring recorded by NASA (1981–2025), and shows where NC State guidance applies. Presets and plan IDs are defined by the backend in `docs/api/presets.md` on the `backend` branch.

## Hard rules

- **No calculation in the frontend.** Totals, ranks, percentiles, dry labels, check counts, qualifying years, eras and thresholds come from the backend. The UI selects and formats them. The only arithmetic allowed is a display difference between two backend values (the slider's "+7 days").
- **Never add the two winters together.** Each leg is its own plan with its own denominators; show them side by side.
- **Missing is not zero.** A valid 0.0 mm stays 0.0; a missing value says "Not available" or "Not evaluated yet", never 0.
- **No hardcoded thresholds.** Heavy-rain and dry cutoffs come from `thresholds` in the response.
- **Every agronomic sentence has a source** in `src/content/strategies.ts` (NC State page checked against the source) or is listed as a gap.
- **No invented proof on the site:** no customer logos, testimonials, prices or stats that are not read from the saved record. Numbers on the marketing pages come from `useNumbers()`.
- **No outcome claims:** no "saved water", "optimized yield", "safe to plant", "best rotation", forecasts or profit.
- **Unknown is a real answer** in forms; never treat a blank as No.
- **Unless a test says otherwise, the backend's field names win.** If the API needs to change, write it in `docs/api-requests.md` and tell Rahul; do not patch around it in the UI.

## Layout and quality bars

- **Theme kit:** read `docs/theme-kit.md` before any UI work. Light only, one typeface (Hanken Grotesk), cyan accent with teal text, grey second heading lines, 6 to 8 px corners, no monospace or uppercase "terminal" labels, no colored stripes, gradients, emoji or decorative icons.
- **Dashboard shell, edge to edge:** dark sidebar that switches pages, top bar (place, winter switch where it applies, Edit farm dates), white cards on a grey canvas. It must read as a dashboard, never a landing page.
- **One question per page** (`state.page`, link param `pg`): Overview (three plan tiles + the 3D field), Past springs (bar chart + day by day), Compare plans (a rain glass and a side-view field picture per plan and winter, `planner/WinterPicture.tsx`; hover names each part, a click opens the large view `planner/WinterZoom.tsx`), Plan detail (both winters as field pictures, then three small cards: before you plant, about this plan, earlier and recent springs), Rye timing (one field picture with the rye end date as a stake you drag, three result tiles), Calendar (a full-width field strip per plan with each job as a dated chip under its month, `planner/FieldCalendar.tsx`). The Extension summary opens from the sidebar.
- **No redundant text:** no subtitle under a clear title, no pill that only says something does not apply, one short caption per number. If the title, number or visual already says it, leave the words out.
- **Show it, do not write it:** a blue bar is winter rain, one dot is one past spring, amber is a moisture check, a ring is a dry spring (`planner/WinterStat.tsx`). Each card gets a title, one visual, one short sentence and one action. Proof (sources, definitions, daily values) stays in the evidence drawer and the summary.
- **One idea per section, less text.** A farmer should know where to look: one number with a plain sentence, details on request.
- At 1280×720 the three plan tiles and the top of the field and springs cards must be above the fold (measure it in the browser).
- WCAG AA contrast is tested in `src/styles/tokens.test.ts`; keyboard must work. Focus rings show for the keyboard only, never on a click (`ui/inputMode.ts`). Desktop and projector only: the app is not used on phones.
- The 3D view is an illustration of planned dates: label it so, and keep everything it shows available in text.

## Code map

- `src/api`: `adapt.ts` is the only file that knows the backend's field names; it turns Rahul's real responses into the model in `schema.ts` that the screens read. `client.ts` loads the saved NASA record in `public/data/nasa/` (his responses exactly as returned) or the live API via `VITE_API_BASE`, both through the adapter.
- `src/view/build.ts`: the only place that turns responses into what screens show.
- `src/content`: card names, sourced headings, glossary, credits.
- `src/state`: selection (card, year, winter, rye date, priorities), form, links.
- `src/site`: the marketing site in front of the planner. `Landing.tsx` and `pages.tsx` (Product, Who it's for, Evidence, Resources, About) follow the tabs.com page templates with Fieldback's own words and numbers; `demo/` holds the Loom-style recordings, which drive the real planner screens with a scripted pointer (the hero's `TourScene` shows the whole dashboard, using the planner's own sidebar from `planner/SideNav.tsx`); the reading pages in `screens/Pages.tsx` (how it works, credits, privacy) sit inside the same site shell, one topic per row with its heading on the left; styles in `styles/site.css` (`st-` and `demo-` classes). Type sizes come from the `--t-*` steps on `.st`, which match the reference page's scale (hero 72, headings 48 and 36, card titles 28, body 16); use those instead of new font sizes. Routes: `./` is the landing page, `?view=app` is the planner, and a link with planner state in its hash still opens the planner.
- `src/screens`, `src/ui` (kit pieces: `Roll`, `Accordion`, `components`), `src/scene` (3D), `src/styles` (`tokens.css`, `fieldback.css` = the kit).
- `scripts/fetch-backend.mjs`: saves the real responses from a running backend into `public/data/nasa/` (`npm run data`).
- `scripts/make-sample.mjs` and `public/data/sample/`: the old synthetic draft, kept only as a fixture for the view-builder tests.

## Commands

```bash
npm run dev          # http://localhost:5173 (the backend's CORS allows this port)
npm test             # unit tests
npm run typecheck
npm run build
npm run data         # save real responses; needs the backend running (FIELDSHIFT_OFFLINE=1 uvicorn fieldshift.api.app:app)
```

## Git

Frontend work goes on `frontend/*` branches and merges into `main`. Never push to or rewrite `backend` or `backend/*`. Commit only when asked.
