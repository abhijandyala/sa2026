import { useEffect, useRef, useState, type CSSProperties } from "react";
import { APP_NAME, CHALLENGE_LABEL } from "../config";
import { WinterPicture } from "../screens/planner/WinterPicture";
import { CalendarScene, RyeScene, SpringsScene, TourScene } from "./demo/scenes";
import { app, Arrow, Chevron, Lazy, Reveal, SiteShell, StatTile, to, useNumbers, Watch, whole } from "./Site";
import { useSiteData } from "./useSiteData";
import { ApiPanel, AskRye, BareRainCard, GapCard, InputWheel, LayerStack, LinePanel, SourceBadges, SpringDotsCard, SummarySheet } from "./visuals";

/*
  The landing page. Section by section it follows the tabs.com home page Abhi recorded
  (hero with a wide picture, source grid with a rolling stat, an auto-advancing list
  beside a line-art panel, hover cards, a dark band with a typed question, a layered
  diagram, three columns, a carousel, a dark trust card, reading links). Where that page
  shows photos and product screenshots, this one shows recordings of the real planner.
*/

const SOURCES = ["NASA POWER", "MERRA-2", "NC State Extension", "NCDA&CS", "NC Climate Office", "USDA NRCS", "Union County, NC", "NASA Space Apps", "Field Shift", "Open data"];

export function Landing() {
  const data = useSiteData();
  const n = useNumbers(data);
  const [tab, setTab] = useState(0);
  const [hold, setHold] = useState(false);
  const rail = useRef<HTMLDivElement>(null);
  const [slide, setSlide] = useState(0);
  const [edge, setEdge] = useState({ start: true, end: false });

  // The list beside the line-art panel advances on its own until someone picks an item.
  useEffect(() => {
    if (hold) return;
    const id = window.setInterval(() => setTab((t) => (t + 1) % 3), 7000);
    return () => window.clearInterval(id);
  }, [hold]);

  const points = [
    { title: "See the rain that lands on bare ground", text: "Each plan shows how much winter rain fell while nothing was growing, as the middle value of every winter on record." },
    { title: "Count the dry springs", text: `Every spring since ${n?.firstYear ?? 1981} is one dot. The dry ones are marked, so you see how often a plan would have asked for a field check.` },
    { title: "Check the two-week rule", text: "NC State says to end a cover crop two weeks before soybeans when soil moisture is a concern. The planner shows where your dates sit." },
  ];

  const questions = [
    { q: "How much rain falls on bare ground?", page: "Compare plans", href: app("pg=compare"), key: "current" as const, leg: 0 },
    { q: "Which springs were dry here?", page: "Past springs", href: app("pg=springs"), key: "cover" as const, leg: 0 },
    { q: "When should the rye end?", page: "Rye timing", href: app("s=cover&pg=rye"), key: "cover" as const, leg: 0 },
    { q: "What about the winter after soybeans?", page: "Plan detail", href: app("s=cover&l=2&pg=plan"), key: "cover" as const, leg: 1 },
    { q: "When does each job happen?", page: "Calendar", href: app("pg=calendar"), key: "current" as const, leg: 1 },
    { q: "What do I bring to my agent?", page: "Extension summary", href: app("v=summary"), key: "cover" as const, leg: 1 },
  ];
  const move = (dir: number) => {
    const el = rail.current;
    if (!el) return;
    const card = el.querySelector<HTMLElement>(".st-q");
    const step = (card?.offsetWidth ?? 320) + 24;
    el.scrollBy({ left: dir * step, behavior: "smooth" });
  };
  const goTo = (i: number) => {
    const el = rail.current;
    if (!el) return;
    el.scrollTo({ left: ((el.scrollWidth - el.clientWidth) * i) / (questions.length - 1), behavior: "smooth" });
  };

  return (
    <SiteShell current="home" title={`${APP_NAME} · Compare winter crop plans against past springs`} springs={n?.springs ?? null}>
      {/* ------------------------------------------------------------ hero */}
      <section className="st-hero st-wrap">
        <p className="st-eyebrow st-rise" style={{ "--d": "0ms" } as CSSProperties}>
          {CHALLENGE_LABEL}
        </p>
        <div className="st-hero-head">
          <h1 className="st-rise" style={{ "--d": "60ms" } as CSSProperties}>
            <span>Every spring is different.</span>
            <span>Your winter plan can be ready.</span>
          </h1>
          <div className="st-hero-side st-rise" style={{ "--d": "140ms" } as CSSProperties}>
            <p>
              Compare three winter plans for a corn and soybean farm against every spring NASA has recorded since {n?.firstYear ?? 1981}.
            </p>
            <div className="st-hero-cta">
              <a className="btn btn-primary" href={app()}>
                Open the planner
              </a>
              <a className="btn btn-secondary" href="#watch">
                Watch it work
              </a>
            </div>
          </div>
        </div>
        <div className="st-hero-stage st-rise" id="watch" style={{ "--d": "220ms" } as CSSProperties}>
          <div className="st-hero-demo">{data ? <TourScene data={data} /> : <div className="st-skeleton" style={{ aspectRatio: "1400 / 880" }} />}</div>
        </div>
      </section>

      {/* ------------------------------------------------------------ sources + stat */}
      <section className="st-wrap st-trust">
        <Reveal>
          <p className="st-small">Built on public records and published guidance</p>
          <div className="st-logos">
            <ul>
              {SOURCES.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            {n ? (
              <StatTile
                stats={[
                  { value: String(n.springs), label: "springs replayed for every plan", tone: "plain" },
                  { value: whole(n.checks), unit: ` of ${n.of}`, label: "springs to check soil moisture, with rye", tone: "teal" },
                  { value: whole(n.bareCover), unit: " mm", label: "winter rain with nothing growing, with rye", tone: "cyan" },
                ]}
              />
            ) : null}
          </div>
        </Reveal>
      </section>

      {/* ------------------------------------------------------------ list + line-art panel */}
      <section className="st-wrap st-section">
        <Reveal>
          <h2 className="st-h2">
            Three winter plans
            <span>measured the same way.</span>
          </h2>
          <p className="st-sub">Each winter is replayed on its own. Nothing is added up or averaged across plans.</p>
        </Reveal>
        <div className="st-split">
          <div className="st-points" role="tablist" aria-label="What the planner shows">
            {points.map((p, i) => (
              <div key={p.title} className={`st-point${i === tab ? " is-on" : ""}`}>
                <span className="st-point-line" aria-hidden="true">
                  <i key={`${tab}-${hold}`} className={hold ? "is-held" : undefined} />
                </span>
                <button
                  type="button"
                  role="tab"
                  aria-selected={i === tab}
                  onClick={() => {
                    setTab(i);
                    setHold(true);
                  }}
                >
                  {p.title}
                </button>
                <div className="st-point-body" hidden={i !== tab}>
                  <p>{p.text}</p>
                </div>
              </div>
            ))}
          </div>
          <LinePanel>
            {n ? (
              <div key={tab} className="st-swap">
                {tab === 0 ? <BareRainCard n={n} /> : tab === 1 ? <SpringDotsCard n={n} /> : <GapCard n={n} />}
              </div>
            ) : null}
          </LinePanel>
        </div>
      </section>

      {/* ------------------------------------------------------------ hover cards */}
      <section className="st-wrap st-section">
        <Reveal>
          <h2 className="st-h2">
            One question per page.
            <span>Pictures first, proof on request.</span>
          </h2>
          <p className="st-sub">Point at a card to play it. Every recording is the planner itself, running on the saved NASA record.</p>
        </Reveal>
        <div className="st-cards">
          {[
            { title: "Move the day the rye ends", text: "Drag the stake and watch the bare weeks, the dry-spring checks and the living days change.", href: app("s=cover&pg=rye"), scene: data ? <RyeScene data={data} chrome={false} play="hover" /> : null, ratio: "1180 / 700" },
            { title: "Replay any past spring", text: "Pick a dry year, a wet one or any glass in the row. Only the weather changes.", href: app("pg=springs"), scene: data ? <SpringsScene data={data} chrome={false} play="hover" /> : null, ratio: "1180 / 700" },
            { title: "Put every job on its day", text: "Harvest, seeding, ending the rye and planting, for each plan and each winter.", href: app("pg=calendar"), scene: data ? <CalendarScene data={data} chrome={false} play="hover" /> : null, ratio: "1180 / 690" },
            { title: "Print a page for your agent", text: "Two letter pages with the numbers, what to discuss, your questions and room for notes.", href: app("v=summary"), scene: <SummarySheet />, ratio: "1180 / 690" },
          ].map((c, i) => (
            <Reveal key={c.title} delay={i * 70} className="st-fcard">
              <a className="st-fcard-head" href={c.href}>
                <span>
                  <strong>{c.title}</strong>
                  <span>{c.text}</span>
                </span>
                <span className="st-fcard-go" aria-hidden="true">
                  <Arrow />
                </span>
              </a>
              <div className="st-fcard-shot">
                <Lazy ratio={c.ratio}>{c.scene}</Lazy>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------ dark band */}
      <section className="st-dark">
        <span className="st-notch" aria-hidden="true" />
        <div className="st-wrap st-dark-in">
          <Reveal>
            <p className="st-dark-tag">
              <span className="fb-mark" aria-hidden="true" /> Rye timing
            </p>
            <h2>
              Ask one question.
              <br />
              Get {n?.springs ?? 45} springs of answers.
            </h2>
            <p className="st-dark-sub">
              Move one date and the planner replays it against the whole record. It never guesses next spring; it shows what past springs did.
            </p>
            <a className="btn st-btn-light" href={app("s=cover&pg=rye")}>
              Open Rye timing <Chevron />
            </a>
          </Reveal>
        </div>
        <div className="st-dotband">
          <div className="st-dots" aria-hidden="true" />
          <div className="st-wrap st-dotband-in">{n ? <AskRye n={n} /> : null}</div>
        </div>
      </section>

      {/* ------------------------------------------------------------ layered diagram */}
      <section className="st-wrap st-section st-intro">
        <Reveal>
          <h2 className="st-h2 is-plain">One picture for past weather, guidance and your dates.</h2>
          <p className="st-sub">
            The planner lays your planned dates over NASA's daily record and NC State's published guidance, so one screen answers what three sources used to.
          </p>
          <a className="btn btn-primary btn-small" href="?view=methods">
            How it works <Chevron />
          </a>
          <Watch href="#watch" />
        </Reveal>
        <Reveal delay={120}>
          <LayerStack />
        </Reveal>
      </section>

      {/* ------------------------------------------------------------ three columns */}
      <section className="st-wrap st-section">
        <Reveal>
          <h2 className="st-h2 is-plain">
            Built to fit the way you already plan.
            <br />
            And the people you plan with.
          </h2>
          <p className="st-sub">Enter the dates you know. Leave the rest as unknown. Unknown is a real answer here.</p>
        </Reveal>
        <div className="st-three">
          <Reveal className="st-col">
            <div className="st-col-art is-plain">
              <InputWheel />
            </div>
            <h3>Start from what you know</h3>
            <p>Harvest, seeding, ending the rye and planting dates for both winters. Soil and moisture concerns if you have them.</p>
            <a className="st-link" href={app()}>
              Edit the farm dates <i />
            </a>
          </Reveal>
          <Reveal className="st-col" delay={80}>
            <div className="st-col-art is-teal">{n ? <ApiPanel n={n} /> : null}</div>
            <h3>Every number has a source</h3>
            <p>The planner shows what the service returned and nothing else. Open any number to see the record, the rule and the limits behind it.</p>
            <a className="st-link" href={to("evidence")}>
              See the evidence <i />
            </a>
          </Reveal>
          <Reveal className="st-col" delay={160}>
            <div className="st-col-art is-night">
              <SummarySheet />
            </div>
            <h3>Take it to your Extension agent</h3>
            <p>A printed summary with what to discuss, tick boxes, your questions and space for the adviser's notes.</p>
            <a className="st-link" href={app("v=summary")}>
              Open the summary <i />
            </a>
          </Reveal>
        </div>
      </section>

      {/* ------------------------------------------------------------ carousel */}
      <section className="st-section st-car">
        <div className="st-wrap st-car-head">
          <h2 className="st-h2 is-plain">
            Questions growers
            <br />
            bring to {APP_NAME}
          </h2>
          <div className="st-car-nav">
            <button type="button" aria-label="Earlier questions" disabled={edge.start} onClick={() => move(-1)}>
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                <path d="M9 2.500L4.500 7 9 11.500" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <button type="button" aria-label="More questions" disabled={edge.end} onClick={() => move(1)}>
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                <path d="M5 2.500L9.500 7 5 11.500" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
        <div
          className="st-rail"
          ref={rail}
          onScroll={(e) => {
            const el = e.currentTarget;
            const max = Math.max(1, el.scrollWidth - el.clientWidth);
            setSlide(Math.round((el.scrollLeft / max) * (questions.length - 1)));
            setEdge({ start: el.scrollLeft < 4, end: el.scrollLeft > max - 4 });
          }}
        >
          {questions.map((c) => {
            const plan = n?.view.cards.find((k) => k.key === c.key)?.legs[c.leg]?.plan;
            return (
              <a className="st-q" key={c.q} href={c.href}>
                <span className="st-q-art" aria-hidden="true">
                  {plan?.sequence ? <WinterPicture plan={plan} wide /> : null}
                </span>
                <span className="st-q-page">{c.page}</span>
                <span className="st-q-text">{c.q}</span>
                <span className="st-q-go" aria-hidden="true">
                  <Arrow />
                </span>
              </a>
            );
          })}
        </div>
        <div className="st-wrap st-car-dots">
          <span className="tabular" aria-hidden="true">
            {String(slide + 1).padStart(2, "0")}
          </span>
          <span className="st-car-track">
            <b aria-hidden="true">[</b>
            {questions.map((c, i) => (
              <button key={c.q} type="button" className={i === slide ? "is-on" : undefined} aria-label={`Go to question ${i + 1}`} aria-current={i === slide ? "true" : undefined} onClick={() => goTo(i)} />
            ))}
            <b aria-hidden="true">]</b>
          </span>
          <span className="tabular" aria-hidden="true">
            {String(questions.length).padStart(2, "0")}
          </span>
        </div>
      </section>

      {/* ------------------------------------------------------------ dark trust card */}
      <section className="st-wrap st-section">
        <Reveal className="st-honest">
          <div>
            <p className="st-honest-tag">Honest by design</p>
            <h2>
              A replay, not a forecast.
              <br />
              A regional record, not your gauge.
            </h2>
            <p>Rainfall is a NASA estimate for a grid cell about 55 km wide. Soil wetness is modeled. Every screen says so.</p>
            <a className="st-link is-light" href="?view=methods">
              Read the limits <i />
            </a>
          </div>
          <SourceBadges />
        </Reveal>
      </section>

      {/* ------------------------------------------------------------ reading */}
      <section className="st-wrap st-section st-read">
        <h2 className="st-h2 is-plain">Read how it works.</h2>
        <div className="st-read-grid">
          <Reveal>
            <a className="st-read-lead" href="?view=methods">
              <span className="st-read-art" aria-hidden="true">
                <span className="fb-mark" />
              </span>
              <span className="st-read-kind">Guide</span>
              <strong>How {APP_NAME} replays a winter plan against {n?.springs ?? 45} springs</strong>
            </a>
          </Reveal>
          <Reveal delay={90} className="st-read-list">
            <a href="?view=credits">
              <span className="st-read-kind">Sources</span>
              <strong>Data and credits: every dataset, guide and license the planner uses</strong>
              <span className="st-fcard-go" aria-hidden="true">
                <Arrow />
              </span>
            </a>
            <a href="?view=privacy">
              <span className="st-read-kind">Policy</span>
              <strong>Privacy and terms: what stays on your device and what never leaves it</strong>
              <span className="st-fcard-go" aria-hidden="true">
                <Arrow />
              </span>
            </a>
            <a className="st-read-all" href={to("resources")}>
              <Arrow /> All resources
            </a>
          </Reveal>
        </div>
      </section>
    </SiteShell>
  );
}
