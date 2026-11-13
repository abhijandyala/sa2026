import { PRIORITY_INFO, PRIORITY_ORDER, type Priority } from "../../content/strategies";
import { MAX_PRIORITIES } from "../../state/model";
import { IconCheck } from "../../ui/icons";

/*
  What matters most to the grower (Phase 7.1). Up to two choices. Choosing one adds
  badges and reasons to the cards; the card order and every number stay the same.
*/
export function PriorityPicker({ priorities, onToggle }: { priorities: Priority[]; onToggle: (p: Priority) => void }) {
  const full = priorities.length >= MAX_PRIORITIES;
  return (
    <div className="priority-picker" role="group" aria-labelledby="pp-label">
      <span id="pp-label" className="control-label">
        Priorities<span className="visually-hidden">: what matters most, pick up to {MAX_PRIORITIES}</span>
      </span>
      {PRIORITY_ORDER.map((p) => {
        const on = priorities.includes(p);
        return (
          <button
            key={p}
            type="button"
            className={`pp-option${on ? " is-on" : ""}`}
            aria-pressed={on}
            disabled={!on && full}
            onClick={() => onToggle(p)}
          >
            {on ? <IconCheck size={14} /> : <span className="pp-box" aria-hidden="true" />}
            {PRIORITY_INFO[p].short}
          </button>
        );
      })}
    </div>
  );
}
