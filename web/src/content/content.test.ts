import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { DATA_CREDITS, LIBRARIES } from "./credits";
import { GLOSSARY } from "./glossary";
import { CARDS, SOURCES } from "./strategies";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const pkg = (name: string) => JSON.parse(readFileSync(join(root, "node_modules", name, "package.json"), "utf8")) as { version: string; license: string };

// The Credits page must match what is actually installed (card 6.5).
const INSTALLED: Record<string, string[]> = {
  "React and React DOM": ["react", "react-dom"],
  "three.js": ["three"],
  "React Three Fiber": ["@react-three/fiber"],
  Zod: ["zod"],
  "Hanken Grotesk (Fontsource)": ["@fontsource-variable/hanken-grotesk"],
  "Vite and @vitejs/plugin-react": ["vite", "@vitejs/plugin-react"],
  TypeScript: ["typescript"],
  "Vitest and Testing Library": ["vitest", "@testing-library/react"],
  Playwright: ["@playwright/test"],
};

describe("credits", () => {
  it.each(LIBRARIES.map((l) => [l.name, l] as const))("%s lists the installed version and license", (_n, lib) => {
    const names = INSTALLED[lib.name];
    expect(names, `no package mapping for ${lib.name}`).toBeDefined();
    const versions = names!.map((n) => pkg(n).version);
    expect(lib.version.split(" / ")).toEqual([...new Set(versions)].length === 1 && names!.length > 1 && !lib.version.includes("/") ? [versions[0]] : versions);
    for (const n of names!) expect(pkg(n).license).toBe(lib.license);
  });

  it("credits every source the cards cite", () => {
    const cited = new Set(CARDS.flatMap((c) => Object.values(c.headings).flat().map((x) => x.source).filter(Boolean)));
    const creditedUrls = DATA_CREDITS.map((d) => d.url);
    for (const id of cited) {
      const url = SOURCES[id!].url;
      expect(creditedUrls.some((u) => url.startsWith(u) || u.startsWith(url)), `${id} is not in the credits`).toBe(true);
    }
  });
});

describe("glossary", () => {
  it("every definition is a full sentence", () => {
    for (const g of Object.values(GLOSSARY)) expect(g.definition).toMatch(/\.$/);
  });
});
