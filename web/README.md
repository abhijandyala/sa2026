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

The planner reads `public/data/bundle.json`, written by the backend pipeline. Until that file exists it loads `public/data/fixture-synthetic.json` and shows a "Synthetic test data" banner on every screen. Regenerate the fixture with `npm run fixture`.

The agreed shape is `src/data/schema.ts`. The frontend never recomputes a total, rank, flag or count; it only formats them.

## Layout of the code

- `src/data`: schema, loader, display formatting
- `src/state`: what the user selected, shareable links, data loading
- `src/ui`: shared components (mirrored in the Fieldback Design System)
- `src/screens`: Planner and Gallery
- `src/styles`: tokens (checked for WCAG AA contrast by `tokens.test.ts`), base, components, layout
