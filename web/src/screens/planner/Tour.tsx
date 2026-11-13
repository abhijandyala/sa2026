import { useEffect, useRef, useState } from "react";
import { Button } from "../../ui/components";

/*
  "Walk me through it" (pattern from covercrop-selector.org's guided path): four short steps
  that point at the real page, not a slideshow. It never blocks the page; Escape or Done
  ends it. Phase 11's demo mode can drive the same steps.
*/

export interface TourStep {
  target: string;
  title: string;
  body: string;
  /** Runs when the step opens, e.g. jump to the dry spring. */
  onEnter?: () => void;
}

export function Tour({ steps, index, onIndex, onClose }: { steps: TourStep[]; index: number; onIndex: (i: number) => void; onClose: () => void }) {
  const step = steps[index]!;
  const headingRef = useRef<HTMLHeadingElement>(null);
  // Sit on the side away from what the step points at, so the panel never hides it.
  const [side, setSide] = useState<"left" | "right">("right");
  const enterRef = useRef(step.onEnter);
  enterRef.current = step.onEnter;

  useEffect(() => {
    enterRef.current?.();
    const el = document.querySelector<HTMLElement>(step.target);
    el?.classList.add("tour-target");
    el?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    if (el) {
      const r = el.getBoundingClientRect();
      setSide(r.left + r.width / 2 > window.innerWidth * 0.6 ? "left" : "right");
    }
    headingRef.current?.focus();
    return () => el?.classList.remove("tour-target");
  }, [index, step.target]);

  const last = index === steps.length - 1;
  return (
    <aside
      className={`tour tour-${side}`}
      role="dialog"
      aria-modal="false"
      aria-labelledby="tour-title"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <p className="tour-progress">
        <span className="tour-count">
          Step {index + 1} of {steps.length}
        </span>
        <span className="tour-bar" aria-hidden="true">
          <span style={{ width: `${((index + 1) / steps.length) * 100}%` }} />
        </span>
      </p>
      <h2 id="tour-title" ref={headingRef} tabIndex={-1}>
        {step.title}
      </h2>
      <p>{step.body}</p>
      <div className="tour-actions">
        <Button className="btn btn-quiet btn-small" onClick={onClose}>
          End the walkthrough
        </Button>
        <span className="tour-gap" />
        {index > 0 ? (
          <Button className="btn btn-secondary btn-small" onClick={() => onIndex(index - 1)}>
            Back
          </Button>
        ) : null}
        <Button className="btn btn-primary btn-small" onClick={() => (last ? onClose() : onIndex(index + 1))}>
          {last ? "Done" : "Next"}
        </Button>
      </div>
    </aside>
  );
}
