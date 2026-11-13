import { useEffect, type ReactNode } from "react";
import { APP_NAME, CHALLENGE_LABEL } from "../config";
import { DATA_CREDITS, DISCLOSURES, LIBRARIES } from "../content/credits";
import { GLOSSARY } from "../content/glossary";
import { SOURCES } from "../content/strategies";

/*
  Methods (card 6.4) and Credits (card 6.5). Plain reading pages so a judge can explain
  the method back and see every source, license and disclosure. The back link returns to
  the planner state the reader came from.
*/

function backToPlanner(e: React.MouseEvent<HTMLAnchorElement>) {
  if (document.referrer && new URL(document.referrer).origin === window.location.origin && window.history.length > 1) {
    e.preventDefault();
    window.history.back();
  }
}

function DocPage({ title, lede, children }: { title: string; lede: string; children: ReactNode }) {
  useEffect(() => {
    const before = document.title;
    document.title = `${title} · ${APP_NAME}`;
    return () => {
      document.title = before;
    };
  }, [title]);
  return (
    <div className="doc">
      <header className="doc-head">
        <a className="doc-brand" href="./">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">{APP_NAME}</span>
        </a>
        <a className="header-link" href="./" onClick={backToPlanner}>
          ← Back to the planner
        </a>
      </header>
      <main className="doc-main">
        <p className="marker">{CHALLENGE_LABEL}</p>
        <h1>{title}</h1>
        <p className="doc-lede">{lede}</p>
        {children}
      </main>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="doc-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

export function MethodsPage() {
  return (
    <DocPage
      title="How Fieldback works"
      lede="Fieldback replays a grower's planned winter dates against past springs recorded by NASA and checks them against NC State guidance. It compares plans; it does not forecast next spring or measure a field."
    >
      <Section id="m-question" title="The question it answers">
        <p>
          A corn grower in the North Carolina Piedmont is planning soybeans. Over winter they can leave no planted cover, plant cereal rye
          as a cover crop, or grow winter wheat for grain. Rye protects the soil but uses water while it grows, so in a dry spring ending
          it too close to planting can leave the seedbed dry. Fieldback shows how each plan would have fared across every past spring on
          record for this area.
        </p>
      </Section>

      <Section id="m-data" title="The weather data">
        <ul>
          <li>
            NASA POWER daily estimates for a reference point near Monroe, Union County, NC: corrected precipitation (PRECTOTCORR) and
            root-zone soil wetness (GWETROOT, from the MERRA-2 model), 1981 to 2025.
          </li>
          <li>Values describe a grid cell roughly 50 km across, not one farm. Local storms can make a field wetter or drier.</li>
          <li>The record is saved with the app, so the comparison works offline. The screen says when data is a saved record, live, or draft.</li>
          <li>A day with no rain counts as 0.0 mm. A missing day makes that spring incomplete; incomplete springs are left out and listed.</li>
        </ul>
      </Section>

      <Section id="m-window" title="The planting window">
        <p>
          For each plan, the window is the 30 days ending the day before planting. For soybeans on May 12 that is April 12 to May 11, in
          every year from 1981 to 2025. Moving the rye end date does not move this window; changing the planting date does. Double-crop
          soybeans after wheat have their own June window.
        </p>
      </Section>

      <Section id="m-rank" title="Ranking springs and the driest 20%">
        <ul>
          <li>Each complete spring is ranked by its 30-day rainfall; rank 1 is the driest.</li>
          <li>
            The dry cutoff is the 20th percentile of complete springs for that window, computed once and shared by every plan. Springs at or
            below it are labeled among the driest 20%. Ties at the cutoff count as dry.
          </li>
          <li>With fewer than 15 complete springs, Fieldback withholds the typical, dry and rank labels and shows only the record.</li>
          <li>This 20% line is a label for comparing past years, not a drought declaration.</li>
        </ul>
      </Section>

      <Section id="m-check" title="The field-moisture check">
        <p>
          NC State Extension suggests ending a cover crop at least two weeks before soybean planting if low soil moisture is a concern (
          <a href={SOURCES["ncs-soy-4"].url} target="_blank" rel="noreferrer">
            NC Soybean Production Guide, ch. 4
          </a>
          ). Fieldback flags a spring when the gap between ending rye and planting is under 14 days and either that spring was in the
          driest 20% or the grower reported a moisture concern. The 20% line and the 14-day guidance are separate thresholds from
          separate sources.
        </p>
        <p>
          A flag means "check your field moisture before keeping rye this close to planting", not "the field was dry". It does not apply
          to plans without a cover crop to end.
        </p>
      </Section>

      <Section id="m-winter" title="Rain on ground with no living cover">
        <p>
          For each winter from corn harvest to planting, Fieldback adds up the rain that fell on days with no planned living cover, and
          shows the median across winters. It measures rain and calendar overlap, not erosion: crop residue may still cover the ground,
          and actual cover depends on how the crop established. A heavy-rain day count will be added once its definition is confirmed.
        </p>
      </Section>

      <Section id="m-eras" title="Earlier vs recent">
        <p>
          Counts are compared between 1981–2000 and 2006–2025, with the same cutoff in both. 2001–2005 stays in the full record but in
          neither period. Each period needs at least 15 of its 20 springs. "About as often" means the two periods differ by less than 10
          percentage points. This describes two periods; it is not a trend, a cause, or a forecast.
        </p>
      </Section>

      <Section id="m-3d" title="The 3D farm view">
        <p>
          An illustration of the planned dates. Crops appear and end on each plan's dates, rain falls only in each field's 30 days before
          planting, and soil color and the water line show modeled soil wetness. Plant heights are stages, not measured growth.
        </p>
      </Section>

      <Section id="m-ground" title="Satellites and models vs. your field">
        <p>
          NASA's estimates show what the region around the grid point was like. A soil check in your own field tells you what your
          seedbed is like this year. Fieldback keeps the two apart: your own report is labeled as yours, and it can trigger the NC State
          guidance on its own.
        </p>
      </Section>

      <Section id="m-limits" title="What Fieldback does not claim">
        <ul>
          <li>It does not forecast next spring.</li>
          <li>It does not measure soil moisture, crop growth, erosion or yield on your field.</li>
          <li>It does not estimate water savings, costs or profit, and does not name a "best" rotation.</li>
          <li>Wheat planting and harvest windows are not yet sourced, so that timing check shows unknown.</li>
          <li>The second winter of each two-year rotation (soybeans to corn) is not evaluated yet.</li>
        </ul>
        <p>
          <strong>It supports, not replaces, local advice.</strong> Take the comparison to your NC State Extension agent before changing a
          plan.
        </p>
      </Section>

      <Section id="m-glossary" title="Words used on the screen">
        <dl className="doc-glossary">
          {Object.values(GLOSSARY).map((g) => (
            <div key={g.term}>
              <dt>{g.term}</dt>
              <dd>{g.definition}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </DocPage>
  );
}

export function CreditsPage() {
  return (
    <DocPage
      title="Credits and disclosures"
      lede="Everything Fieldback uses, where it comes from, and what to know about how it was built."
    >
      <Section id="c-data" title="Data and guidance">
        <ul className="doc-credits">
          {DATA_CREDITS.map((d) => (
            <li key={d.name}>
              <a href={d.url} target="_blank" rel="noreferrer">
                {d.name}
              </a>{" "}
              · {d.owner}
              <p>{d.used}</p>
              {d.note ? <p className="doc-note">{d.note}</p> : null}
            </li>
          ))}
        </ul>
      </Section>

      <Section id="c-code" title="Open-source code and fonts">
        <div className="table-scroll doc-table">
          <table>
            <thead>
              <tr>
                <th scope="col">Package</th>
                <th scope="col">Version</th>
                <th scope="col">License</th>
                <th scope="col">Used for</th>
              </tr>
            </thead>
            <tbody>
              {LIBRARIES.map((l) => (
                <tr key={l.name}>
                  <th scope="row">{l.name}</th>
                  <td>{l.version}</td>
                  <td>{l.license}</td>
                  <td>{l.use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="doc-note">
          Source code:{" "}
          <a href="https://github.com/abhijandyala/sa2026" target="_blank" rel="noreferrer">
            github.com/abhijandyala/sa2026
          </a>
        </p>
      </Section>

      <Section id="c-disclose" title="Disclosures">
        <dl className="doc-glossary">
          {DISCLOSURES.map((d) => (
            <div key={d.title}>
              <dt>{d.title}</dt>
              <dd>{d.text}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </DocPage>
  );
}

export function PrivacyPage() {
  return (
    <DocPage
      title="Privacy and terms"
      lede="What Fieldback keeps, what it sends and to whom, and the terms for using what it shows."
    >
      <Section id="p-keep" title="What Fieldback keeps">
        <p>
          Nothing about you. There are no accounts, no cookies, no analytics and no browser storage. Your farm dates live only in
          this page while it is open; closing the tab clears them.
        </p>
      </Section>
      <Section id="p-send" title="What is sent, and where">
        <ul>
          <li>The Union County sample is stored with this site. Opening it sends nothing anywhere.</li>
          <li>
            When the live service is connected, applying dates sends your plan dates to it so it can replay them against past
            springs. Choosing another place sends that place's coordinates so it can find the NASA POWER grid cell.
          </li>
          <li>The service asks NASA for the grid cell's center, not your exact point.</li>
          <li>Shared links hold view choices only (plan, year, winter, priorities, listed place). Never your dates or typed coordinates.</li>
        </ul>
      </Section>
      <Section id="p-terms" title="Terms of use">
        <ul>
          <li>
            Fieldback replays past weather to support a conversation with your Extension agent. It is not a forecast, a field
            measurement or professional advice, and it makes no promise about yields, costs or outcomes.
          </li>
          <li>It is provided as is, without warranty, as a NASA Space Apps Challenge 2026 project.</li>
          <li>
            NASA does not endorse Fieldback. NASA POWER data is used under NASA's open data terms; NC State Extension guidance is
            linked to its source and summarized, not copied.
          </li>
          <li>Every source and library, with its license, is listed on the Credits page.</li>
        </ul>
      </Section>
    </DocPage>
  );
}
