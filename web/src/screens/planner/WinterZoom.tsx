import { useEffect, useRef, useState } from "react";
import type { LegSummaryVM } from "../../view/build";
import { Roll } from "../../ui/Roll";
import { partDates, partsOf, WinterPicture } from "./WinterPicture";

/*
  The large view of one field picture (Compare page). It grows out of the small picture
  that was clicked and shrinks back into it on close. Under the picture every part of the
  season is named with its planned dates; pointing at a name marks that part in the
  picture and the other way round. Same backend values as the cell it came from.
*/
export function WinterZoom({
  planName,
  leg,
  axisMax,
  from,
  onClose,
}: {
  planName: string;
  leg: LegSummaryVM;
  /** The page's shared scale for the rain glass. */
  axisMax: number;
  /** Where the small picture sits on screen, so the large one can grow out of it. */
  from: DOMRect;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closing = useRef(false);
  const [hot, setHot] = useState<number | null>(null);
  const parts = leg.plan ? partsOf(leg.plan) : [];

  // The move between the small picture's place and the dialog's own place.
  const frames = (el: HTMLElement): Keyframe[] => {
    const to = el.getBoundingClientRect();
    const scale = Math.max(0.05, from.width / to.width);
    const dx = from.left + from.width / 2 - (to.left + to.width / 2);
    const dy = from.top + from.height / 2 - (to.top + to.height / 2);
    return [
      { transform: `translate(${dx}px, ${dy}px) scale(${scale})`, opacity: 0 },
      { opacity: 1, offset: 0.35 },
      { transform: "none", opacity: 1 },
    ];
  };
  const still = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches || typeof ref.current?.animate !== "function";

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!el.open) el.showModal();
    if (!still()) el.animate(frames(el), { duration: 380, easing: "cubic-bezier(0.4, 0, 0.2, 1)" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const close = () => {
    const el = ref.current;
    if (!el || closing.current) return;
    closing.current = true;
    // Closing the dialog itself hands the keyboard back to the picture that opened it.
    const done = () => {
      if (el.open) el.close();
      onClose();
    };
    if (still()) {
      done();
      return;
    }
    el.classList.add("is-closing");
    const a = el.animate(frames(el).reverse(), { duration: 260, easing: "cubic-bezier(0.4, 0, 0.2, 1)", fill: "forwards" });
    a.onfinish = done;
    a.oncancel = done;
  };

  const fill = leg.soilMm === null || axisMax <= 0 ? 0 : Math.max(0, Math.min(1, leg.soilMm / axisMax));
  const { count, denominator } = leg.check;

  return (
    <dialog
      ref={ref}
      className="wz"
      aria-labelledby="wz-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="wz-panel">
        <header className="wz-head">
          <div>
            <h2 id="wz-title">{planName}</h2>
            <p className="wz-sub">
              Winter {leg.leg} · {leg.leg === 1 ? "after corn" : "after soybeans"}
            </p>
          </div>
          <button type="button" className="wz-close" aria-label="Close the large picture" onClick={close} autoFocus>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <div className="wz-fact">
          <span className={`cmp-glass${leg.soilMm === null ? " is-missing" : ""}`} aria-hidden="true">
            <span style={{ height: `${fill * 100}%` }} />
          </span>
          {leg.soilMm === null ? (
            <span className="cmp-none">Not available</span>
          ) : (
            <span className="cmp-value">
              <Roll value={leg.soilMm.toFixed(0)} className="cmp-num" />
              <span className="cmp-unit"> mm</span>
            </span>
          )}
          <span className="wz-fact-label">winter rain with nothing growing</span>
          {leg.check.applies ? (
            <span className="wz-check">
              <span className="ws-dot is-check" aria-hidden="true" />
              {count === null || denominator === null ? "Check soil moisture before planting" : `Check soil moisture in ${count} of ${denominator} springs`}
            </span>
          ) : null}
        </div>

        {leg.plan ? <WinterPicture plan={leg.plan} large highlight={hot} onHover={setHot} /> : null}

        <ol className="wz-parts">
          {parts.map((p, i) => (
            <li
              key={`${p.kind}-${p.from}`}
              className={`wz-part${hot === i ? " is-hot" : ""}`}
              onPointerEnter={() => setHot(i)}
              onPointerLeave={() => setHot(null)}
            >
              <span className={`wp-chip is-${p.kind}`} aria-hidden="true" />
              <span className="wz-part-title">{p.title}</span>
              <span className="wz-part-dates tabular">{partDates(p)}</span>
            </li>
          ))}
        </ol>
        <p className="wz-note">Illustration of planned dates. The rain streaks are not daily rainfall.</p>
      </div>
    </dialog>
  );
}
