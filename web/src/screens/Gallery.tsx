import { useRef, useState, type ReactNode } from "react";
import {
  Banner,
  Button,
  DateField,
  Drawer,
  Segmented,
  Slider,
  SourceChip,
  StatusPill,
  StrategyCardShell,
  Term,
  TriStateField,
  YearTile,
} from "../ui/components";

/*
  Every component in every state on one page (card 0.3). Use it for design review,
  keyboard checks, the grayscale check, and as the reference for /design-sync.
  All numbers here are illustrative.
*/
export function Gallery() {
  const [seg, setSeg] = useState<"cover" | "buffer">("buffer");
  const [slider, setSlider] = useState(198);
  const [date, setDate] = useState<string | null>("2027-05-12");
  const [tri, setTri] = useState<"yes" | "no" | "unknown">("unknown");
  const [selectedYear, setSelectedYear] = useState(2012);
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);

  return (
    <main className="gallery">
      <header className="gallery-head">
        <p className="marker">Fieldback · component gallery</p>
        <h1>Components and states</h1>
        <p className="gallery-note">Illustrative values only. Check each section with the keyboard, on a phone, and in grayscale.</p>
      </header>

      <Section title="Buttons">
        <div className="row">
          <Button variant="primary">Apply dates</Button>
          <Button>Show evidence</Button>
          <Button variant="quiet">Reset example</Button>
          <Button disabled>Apply dates</Button>
        </div>
      </Section>

      <Section title="Segmented control">
        <Segmented
          label="Emphasis"
          value={seg}
          onChange={setSeg}
          options={[
            { value: "cover", label: "More living cover" },
            { value: "buffer", label: "More time before planting" },
          ]}
        />
      </Section>

      <Section title="Status pills">
        <div className="row">
          <StatusPill kind="ok">No dry-window flag</StatusPill>
          <StatusPill kind="check">Check field moisture</StatusPill>
          <StatusPill kind="unavailable">Weather unavailable</StatusPill>
          <StatusPill kind="inapplicable">Rye timing does not apply</StatusPill>
          <StatusPill kind="saved">Saved NASA record · Nov 14, 2026</StatusPill>
          <StatusPill kind="synthetic">Synthetic test data</StatusPill>
        </div>
      </Section>

      <Section title="Source chips">
        <div className="row">
          <SourceChip kind="nasa" href="https://power.larc.nasa.gov/docs/services/api/temporal/daily/" />
          <SourceChip kind="ncstate" href="https://content.ces.ncsu.edu/north-carolina-soybean-production-guide/rotational-considerations" />
          <SourceChip kind="usda" />
          <SourceChip kind="farmer" />
          <SourceChip kind="calculated" />
          <SourceChip kind="sample" />
        </div>
      </Section>

      <Section title="Year tiles">
        <div className="tile-demo">
          {[
            { y: 2009, r: 0.95, c: true },
            { y: 2010, r: 0.6, c: true },
            { y: 2011, r: 0.35, c: true, m: "typical" as const },
            { y: 2012, r: 0.05, c: true, m: "dry-replay" as const },
            { y: 2013, r: null, c: false },
            { y: 2014, r: 0.75, c: true },
          ].map((t) => (
            <YearTile
              key={t.y}
              year={t.y}
              pctRank={t.r}
              complete={t.c}
              marker={t.m}
              selected={selectedYear === t.y}
              onSelect={() => setSelectedYear(t.y)}
              description={t.c ? `illustrative rank ${t.r}` : "no complete record"}
            />
          ))}
        </div>
        <p className="gallery-note">Paler is drier. Circle marks the typical year, diamond the dry replay year, hatching an incomplete record.</p>
      </Section>

      <Section title="Slider">
        <div style={{ maxWidth: 520 }}>
          <Slider
            label="End the cover crop"
            min={150}
            max={208}
            value={slider}
            onChange={setSlider}
            valueText={`${slider} planned days with living rye · ${210 - slider} days before soybean planting`}
            boundary={{ at: 196, label: "14 days" }}
          />
        </div>
      </Section>

      <Section title="Form fields">
        <div className="form-demo">
          <DateField id="g-soy" label="Planned soybean planting date" value={date} onChange={setDate} allowUnknown />
          <DateField
            id="g-rye"
            label="When would you end the rye cover?"
            value="2027-05-20"
            onChange={() => {}}
            error="Choose a rye end date after seeding and before soybean planting."
          />
          <TriStateField
            id="g-moist"
            label="Field moisture concern"
            hint="Reported by you. Leave Unknown if you have not checked."
            value={tri}
            onChange={setTri}
          />
        </div>
      </Section>

      <Section title="Glossary term">
        <p>
          A <Term term="cover crop">A crop planted to protect and improve the soil rather than to sell.</Term> keeps
          living roots in the ground over winter.
        </p>
      </Section>

      <Section title="Banners">
        <div className="stack">
          <Banner kind="synthetic">
            <strong>Synthetic test data, not for judging.</strong> Real NASA weather loads when the saved record is added.
          </Banner>
          <Banner kind="error">Weather unavailable for this planting window. You can still compare dates.</Banner>
          <Banner kind="info">Saved NASA record · retrieved Nov 14, 2026.</Banner>
        </div>
      </Section>

      <Section title="Strategy cards">
        <div className="cards-demo">
          <StrategyCardShell
            index={1}
            name="What you do now"
            subtitle="No planted winter cover · crop residue may remain"
            headline="9 of 44 springs"
            secondary="had a dry soybean planting window"
            metric="Rye timing does not apply"
            status={<StatusPill kind="inapplicable">No rye timing</StatusPill>}
            actions={<Button>Show evidence</Button>}
          />
          <StrategyCardShell
            index={2}
            name="Protect the soil"
            subtitle="Cereal rye before soybeans, rye again before corn"
            headline="9 of 44 springs"
            secondary="dry window and under 14 days between rye and planting"
            metric="12 days before planting · 198 planned days with living rye"
            status={<StatusPill kind="check">Check field moisture</StatusPill>}
            badges={<SourceChip kind="ncstate" />}
            actions={
              <>
                <Button variant="primary">Adjust rye timing</Button>
                <Button>Show evidence</Button>
              </>
            }
            selected
            tone="check"
          />
          <StrategyCardShell
            index={3}
            name="Earn more"
            subtitle="Wheat for grain, then June soybeans"
            headline="Not compared"
            secondary="Weather unavailable for this window"
            metric="5 days between wheat harvest and planting"
            status={<StatusPill kind="unavailable">Weather unavailable</StatusPill>}
            actions={<Button>Show evidence</Button>}
          />
        </div>
      </Section>

      <Section title="Drawer">
        <Button ref={opener} onClick={() => setOpen(true)}>
          Show evidence
        </Button>
        <Drawer open={open} title="Why this check appeared" onClose={() => setOpen(false)} returnFocusRef={opener}>
          <p>Dry window (NASA) and a 12-day gap (your plan).</p>
          <p>NC State: end the cover at least 2 weeks before planting if soil moisture is a concern.</p>
        </Drawer>
      </Section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="gallery-section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
