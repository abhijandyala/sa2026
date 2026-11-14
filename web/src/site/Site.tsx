import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { APP_FULL_NAME, APP_NAME, CHALLENGE_LABEL } from "../config";
import { buildView } from "../view/build";
import { Roll } from "../ui/Roll";
import type { SiteData } from "./useSiteData";

/*
  Shared pieces of the marketing site (Nov 13). Its structure and motion follow the
  tabs.com pages Abhi recorded: announcement bar, slim nav with menus, two-line headings
  with a grey second line, hairline grids, a dark closing band and a dark footer.
  The words, numbers and pictures are A.C.R.E's own; nothing of theirs is reused.
*/

export type SiteView = "home" | "product" | "growers" | "evidence" | "resources" | "about";
export const to = (view: SiteView) => (view === "home" ? "./" : `?view=${view}`);
/** A planner page, opened directly. */
export const app = (hash = "") => `?view=app${hash ? `#${hash}` : ""}`;

export const APP_PAGES: Array<{ pg: string; name: string; line: string }> = [
  { pg: "pg=overview", name: "Overview", line: "The three plans and your field in 3D" },
  { pg: "pg=springs", name: "Past springs", line: "Replay any spring since 1981" },
  { pg: "pg=compare", name: "Compare plans", line: "Both winters, side by side" },
  { pg: "s=cover&pg=plan", name: "Plan detail", line: "One plan, looked at closely" },
  { pg: "s=cover&pg=rye", name: "Rye timing", line: "Move the day the rye ends" },
  { pg: "pg=calendar", name: "Calendar", line: "Every field job on its day" },
];

export const Arrow = ({ size = 12 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 12 12" aria-hidden="true">
    <path d="M3 9l6-6M4.500 3H9v4.500" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const CHEVRON = (
  <svg width="12" height="12" viewBox="0 0 12 12">
    <path d="M4.500 2.500L8 6l-3.500 3.500" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
/** Two chevrons in one slot: on hover the first slides out to the right as the second slides in from the left. */
export const Chevron = () => (
  <span className="st-chev" aria-hidden="true">
    {CHEVRON}
    {CHEVRON}
  </span>
);

/** The small "watch it work" card: a thumbnail with a play ring, a title and one grey line. */
export function Watch({ href, dark = false }: { href: string; dark?: boolean }) {
  return (
    <a className={`st-watch${dark ? " is-dark" : ""}`} href={href}>
      <span className="st-watch-thumb" aria-hidden="true">
        <span className="st-watch-play">
          <svg width="12" height="13" viewBox="0 0 12 13">
            <path d="M2.500 1.500v10l8.500-5z" fill="currentColor" />
          </svg>
        </span>
      </span>
      <span>
        <strong>Compare. Replay. Decide what to ask.</strong>
        <span>Watch the planner at work</span>
      </span>
    </a>
  );
}

/** True once the element has scrolled into view (and, with `once: false`, while it stays there). */
export function useInView<T extends HTMLElement>(once = true, margin = "0px 0px -12% 0px") {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e?.isIntersecting) {
          setSeen(true);
          if (once) io.disconnect();
        } else if (!once) setSeen(false);
      },
      { rootMargin: margin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [once, margin]);
  return [ref, seen] as const;
}

/** Fades and lifts its content into place the first time it is scrolled to. */
export function Reveal({ children, delay = 0, as: Tag = "div", className = "" }: { children: ReactNode; delay?: number; as?: "div" | "section" | "li"; className?: string }) {
  const [ref, seen] = useInView<HTMLElement>();
  return (
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    <Tag ref={ref as any} className={`st-reveal${seen ? " is-in" : ""} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </Tag>
  );
}

/** Mounts its heavy content only near the viewport, so a page of recordings stays light. */
export function Lazy({ children, ratio }: { children: ReactNode; ratio: string }) {
  const [ref, near] = useInView<HTMLDivElement>(false, "300px 0px 300px 0px");
  return (
    <div ref={ref} className="st-lazy" style={{ aspectRatio: near ? undefined : ratio }}>
      {near ? children : null}
    </div>
  );
}

/** The few numbers the pages quote, read from the saved record so the words can never drift from the app. */
export function useNumbers(data: SiteData | null | undefined) {
  return useMemo(() => {
    if (!data) return null;
    const view = buildView(data, { card: "cover", year: null, leg: 1 });
    const now = view.cards.find((c) => c.key === "current")?.legs[0];
    const cover = view.cards.find((c) => c.key === "cover")?.legs[0];
    const years = data.years.years;
    return {
      view,
      springs: cover?.springs.length ?? years.length,
      firstYear: years[0]?.year ?? null,
      lastYear: years[years.length - 1]?.year ?? null,
      bareNow: now?.soilMm ?? null,
      bareCover: cover?.soilMm ?? null,
      /** Winters the backend could evaluate for the rye plan (its own count). */
      winters: view.cards.find((c) => c.key === "cover")?.soil.seasons ?? null,
      checks: cover?.check.count ?? null,
      of: cover?.check.denominator ?? null,
      gap: cover?.gapDays ?? null,
      living: cover?.livingDays ?? null,
    };
  }, [data]);
}
export type Numbers = NonNullable<ReturnType<typeof useNumbers>>;
export const whole = (v: number | null | undefined) => (v === null || v === undefined ? "–" : v.toFixed(0));

/**
  A stat that swaps every few seconds, the way the reference page's tile does: the tiles are
  stacked, the next one wipes in over the last and its digits roll up from zero. A click skips ahead.
*/
export function StatTile({ stats }: { stats: Array<{ value: string; unit?: string; label: string; tone: "plain" | "teal" | "cyan" }> }) {
  const [i, setI] = useState(0);
  const [ref, seen] = useInView<HTMLDivElement>(false);
  const count = stats.length;
  useEffect(() => {
    if (!seen || count < 2) return;
    const id = window.setTimeout(() => setI((n) => (n + 1) % count), 4200);
    return () => window.clearTimeout(id);
  }, [seen, count, i]);
  return (
    <div ref={ref} className="st-stats">
      {stats.map((s, k) => {
        const on = k === i;
        const before = k === (i - 1 + count) % count;
        return (
          <button
            type="button"
            key={s.label}
            className={`st-stat is-${s.tone}${on ? " is-on" : before ? " is-before" : ""}`}
            onClick={() => setI((n) => (n + 1) % count)}
            tabIndex={on ? 0 : -1}
            aria-hidden={!on}
            aria-label={`${s.value}${s.unit ?? ""} ${s.label}. Show the next number.`}
          >
            <span className="st-stat-label">{s.label}</span>
            <span className="st-stat-value">
              <Roll value={on && seen ? s.value : s.value.replace(/\d/g, "0")} />
              {s.unit ? <span className="st-stat-unit">{s.unit}</span> : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** A top-nav item that goes to its own page when clicked and shows its menu on hover or keyboard focus. */
function Menu({ label, href, children, current }: { label: string; href: string; children: ReactNode; current?: boolean }) {
  return (
    <div className="st-menu">
      <a className="st-nav-link" href={href} aria-haspopup="true" aria-current={current ? "page" : undefined}>
        {label}
      </a>
      <div className="st-menu-panel">{children}</div>
    </div>
  );
}

export function SiteNav({ current }: { current: SiteView }) {
  const [stuck, setStuck] = useState(false);
  const [away, setAway] = useState(false);
  // The bar and the nav travel together: they slide away on the way down and come back on the way up.
  useEffect(() => {
    let last = window.scrollY;
    const on = () => {
      const y = window.scrollY;
      setStuck(y > 8);
      if (Math.abs(y - last) < 6) return;
      setAway(y > last && y > 260);
      last = y;
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  const link = (view: SiteView, label: string) => (
    <a className="st-nav-link" href={to(view)} aria-current={current === view ? "page" : undefined}>
      {label}
    </a>
  );
  return (
    <div className={`st-head${away ? " is-away" : ""}`}>
      <a className="st-announce" href={to("evidence")}>
        <span className="st-announce-dot" aria-hidden="true" />
        Now running on NASA POWER records for eight North Carolina counties
        <Chevron />
      </a>
      <header className={`st-nav${stuck ? " is-stuck" : ""}`}>
        <a className="st-brand" href="./" aria-label={`${APP_NAME} home`}>
          <span className="fb-mark" aria-hidden="true" />
          {APP_NAME}
        </a>
        <nav className="st-nav-links" aria-label="Site">
          <Menu label="Product" href={to("product")} current={current === "product"}>
            <div className="st-menu-cols">
              <ul>
                {APP_PAGES.map((p) => (
                  <li key={p.name}>
                    <a href={app(p.pg)}>
                      <strong>{p.name}</strong>
                      <span>{p.line}</span>
                    </a>
                  </li>
                ))}
              </ul>
              <a className="st-menu-card" href={to("product")}>
                <span className="st-menu-card-tag">Tour</span>
                <strong>See every page of the planner in one place</strong>
                <span className="st-link">
                  Product overview <Chevron />
                </span>
              </a>
            </div>
          </Menu>
          {link("growers", "Who it's for")}
          {link("evidence", "Evidence")}
          <Menu label="Resources" href={to("resources")} current={current === "resources"}>
            <div className="st-menu-cols is-narrow">
              <ul>
                <li>
                  <a href={to("resources")}>
                    <strong>Resource center</strong>
                    <span>Guides, sources and limits</span>
                  </a>
                </li>
                <li>
                  <a href="?view=methods">
                    <strong>How it works</strong>
                    <span>The method, step by step</span>
                  </a>
                </li>
                <li>
                  <a href="?view=credits">
                    <strong>Data and credits</strong>
                    <span>Every source and license</span>
                  </a>
                </li>
                <li>
                  <a href="?view=privacy">
                    <strong>Privacy and terms</strong>
                    <span>What stays on your device</span>
                  </a>
                </li>
              </ul>
            </div>
          </Menu>
          {link("about", "About")}
        </nav>
        <div className="st-nav-actions">
          <a className="st-nav-link" href={app("v=summary")}>
            Sample summary
          </a>
          <a className="btn btn-primary btn-small" href={app()}>
            Open the planner
          </a>
        </div>
      </header>
    </div>
  );
}

export function SiteFooter() {
  return (
    <footer className="st-foot">
      <div className="st-wrap st-foot-grid">
        <div className="st-foot-lead">
          <p>
            <span className="fb-mark st-foot-mark" aria-hidden="true" /> {APP_NAME}
          </p>
          <p className="st-foot-note">{APP_FULL_NAME}. A replay of past weather for planning talks. Not a forecast, and not a field measurement.</p>
        </div>
        <div>
          <h3>Product</h3>
          <ul>
            {APP_PAGES.map((p) => (
              <li key={p.name}>
                <a href={app(p.pg)}>{p.name}</a>
              </li>
            ))}
            <li>
              <a href={app("v=summary")}>Extension summary</a>
            </li>
          </ul>
        </div>
        <div>
          <h3>Site</h3>
          <ul>
            <li>
              <a href={to("product")}>Product</a>
            </li>
            <li>
              <a href={to("growers")}>Who it's for</a>
            </li>
            <li>
              <a href={to("evidence")}>Evidence</a>
            </li>
            <li>
              <a href={to("about")}>About</a>
            </li>
          </ul>
        </div>
        <div>
          <h3>Resources</h3>
          <ul>
            <li>
              <a href={to("resources")}>Resource center</a>
            </li>
            <li>
              <a href="?view=methods">How it works</a>
            </li>
            <li>
              <a href="?view=credits">Data and credits</a>
            </li>
            <li>
              <a href="?view=privacy">Privacy and terms</a>
            </li>
          </ul>
        </div>
      </div>
      <div className="st-wrap st-foot-base">
        <span>{CHALLENGE_LABEL} · Charlotte</span>
        <span>Past weather from NASA POWER. Guidance from NC State Extension.</span>
      </div>
    </footer>
  );
}

/** The dark closing band above the footer, the same on every page. */
export function SiteClose({ springs }: { springs: number | null }) {
  return (
    <section className="st-close">
      <div className="st-wrap">
        <Reveal>
          <h2>
            See your winter plan
            <br />
            against {springs ? `${springs} real springs` : "every real spring"}.
          </h2>
          <a className="btn btn-primary" href={app()}>
            Open the planner
          </a>
        </Reveal>
      </div>
      <div className="st-dotband">
        <div className="st-dots" aria-hidden="true" />
        <div className="st-wrap st-close-watch">
          <Watch href="./#watch" dark />
        </div>
      </div>
    </section>
  );
}

export function SiteShell({ current, title, children, springs }: { current: SiteView; title: string; children: ReactNode; springs: number | null }) {
  useEffect(() => {
    const before = document.title;
    document.title = title;
    window.scrollTo(0, 0);
    return () => {
      document.title = before;
    };
  }, [title]);
  return (
    <div className="st">
      <SiteNav current={current} />
      <main>{children}</main>
      <SiteClose springs={springs} />
      <SiteFooter />
    </div>
  );
}
