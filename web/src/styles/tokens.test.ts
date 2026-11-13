import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// WCAG 2.2 AA: 4.5:1 for normal text, 3:1 for large text and UI component edges
// (playbook p.37, handbook p.16). Checks every pair the components actually use.

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "tokens.css"), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`missing block ${selector}`);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  const body = css.slice(open + 1, close);
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;/g)) {
    out[m[1]!] = m[2]!;
  }
  return out;
}

function luminance(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = c.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT_PAIRS: Array<[string, string]> = [
  ["ink", "bg"],
  ["ink", "surface"],
  ["ink", "surface-2"],
  ["ink-muted", "bg"],
  ["ink-muted", "surface"],
  ["ink-muted", "surface-2"],
  ["action-ink", "action"],
  ["action", "surface"],
  ["action", "bg"],
  ["rain", "surface"],
  ["rain", "rain-soft"],
  ["rain-strong", "rain-soft"],
  ["cover", "surface"],
  ["cover", "cover-soft"],
  ["fallow", "surface"],
  ["fallow", "fallow-soft"],
  ["corn", "surface"],
  ["wheat", "surface"],
  ["soy", "surface"],
  ["check", "check-soft"],
  ["check", "surface"],
  ["ink", "check-soft"],
  ["error", "surface"],
  ["error", "error-soft"],
];

const UI_PAIRS: Array<[string, string]> = [
  ["line-strong", "surface"],
  ["line-strong", "bg"],
  ["focus", "surface"],
  ["focus", "bg"],
];

const light = block(":root {");
const dark = { ...light, ...block(':root[data-theme="dark"]') };

describe.each([
  ["light", light],
  ["dark", dark],
])("%s theme contrast", (_name, t) => {
  it.each(TEXT_PAIRS)("text %s on %s is at least 4.5:1", (fg, bg) => {
    expect(t[fg], `missing token ${fg}`).toBeDefined();
    expect(t[bg], `missing token ${bg}`).toBeDefined();
    expect(contrast(t[fg]!, t[bg]!)).toBeGreaterThanOrEqual(4.5);
  });
  it.each(UI_PAIRS)("UI edge %s on %s is at least 3:1", (fg, bg) => {
    expect(contrast(t[fg]!, t[bg]!)).toBeGreaterThanOrEqual(3);
  });
});

it("dark media block matches the explicit dark block", () => {
  const start = css.indexOf("@media (prefers-color-scheme: dark)");
  const media = css.slice(start, css.indexOf(':root[data-theme="dark"]'));
  const mediaTokens: Record<string, string> = {};
  for (const m of media.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;/g)) mediaTokens[m[1]!] = m[2]!;
  expect(mediaTokens).toEqual(block(':root[data-theme="dark"]'));
});
