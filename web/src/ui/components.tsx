import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";
import { IconAlert, IconCheck, IconClose, IconDash, IconFlask, IconInfo, IconRain } from "./icons";

/* ---------------------------------------------------------------- Button */

type ButtonProps = { variant?: "primary" | "secondary" | "quiet" } & ButtonHTMLAttributes<HTMLButtonElement>;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", children, ...rest },
  ref,
) {
  return (
    <button ref={ref} type="button" className={`btn btn-${variant}`} {...rest}>
      {children}
    </button>
  );
});

/* ---------------------------------------------------------------- Segmented control
   A radio group: arrow keys move the choice (WCAG, handbook p.16). */

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (v: T) => void;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const idx = options.findIndex((o) => o.value === value);
  const move = (dir: number) => {
    const next = (idx + dir + options.length) % options.length;
    onChange(options[next]!.value);
    refs.current[next]?.focus();
  };
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o, i) => (
        <button
          key={o.value}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          className="segmented-option"
          onClick={() => onChange(o.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" || e.key === "ArrowDown") {
              e.preventDefault();
              move(1);
            } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
              e.preventDefault();
              move(-1);
            }
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- Status pill
   Meaning carried by text and icon, never color alone (playbook p.37). */

export type StatusKind = "ok" | "check" | "unavailable" | "inapplicable" | "synthetic" | "saved" | "dry" | "live";

const STATUS_ICON: Record<StatusKind, ReactNode> = {
  ok: <IconCheck />,
  check: <IconAlert />,
  unavailable: <IconDash />,
  inapplicable: <IconDash />,
  synthetic: <IconFlask />,
  saved: <IconCheck />,
  dry: <IconRain />,
  live: <IconCheck />,
};

export function StatusPill({ kind, children }: { kind: StatusKind; children: ReactNode }) {
  return (
    <span className={`pill pill-${kind}`}>
      {STATUS_ICON[kind]}
      <span>{children}</span>
    </span>
  );
}

/* ---------------------------------------------------------------- Source chip */

export type SourceKind = "nasa" | "usda" | "ncstate" | "farmer" | "calculated" | "sample" | "model";
const SOURCE_LABEL: Record<SourceKind, string> = {
  nasa: "NASA",
  usda: "USDA",
  ncstate: "NC State",
  farmer: "Farmer reported",
  calculated: "Calculated",
  sample: "Sample",
  model: "NASA model",
};

/**
 * Source tags for "Show sources" (card 6.3). Hidden, including from screen readers,
 * until the planner turns on audit mode; then every number shows where it came from.
 */
export function Src({ k }: { k: SourceKind | SourceKind[] }) {
  const kinds = Array.isArray(k) ? k : [k];
  return (
    <span className="src-group">
      {kinds.map((kind) => (
        <span key={kind} className={`src chip chip-${kind}`}>
          {SOURCE_LABEL[kind]}
        </span>
      ))}
    </span>
  );
}

export function SourceChip({ kind, href, title }: { kind: SourceKind; href?: string; title?: string }) {
  const text = SOURCE_LABEL[kind];
  return href ? (
    <a className={`chip chip-${kind}`} href={href} target="_blank" rel="noreferrer" title={title}>
      {text}
      <span className="visually-hidden"> (opens source in a new tab)</span>
    </a>
  ) : (
    <span className={`chip chip-${kind}`} title={title}>
      {text}
    </span>
  );
}

/* ---------------------------------------------------------------- Year tile
   Drier windows are paler (less rain, less blue). Incomplete years are hatched and
   never shown as dry (handbook p.11). Text label always present for grayscale. */

export function YearTile({
  year,
  pctRank,
  complete,
  selected,
  marker,
  onSelect,
  description,
}: {
  year: number;
  pctRank: number | null;
  complete: boolean;
  selected: boolean;
  marker?: "typical" | "dry-replay";
  onSelect: () => void;
  description: string;
}) {
  const fill = complete && pctRank !== null ? Math.round(18 + pctRank * 72) : 0;
  return (
    <button
      type="button"
      className={`year-tile${selected ? " is-selected" : ""}${complete ? "" : " is-incomplete"}`}
      style={complete ? ({ "--fill": `${fill}%` } as CSSProperties) : undefined}
      aria-pressed={selected}
      aria-label={`${year}: ${description}`}
      onClick={onSelect}
    >
      <span className="year-tile-label">{String(year).slice(2)}</span>
      {marker ? <span className={`year-tile-marker marker-${marker}`} aria-hidden="true" /> : null}
    </button>
  );
}

/* ---------------------------------------------------------------- Slider */

export function Slider({
  label,
  min,
  max,
  value,
  onChange,
  valueText,
  boundary,
  id,
}: {
  label: string;
  min: number;
  max: number;
  value: number;
  onChange: (v: number) => void;
  valueText: string;
  boundary?: { at: number; label: string };
  id?: string;
}) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const pct = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <div className="slider">
      <label htmlFor={inputId} className="slider-label">
        {label}
      </label>
      <div className="slider-track-wrap">
        <input
          id={inputId}
          type="range"
          min={min}
          max={max}
          step={1}
          value={value}
          aria-valuetext={valueText}
          onChange={(e) => onChange(Number(e.target.value))}
          onKeyDown={(e) => {
            if (e.key === "PageUp" || e.key === "PageDown") {
              e.preventDefault();
              const next = Math.min(max, Math.max(min, value + (e.key === "PageUp" ? 7 : -7)));
              onChange(next);
            }
          }}
        />
        {boundary ? (
          <span className="slider-boundary" style={{ left: `${pct(boundary.at)}%` }}>
            <span className="slider-boundary-label">{boundary.label}</span>
          </span>
        ) : null}
      </div>
      <output htmlFor={inputId} className="slider-readout tabular">
        {valueText}
      </output>
    </div>
  );
}

/* ---------------------------------------------------------------- Field wrapper + error */

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
  htmlFor: string;
}) {
  return (
    <div className={`field${error ? " has-error" : ""}`}>
      <label htmlFor={htmlFor} className="field-label">
        {label}
      </label>
      {hint ? (
        <p className="field-hint" id={`${htmlFor}-hint`}>
          {hint}
        </p>
      ) : null}
      {children}
      {error ? (
        <p className="field-error" id={`${htmlFor}-error`} role="alert">
          <IconAlert /> {error}
        </p>
      ) : null}
    </div>
  );
}

/* ---------------------------------------------------------------- Date field with Unknown
   Unknown is an explicit choice, never a blank (playbook p.39). */

export function DateField({
  id,
  label,
  value,
  onChange,
  allowUnknown,
  error,
  hint,
}: {
  id: string;
  label: string;
  value: string | null;
  onChange: (v: string | null) => void;
  allowUnknown?: boolean;
  error?: string | null;
  hint?: string;
}) {
  const unknown = value === null;
  const describedBy = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <Field label={label} hint={hint} error={error} htmlFor={id}>
      <div className="date-row">
        <input
          id={id}
          type="date"
          className="input"
          value={value ?? ""}
          disabled={unknown}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(e) => onChange(e.target.value || null)}
        />
        {allowUnknown ? (
          <label className="check-inline">
            <input type="checkbox" checked={unknown} onChange={(e) => onChange(e.target.checked ? null : "")} />
            Unknown
          </label>
        ) : null}
      </div>
    </Field>
  );
}

/* ---------------------------------------------------------------- Yes / No / Unknown */

export function TriStateField({
  id,
  label,
  value,
  onChange,
  hint,
}: {
  id: string;
  label: string;
  value: "yes" | "no" | "unknown";
  onChange: (v: "yes" | "no" | "unknown") => void;
  hint?: string;
}) {
  return (
    <fieldset className="tristate" aria-describedby={hint ? `${id}-hint` : undefined}>
      <legend className="field-label">{label}</legend>
      {hint ? (
        <p className="field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      <div className="tristate-options">
        {(["yes", "no", "unknown"] as const).map((v) => (
          <label key={v} className="tristate-option">
            <input type="radio" name={id} value={v} checked={value === v} onChange={() => onChange(v)} />
            {v === "yes" ? "Yes" : v === "no" ? "No" : "Unknown"}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/* ---------------------------------------------------------------- Glossary term
   Opens on click, tap or keyboard; never hover-only (handbook p.16). */

export function Term({ term, children }: { term: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);
  return (
    <span className="term" ref={ref}>
      <button
        type="button"
        className="term-button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
      >
        {term}
        <IconInfo size={13} />
      </button>
      {open ? (
        <span className="term-pop" id={id} role="note">
          {children}
        </span>
      ) : null}
    </span>
  );
}

/* ---------------------------------------------------------------- Drawer
   Keeps the page state; Escape closes; focus returns to the opener (playbook p.43). */

export function Drawer({
  open,
  title,
  onClose,
  returnFocusRef,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLElement>;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const headingId = useId();
  // Latest handler in a ref, so re-renders (typing in a field) never re-run the focus
  // effect below. Focus moves only when the drawer opens or closes.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    const opener = returnFocusRef?.current;
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  if (!open) return null;
  return (
    <div className="drawer-layer">
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <div className="drawer" role="dialog" aria-modal="true" aria-labelledby={headingId} tabIndex={-1} ref={panel}>
        <header className="drawer-head">
          <h2 id={headingId}>{title}</h2>
          <button type="button" className="btn btn-quiet icon-only" onClick={onClose} aria-label="Close">
            <IconClose />
          </button>
        </header>
        <div className="drawer-body">{children}</div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Banner */

export function Banner({ kind, children }: { kind: "synthetic" | "error" | "info"; children: ReactNode }) {
  return (
    <div className={`banner banner-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {kind === "synthetic" ? <IconFlask /> : kind === "error" ? <IconAlert /> : <IconInfo />}
      <div>{children}</div>
    </div>
  );
}

/* ---------------------------------------------------------------- Strategy card shell
   Fixed slot order for all three cards so rows line up (playbook p.40, handbook p.10). */

export function StrategyCardShell({
  index,
  name,
  subtitle,
  headline,
  secondary,
  metric,
  status,
  badges,
  actions,
  selected,
  tone,
}: {
  index: number;
  name: string;
  subtitle: string;
  headline: ReactNode;
  secondary?: ReactNode;
  metric?: ReactNode;
  status?: ReactNode;
  badges?: ReactNode;
  actions?: ReactNode;
  selected?: boolean;
  tone?: "default" | "check";
}) {
  return (
    <article className={`strategy-card${selected ? " is-selected" : ""}${tone === "check" ? " tone-check" : ""}`}>
      <header className="sc-head">
        <span className="sc-index tabular" aria-hidden="true">
          {index}
        </span>
        <div>
          <h3 className="sc-name">{name}</h3>
          <p className="sc-sub">{subtitle}</p>
        </div>
      </header>
      <div className="sc-headline">{headline}</div>
      <div className="sc-secondary">{secondary}</div>
      <div className="sc-metric">{metric}</div>
      <div className="sc-status">{status}</div>
      <div className="sc-badges">{badges}</div>
      <div className="sc-actions">{actions}</div>
    </article>
  );
}
