# Fieldback web

The frontend for Fieldback (NASA Space Apps 2026, Field Shift, Charlotte): compare three winter crop plans for a North Carolina corn and soybean farm against past springs recorded by NASA.

## Run it

```bash
cd web
npm install
npm run dev        # http://localhost:5173
```

Component gallery with every state: `http://localhost:5173/?view=gallery`.

## Check it

```bash
npm test           # unit tests: formatting, loader, data contract, state model, color contrast
npm run typecheck
npm run build      # static site in web/dist, works offline from `npx vite preview`
npm run test:e2e   # browser check of the judge path (first run: npx playwright install chromium)
```

## Data

The planner always loads the saved Union County sample from `public/data/sample/` (`years.json`, `compare.json`, `sensitivity.json`), shaped exactly like the backend API. Today it is synthetic draft data (`npm run sample` regenerates it) and the UI shows a "Draft sample data" banner; the backend's generated output replaces these files later. Date edits call the live API when `VITE_API_BASE` is set at build time; if it is missing or slow, the saved sample stays on screen with a notice. What the frontend still needs from the API is in `docs/api-requests.md`.

The API types are in `src/api/schema.ts`, matching the backend's draft examples. The frontend never recomputes a total, rank, flag or count; it only formats them.

## Layout of the code

- `src/api`: API types and client (saved sample + live service, bounded waits, newest answer wins)
- `src/view`: turns API responses into what each screen shows; selection only, no calculation
- `src/content`: card names and the sourced five headings for each plan
- `src/data`: display formatting
- `src/state`: what the user selected, the farm form, shareable links, data loading
- `src/ui`: shared components (mirrored in the Fieldback Design System)
- `src/screens`: Planner and Gallery
- `src/styles`: tokens (checked for WCAG AA contrast by `tokens.test.ts`), base, components, layout
