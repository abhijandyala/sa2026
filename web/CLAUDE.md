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
- **No outcome claims:** no "saved water", "optimized yield", "safe to plant", "best rotation", forecasts or profit.
- **Unknown is a real answer** in forms; never treat a blank as No.
- **Unless a test says otherwise, the backend's field names win.** If the API needs to change, write it in `docs/api-requests.md` and tell Rahul; do not patch around it in the UI.

## Layout and quality bars

- Layout: header (title row, then winter switch and actions), a hero with the 3D farm (three fields side by side) on the left and the 45-spring almanac on the right, then three cards, then detail. At 1280×720 every card's numbers must end above the fold, even with the draft banner (measure it in the browser; 705 px on Nov 13).
- WCAG AA contrast is tested in `src/styles/tokens.test.ts`; keyboard, light and dark must all work. Desktop and projector only: the app is not used on phones, so do not spend time on phone layouts.
- The 3D view is an illustration of planned dates: label it so, and keep everything it shows available in 2D.

## Code map

- `src/api`: API types (zod) and client: saved sample in `public/data/sample/`, live API via `VITE_API_BASE`.
- `src/view/build.ts`: the only place that turns responses into what screens show.
- `src/content`: card names, sourced headings, glossary, credits.
- `src/state`: selection (card, year, winter, rye date, priorities), form, links.
- `src/screens`, `src/ui`, `src/scene` (3D), `src/styles`.
- `scripts/make-sample.mjs`: synthetic draft sample in the API shape. Regenerate with `npm run sample`.

## Commands

```bash
npm run dev          # http://localhost:5173 (the backend's CORS allows this port)
npm test             # unit tests
npm run typecheck
npm run build
npm run test:e2e     # browser tests; first run needs: npx playwright install chromium
```

## Git

Frontend work goes on `frontend/*` branches and merges into `main`. Never push to or rewrite `backend` or `backend/*`. Commit only when asked.
