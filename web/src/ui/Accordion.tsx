import { useId, type ReactNode } from "react";

/*
  Accordion list (theme kit). One item open at a time. The open item draws a thin accent
  line across its top, the way a tab shows it is current; the others stay quiet grey.
*/
export interface AccordionItem {
  id: string;
  title: ReactNode;
  /** Short text shown at the right of the title row, e.g. a year or a count. */
  meta?: ReactNode;
  body: ReactNode;
}

export function Accordion({ items, open, onOpen, label }: { items: AccordionItem[]; open: string | null; onOpen: (id: string) => void; label: string }) {
  const base = useId();
  return (
    <div className="acc" role="group" aria-label={label}>
      {items.map((it) => {
        const isOpen = it.id === open;
        return (
          <div key={it.id} className={`acc-item${isOpen ? " is-open" : ""}`}>
            <span className="acc-line" aria-hidden="true" />
            <h3 className="acc-head">
              <button type="button" aria-expanded={isOpen} aria-controls={`${base}-${it.id}`} onClick={() => onOpen(it.id)}>
                <span className="acc-title">{it.title}</span>
                {it.meta ? <span className="acc-meta">{it.meta}</span> : null}
              </button>
            </h3>
            <div id={`${base}-${it.id}`} className="acc-body" hidden={!isOpen}>
              {it.body}
            </div>
          </div>
        );
      })}
    </div>
  );
}
