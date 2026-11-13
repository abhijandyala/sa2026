import { NC_PATH, NC_VIEW } from "../../content/ncOutline";
import { PLACES } from "../../content/locations";
import type { GridCell } from "../../state/useData";

/*
  A small North Carolina map for the place picker (Phase 9). The radio list next to it is
  the accessible way to choose; the map is a pointer shortcut and a picture of where each
  place is. A grid-cell box is drawn only when the service has named the cell; nothing here
  works out which cell a point is in.
*/

const px = (lon: number) => (lon - NC_VIEW.west) * NC_VIEW.cos * NC_VIEW.k;
const py = (lat: number) => (NC_VIEW.north - lat) * NC_VIEW.k;
const pct = (v: number, of: number) => `${(v / of) * 100}%`;

export function NcMap({
  choice,
  typed,
  cell,
  onPick,
}: {
  choice: string;
  typed: { latitude: number; longitude: number } | null;
  cell: GridCell | null;
  onPick: (id: string) => void;
}) {
  const { width: W, height: H } = NC_VIEW;
  const inView = (lat: number, lon: number) => px(lon) >= 0 && px(lon) <= W && py(lat) >= 0 && py(lat) <= H;
  return (
    <figure className="nc-map">
      <div className="nc-map-frame" style={{ aspectRatio: `${W} / ${H}` }}>
        <svg viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
          <path d={NC_PATH} className="nc-outline" />
          {cell ? (
            <rect
              className="nc-cell"
              x={px(cell.lon - cell.lonStep / 2)}
              y={py(cell.lat + cell.latStep / 2)}
              width={cell.lonStep * NC_VIEW.cos * NC_VIEW.k}
              height={cell.latStep * NC_VIEW.k}
            />
          ) : null}
        </svg>
        {PLACES.map((p) => (
          <button
            key={p.id}
            type="button"
            tabIndex={-1}
            aria-hidden="true"
            className={`nc-dot${choice === p.id ? " is-on" : ""}${p.sample ? " is-sample" : ""}`}
            style={{ left: pct(px(p.longitude), W), top: pct(py(p.latitude), H) }}
            title={p.name}
            onClick={() => onPick(p.id)}
          >
            {choice === p.id ? <span className="nc-dot-label">{p.name.replace(" County", "")}</span> : null}
          </button>
        ))}
        {typed && inView(typed.latitude, typed.longitude) ? (
          <span
            className="nc-dot is-typed is-on"
            aria-hidden="true"
            style={{ left: pct(px(typed.longitude), W), top: pct(py(typed.latitude), H) }}
          />
        ) : null}
      </div>
      <figcaption>North Carolina, from US Census boundaries. Dots are approximate county centers.</figcaption>
    </figure>
  );
}
