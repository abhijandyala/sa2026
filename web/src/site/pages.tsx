import type { ReactNode } from "react";
import { APP_NAME, CHALLENGE_LABEL } from "../config";
import { mm } from "../data/format";
import { WinterPicture } from "../screens/planner/WinterPicture";
import { CalendarScene, CompareScene, RyeScene, SpringsScene } from "./demo/scenes";
import { app, APP_PAGES, Arrow, Chevron, Lazy, Reveal, SiteShell, to, useNumbers, whole, type Numbers } from "./Site";
import { useSiteData } from "./useSiteData";
import { BareRainCard, GapCard, SpringDotsCard, SummarySheet } from "./visuals";

/*
  The pages behind the top navigation. Each follows the matching tabs.com template:
  Product (centred hero, recording, alternating rows, feature grid), Who it's for
  (split hero with facts, then one band per audience), Evidence (centred hero, cards,
  a grid of findings), Resources (dark hero, a lead card and a list) and About
  (centred hero, four cards, an "included" table).
*/

const Pill = ({ children }: { children: ReactNode }) => (
  <p className="st-pill">
    <span className="fb-mark" aria-hidden="true" />
    {children}
  </p>
);

function Row({ title, text, stat, visual, flip }: { title: string; text: string; stat: ReactNode; visual: ReactNode; flip?: boolean }) {
  return (
    <Reveal className={`st-row${flip ? " is-flip" : ""}`}>
      <div className="st-row-text">
        <span className="st-row-icon" aria-hidden="true" />
        <h3>{title}</h3>
        <p>{text}</p>
        <p className="st-row-stat">{stat}</p>
      </div>
      <div className="st-row-art">{visual}</div>
    </Reveal>
  );
}

const Check = ({ children }: { children: ReactNode }) => (
  <li>
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
      <path d="M2.500 6.300l2.300 2.300 4.700-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
    {children}
  </li>
);

/* ------------------------------------------------------------------ Product */
export function ProductPage() {
  const data = useSiteData();
  const n = useNumbers(data);
  return (
    <SiteShell current="product" title={`Product · ${APP_NAME}`} springs={n?.springs ?? null}>
      <section className="st-wrap st-phero">
        <Pill>The planner</Pill>
        <h1>
          Winter plans you can
          <br />
          see before you plant
        </h1>
        <p>
          Six pages, one question each. Every picture is drawn from your dates and {n?.springs ?? 45} springs of NASA records.
        </p>
        <a className="btn st-btn-ink" href={app()}>
          Open the planner
        </a>
        <div className="st-phero-demo">{data ? <RyeScene data={data} /> : <div className="st-skeleton" style={{ aspectRatio: "1180 / 780" }} />}</div>
      </section>

      <div className="st-marquee" aria-hidden="true">
        <div>
          {[0, 1].map((k) => (
            <span key={k}>
              {["NASA POWER", "MERRA-2", "NC State Extension", "NCDA&CS", "NC Climate Office", "USDA NRCS", "Union County, NC", "NASA Space Apps"].map((s) => (
                <b key={s}>{s}</b>
              ))}
            </span>
          ))}
        </div>
      </div>

      <section className="st-wrap st-section">
        <Reveal className="st-center">
          <span className="st-row-icon is-big" aria-hidden="true" />
          <p className="st-small">Why {APP_NAME}?</p>
          <h2 className="st-h2 is-plain">
            From one winter's guess to {n?.springs ?? 45} springs
            <br />
            of evidence, in pictures.
          </h2>
        </Reveal>
        {n ? (
          <div className="st-rows">
            <Row
              title="See what bare ground costs you in rain"
              text="The glass fills with the winter rain that fell while nothing was growing. Switch plans and it changes."
              stat={
                <>
                  <strong>{whole(n.bareNow)} mm</strong> with no cover, <strong>{whole(n.bareCover)} mm</strong> with rye
                </>
              }
              visual={<BareRainCard n={n} />}
            />
            <Row
              flip
              title="Know how often a plan asks for a field check"
              text="One dot per past spring. Amber marks the dry springs where the rye ended close to planting."
              stat={
                <>
                  <strong>
                    {n.checks} of {n.of}
                  </strong>{" "}
                  springs with rye ended {n.gap} days before planting
                </>
              }
              visual={<SpringDotsCard n={n} />}
            />
            <Row
              title="Find the date that clears the check"
              text="NC State's guidance is two weeks. Move the rye's end date and see when your plan meets it."
              stat={
                <>
                  <strong>{n.living} days</strong> of living rye planned
                </>
              }
              visual={<GapCard n={n} />}
            />
          </div>
        ) : null}
      </section>

      <section className="st-band">
        <div className="st-wrap st-section">
          <Reveal className="st-center">
            <p className="st-small">Pages</p>
            <h2 className="st-h2 is-plain">
              The pages you need, each built
              <br />
              around one picture
            </h2>
          </Reveal>
          <div className="st-bento">
            <Reveal className="st-bcard is-wide">
              <div>
                <p className="st-bcard-tag">Compare plans</p>
                <h3>Three plans, both winters, one scale</h3>
                <p>A rain glass and a side view of the field for every plan and winter. The winters are never added together.</p>
                <ul className="st-checks">
                  <Check>Blue rain marks the weeks with nothing growing</Check>
                  <Check>Point at any part of the picture to name it</Check>
                  <Check>Click a picture to open it large</Check>
                </ul>
              </div>
              <div className="st-bcard-shot">
                <Lazy ratio="1180 / 720">{data ? <CompareScene data={data} chrome={false} play="hover" /> : null}</Lazy>
              </div>
            </Reveal>
            <Reveal className="st-bcard is-wide">
              <div>
                <p className="st-bcard-tag">Past springs</p>
                <h3>Replay the dry year your neighbors still talk about</h3>
                <p>Every spring since {n?.firstYear ?? 1981} is a rain glass. Pick one and the fields show that spring's weather.</p>
                <ul className="st-checks">
                  <Check>Typical, dry and wet springs one click away</Check>
                  <Check>Rank and modeled soil wetness for the picked year</Check>
                  <Check>Your dates never move; only the weather does</Check>
                </ul>
              </div>
              <div className="st-bcard-shot">
                <Lazy ratio="1180 / 700">{data ? <SpringsScene data={data} chrome={false} play="hover" /> : null}</Lazy>
              </div>
            </Reveal>
            <Reveal className="st-bcard">
              <p className="st-bcard-tag">Calendar</p>
              <h3>Every job on its day</h3>
              <p>Harvest, seeding, ending the rye and planting, as dated chips under a field strip for each plan.</p>
              <div className="st-bcard-shot">
                <Lazy ratio="1180 / 690">{data ? <CalendarScene data={data} chrome={false} play="hover" /> : null}</Lazy>
              </div>
            </Reveal>
            <Reveal className="st-bcard" delay={80}>
              <p className="st-bcard-tag">Extension summary</p>
              <h3>A page to bring to your agent</h3>
              <p>The numbers, what to discuss, your questions and room for notes, on two letter pages.</p>
              <div className="st-bcard-shot is-sheet">
                <SummarySheet />
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      <section className="st-wrap st-section">
        <h2 className="st-h2 is-plain">Open any page of the planner</h2>
        <div className="st-explore">
          {APP_PAGES.map((p, i) => (
            <Reveal key={p.name} delay={(i % 3) * 70}>
              <a href={app(p.pg)}>
                <span className="st-bcard-tag">{p.name}</span>
                <strong>{p.line}</strong>
                <span className="st-link">
                  Open {p.name} <Chevron />
                </span>
              </a>
            </Reveal>
          ))}
        </div>
      </section>
    </SiteShell>
  );
}

/* ------------------------------------------------------------------ Who it's for */
export function GrowersPage() {
  const data = useSiteData();
  const n = useNumbers(data);
  const bands: Array<{ tag: string; title: string; text: string; points: string[]; visual: ReactNode; link: [string, string] }> = [
    {
      tag: "Growers",
      title: "Decide what to try next winter with the record in front of you",
      text: "Enter the dates you already plan around. The planner shows what each winter plan would have met in every spring on record.",
      points: ["No account and nothing to install", "Works from a phone hotspot or with no network at all", "Unknown is always an allowed answer"],
      visual: n ? <BareRainCard n={n} /> : null,
      link: ["Open the planner", app()],
    },
    {
      tag: "Extension agents",
      title: "Start the conversation from the same page",
      text: "The printed summary lists the dates, both winters' numbers and the checks to talk over, with room for your notes.",
      points: ["Sources are numbered and printed", "Tick boxes for what was discussed", "The grower's own questions are on the page"],
      visual: <SummarySheet />,
      link: ["See a sample summary", app("v=summary")],
    },
    {
      tag: "Students and judges",
      title: "Check any number back to its source",
      text: "Open a number to see the NASA record, the NC State rule and the limits behind it, or download every value the page received.",
      points: ["Each claim carries its source", "The saved responses ship with the site", "A replay, never a forecast"],
      visual: n ? <SpringDotsCard n={n} /> : null,
      link: ["Read how it works", "?view=methods"],
    },
  ];
  return (
    <SiteShell current="growers" title={`Who it's for · ${APP_NAME}`} springs={n?.springs ?? null}>
      <section className="st-wrap st-shero">
        <div className="st-shero-text">
          <Pill>Who it's for</Pill>
          <h1>
            Less guessing,
            <br />
            more to talk about.
          </h1>
          <p>
            {APP_NAME} helps corn and soybean growers in the North Carolina Piedmont, and the people who advise them, look at a winter plan against real past springs.
          </p>
          <div className="st-hero-cta">
            <a className="btn st-btn-ink" href={app()}>
              Open the planner
            </a>
            <a className="btn btn-secondary" href={to("product")}>
              See the product <Chevron />
            </a>
          </div>
          {n ? (
            <dl className="st-facts">
              <div>
                <dt>{n.springs}</dt>
                <dd>springs replayed</dd>
              </div>
              <div>
                <dt>3</dt>
                <dd>winter plans compared</dd>
              </div>
              <div>
                <dt>2</dt>
                <dd>winters, never added</dd>
              </div>
            </dl>
          ) : null}
        </div>
        <div className="st-shero-art">{data ? <CompareScene data={data} chrome={false} /> : null}</div>
      </section>

      {bands.map((b, i) => (
        <section className={`st-aud${i % 2 ? " is-tint" : ""}`} key={b.tag}>
          <div className="st-wrap st-aud-in">
            <Reveal>
              <p className="st-small">{b.tag}</p>
              <h2 className="st-h2 is-plain">{b.title}</h2>
              <p className="st-sub">{b.text}</p>
              <ul className="st-checks">
                {b.points.map((p) => (
                  <Check key={p}>{p}</Check>
                ))}
              </ul>
              <a className="st-link" href={b.link[1]}>
                {b.link[0]} <i />
              </a>
            </Reveal>
            <Reveal delay={100} className="st-aud-art">
              {b.visual}
            </Reveal>
          </div>
        </section>
      ))}
    </SiteShell>
  );
}

/* ------------------------------------------------------------------ Evidence */
function findings(n: Numbers) {
  const cards = n.view.cards;
  const leg = (key: string, i: number) => cards.find((c) => c.key === key)?.legs[i];
  const w1 = n.view.window;
  return [
    { v: mm(leg("current", 0)?.soilMm ?? null), t: "Winter rain with nothing growing, no cover, winter after corn" },
    { v: mm(leg("cover", 0)?.soilMm ?? null), t: "The same winter with cereal rye" },
    { v: mm(leg("current", 1)?.soilMm ?? null), t: "No cover, winter after soybeans" },
    { v: mm(leg("cover", 1)?.soilMm ?? null), t: "The same winter with cereal rye" },
    { v: `${n.checks} of ${n.of}`, t: "Springs where the rye plan asks for a soil-moisture check" },
    { v: w1?.threshold.value != null ? mm(w1.threshold.value) : "Not available", t: "Dry-spring cutoff for the 30 days before soybean planting" },
    { v: w1?.median_mm != null ? mm(w1.median_mm) : "Not available", t: "Typical rain in those 30 days" },
    { v: `${n.firstYear} to ${n.lastYear}`, t: "Springs in the NASA POWER record used here" },
  ];
}

export function EvidencePage() {
  const data = useSiteData();
  const n = useNumbers(data);
  const stories = n
    ? [
        { key: "current" as const, leg: 0, title: "No planted cover", line: `${whole(n.bareNow)} mm of winter rain met bare ground in the middle winter.`, href: app("s=current&pg=plan") },
        { key: "cover" as const, leg: 0, title: "Cereal rye before soybeans", line: `${whole(n.bareCover)} mm, and a soil check in ${n.checks} of ${n.of} springs.`, href: app("s=cover&pg=plan") },
        { key: "cover" as const, leg: 1, title: "Cereal rye before corn", line: "The winter after soybeans, replayed on its own planting date.", href: app("s=cover&l=2&pg=plan") },
        { key: "current" as const, leg: 1, title: "No cover after soybeans", line: "A shorter winter, and still mostly bare.", href: app("s=current&l=2&pg=plan") },
      ]
    : [];
  return (
    <SiteShell current="evidence" title={`Evidence · ${APP_NAME}`} springs={n?.springs ?? null}>
      <section className="st-wrap st-phero is-tight">
        <h1>What the record says</h1>
        <p>
          Every figure on this page is read from the saved NASA POWER record for Union County, North Carolina, as the planner's own service returned it.
        </p>
      </section>
      <div className="st-rail is-static">
        {stories.map((s) => {
          const plan = n?.view.cards.find((c) => c.key === s.key)?.legs[s.leg]?.plan;
          return (
            <a className="st-q is-tall" key={s.title} href={s.href}>
              <span className="st-q-art" aria-hidden="true">
                {plan?.sequence ? <WinterPicture plan={plan} wide /> : null}
              </span>
              <span className="st-q-page">{s.title}</span>
              <span className="st-q-text">{s.line}</span>
              <span className="st-q-go" aria-hidden="true">
                <Arrow />
              </span>
            </a>
          );
        })}
      </div>
      <section className="st-wrap st-section">
        <h2 className="st-h2 is-plain">All findings</h2>
        <div className="st-find">
          {(n ? findings(n) : []).map((f, i) => (
            <Reveal key={f.t} delay={(i % 4) * 60}>
              <p className="st-find-v tabular">{f.v}</p>
              <p>{f.t}</p>
            </Reveal>
          ))}
        </div>
        <p className="st-sub st-find-note">
          Rainfall is a regional estimate for a grid cell about 55 km wide. The check follows NC State's guidance to end a cover crop two weeks before soybeans when low soil moisture is a concern. These are past springs, not a forecast.
        </p>
      </section>
    </SiteShell>
  );
}

/* ------------------------------------------------------------------ Resources */
export function ResourcesPage() {
  const data = useSiteData();
  const n = useNumbers(data);
  const list: Array<[string, string, string, string]> = [
    ["Guide", "How it works", "The method in plain steps: windows, thresholds, the two periods and the rules.", "?view=methods"],
    ["Sources", "Data and credits", "Every dataset, guide, library and license, with links.", "?view=credits"],
    ["Policy", "Privacy and terms", "What stays in your browser and what is never sent anywhere.", "?view=privacy"],
    ["Sample", "Extension summary", "A printable two-page summary for the Union County sample.", app("v=summary")],
    ["Tour", "Product overview", "Every page of the planner, with a recording of each.", to("product")],
    ["Record", "Evidence", "The figures the planner reads from the NASA record.", to("evidence")],
  ];
  return (
    <SiteShell current="resources" title={`Resources · ${APP_NAME}`} springs={n?.springs ?? null}>
      <section className="st-rhero">
        <div className="st-wrap">
          <p className="st-small">Resources</p>
          <h1>Guides and sources</h1>
          <a className="btn st-btn-ghost" href="?view=methods">
            Start with how it works <Chevron />
          </a>
          <div className="st-rhero-grid">
            <a className="st-rlead" href="?view=methods">
              <span className="st-read-kind">Guide</span>
              <span className="st-rlead-art" aria-hidden="true">
                <span className="fb-mark" />
              </span>
              <strong>How {APP_NAME} replays a winter plan against {n?.springs ?? 45} springs</strong>
              <span className="st-link is-light">
                Read more <i />
              </span>
            </a>
            <a className="st-rside" href="?view=credits">
              <span className="st-rside-art" aria-hidden="true" />
              <span className="st-read-kind">Sources</span>
              <strong>Data and credits: NASA POWER, NC State Extension and the open libraries behind the planner</strong>
            </a>
          </div>
        </div>
      </section>
      <section className="st-wrap st-section">
        <h2 className="st-h2 is-plain">Everything in one list</h2>
        <ul className="st-rlist">
          {list.map(([kind, title, text, href]) => (
            <li key={title}>
              <a href={href}>
                <span className="st-read-kind">{kind}</span>
                <strong>{title}</strong>
                <span>{text}</span>
                <span className="st-fcard-go" aria-hidden="true">
                  <Arrow />
                </span>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </SiteShell>
  );
}

/* ------------------------------------------------------------------ About */
export function AboutPage() {
  const data = useSiteData();
  const n = useNumbers(data);
  const cards: Array<{ name: string; line: string; big: string; small: string; points: string[]; hot?: boolean }> = [
    { name: "Free", line: "For anyone planning a winter.", big: "$0", small: "no plans, no trials", points: ["All six pages", "The printed summary"] },
    { name: "Private", line: "Your dates stay in your browser.", big: "0", small: "accounts to create", points: ["Nothing to sign up for", "Typed coordinates never go in a link"], hot: true },
    { name: "Offline", line: "The NASA record ships with the site.", big: String(n?.springs ?? 45), small: "springs saved on board", points: ["Works with the network off", "Live service only for edited dates"] },
    { name: "Open", line: "Public data and published guidance.", big: "2", small: "sources of record", points: ["NASA POWER daily weather", "NC State Extension guides"] },
  ];
  const included: Array<[string, string]> = [
    ["Three winter plans", "What you do now, add winter cover, add a grain crop"],
    ["Two winters each", "After corn and after soybeans, never added together"],
    ["Past springs", `Every spring from ${n?.firstYear ?? 1981} to ${n?.lastYear ?? 2025}`],
    ["Rye timing", "Any end date between seeding and planting"],
    ["Evidence", "Source, rule and limits behind every number"],
    ["Summary", "Two letter pages for your Extension agent"],
  ];
  return (
    <SiteShell current="about" title={`About · ${APP_NAME}`} springs={n?.springs ?? null}>
      <section className="st-wrap st-phero is-tight">
        <p className="st-small">{CHALLENGE_LABEL}</p>
        <h1>Built for one weekend. Honest for every spring.</h1>
        <p>{APP_NAME} is a NASA Space Apps 2026 project from Charlotte for the Field Shift challenge.</p>
        <p className="st-chip">Free and open for every grower</p>
      </section>
      <section className="st-wrap st-plans">
        {cards.map((c, i) => (
          <Reveal key={c.name} delay={i * 70} className={`st-plan${c.hot ? " is-hot" : ""}`}>
            {c.hot ? <span className="st-plan-flag">Most asked about</span> : null}
            <div className="st-plan-top">
              <h2>{c.name}</h2>
              <p>{c.line}</p>
            </div>
            <div className="st-plan-body">
              <p className="st-plan-big">
                {c.big} <span>{c.small}</span>
              </p>
              <ul className="st-checks">
                {c.points.map((p) => (
                  <Check key={p}>{p}</Check>
                ))}
              </ul>
              <a className={`btn ${c.hot ? "st-btn-ink" : "btn-secondary"}`} href={app()}>
                Open the planner
              </a>
            </div>
          </Reveal>
        ))}
      </section>
      <section className="st-wrap st-section">
        <h2 className="st-h2 is-plain">What's included</h2>
        <dl className="st-incl">
          {included.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="st-wrap st-section st-team">
        <Reveal>
          <h2 className="st-h2 is-plain">The team</h2>
          <p className="st-sub">Two people, split down the middle so every number has one owner.</p>
        </Reveal>
        <div className="st-team-grid">
          <Reveal>
            <h3>Frontend</h3>
            <p>Abhi built the planner you see: the pages, the field pictures, the 3D fields and this site.</p>
          </Reveal>
          <Reveal delay={80}>
            <h3>Backend and data</h3>
            <p>Rahul built the service: the NASA POWER record, every calculation, the NC State rules and the checks.</p>
          </Reveal>
          <Reveal delay={160}>
            <h3>The rule we kept</h3>
            <p>The frontend never computes a number. It shows what the service returned, with its source, or says it is not available.</p>
          </Reveal>
        </div>
      </section>
    </SiteShell>
  );
}
