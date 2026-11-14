# A.C.R.E theme kit (Nov 13, 2026)

The look is modeled on tabs.com, studied from Abhi's screen recording (frame by frame at 2 fps) and measured on the live site. We took its design language, not its assets: no logo, photos, illustrations or code. Its typeface (Beausite Classic) is commercial, so Hanken Grotesk (OFL) stands in.

## Where it lives

| File | What it holds |
| --- | --- |
| `src/styles/tokens.css` | Colors, type sizes, spacing, radius, motion. Light only. Contrast-tested in `tokens.test.ts`. |
| `src/styles/fieldback.css` | Kit components (buttons, segmented control, pills, accordion, rolling numbers) and the page layout. Loaded last. |
| `src/ui/Roll.tsx` | Rolling number: digits roll to the new value. |
| `src/ui/Accordion.tsx` | One-open list with the accent line across the open item. |
| `src/styles/layout.css`, `components.css` | Older rules still used by the drawers, rye timing, day-by-day chart, summary and reading pages. They pick up the new tokens; prune as those parts are redesigned. |

## Rules

1. **One typeface.** Hanken Grotesk for everything. No monospace, no uppercase "terminal" labels. Hierarchy comes from size, weight (350 headings, 400 text, 500 labels) and grey.
2. **Headings in two lines:** the statement in ink, the second line in grey (`.fb-dim`). Tight tracking (-0.025 to -0.035em).
3. **Color:** white pages, `--surface-2` grey panels, hairline `--line` rules. One accent: cyan `--accent` as a fill with dark text; deep teal `--action` for text, links, focus and selected data. Amber `--check` only for a check the grower can act on. Green only for living cover. Never cyan text.
4. **Shape:** 6 px controls, 8 px panels, no card shadows (only the segmented control's selected chip has one).
5. **A dashboard, not a landing page:** edge to edge. Dark sidebar (`.db-side`), slim top bar (`.db-top`), a row of number tiles (`.db-tiles`), then white cards (`.db-card`) on the grey canvas in a 12-column grid (`.db-grid`). Card titles are 16 px / 500 with one grey line under them; no big marketing headlines. One idea per card; details open on request (accordion, drawer).
6. **No redundant text.** Never build a card as title + subtitle + info + pill. A clear title gets no line under it. No pill or line that only says something does not apply. One number, one short caption, and a pill only when there is something to act on. Honesty labels (illustration, not a forecast, regional estimate, draft data) appear once and short.
7. **Numbers are answers:** one big number with a plain sentence beside it ("437 mm of winter rain falls with nothing growing"). Every number is a "see why" link.
8. **Motion:** 300 ms for state, 600 ms for lines and digits, one curve `cubic-bezier(0.4, 0, 0.2, 1)`. Lines fill, digits roll, panels rise 6 px. Nothing loops except the 3D camera's slow drift. `prefers-reduced-motion` turns it all off.
9. **3D:** fields float on the dotted stage with a soft shadow, seen from a three-quarter angle. The selected field lifts and gets a cyan frame; plants ease to their stage; the season plays to mid-winter once on load.

## Measured from tabs.com

Ink `oklch(0.22 0.006 237)` (about #15191C), muted text at 60% ink, cyan `oklch(0.83 0.14 207)` (about #2ADCEB), deep teal `rgb(0, 70, 86)`, panel grey `rgb(248, 248, 248)`, radius 6 px, buttons 15 px / 500 with `0.4s cubic-bezier(0.4, 0, 0.2, 1)`, h1 72 px / 400 / -0.04em, h2 48 px / 350 / -0.02em, h3 20 px / 500.
