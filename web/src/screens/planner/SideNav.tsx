import type { ReactNode } from "react";
import { APP_NAME } from "../../config";
import type { Page } from "../../state/model";

/*
  The dashboard's dark sidebar: brand, one button per page, and the Extension summary.
  It is its own file so the recording on the landing page shows the same sidebar the
  planner does, not a copy of it.
*/

export const NAV: Array<{ page: Page; label: string; icon: string }> = [
  { page: "overview", label: "Overview", icon: "M3 8l6-5 6 5v7H3zM7.5 15v-4h3v4" },
  { page: "springs", label: "Past springs", icon: "M3 15V9M7 15V4M11 15v-8M15 15v-5" },
  { page: "compare", label: "Compare plans", icon: "M3 4h3v10H3zM7.5 7h3v7h-3zM12 2h3v12h-3z" },
  { page: "plan", label: "Plan detail", icon: "M4 3h10v12H4zM7 7h4M7 10h4" },
  { page: "rye", label: "Rye timing", icon: "M9 15V7M9 7c0-2 1.5-4 4-4 0 2.500-1.500 4-4 4zM9 10c0-2-1.500-3.500-4-3.500 0 2 1.500 3.500 4 3.500z" },
  { page: "calendar", label: "Calendar", icon: "M3 5h12v10H3zM3 8h12M6 3v3M12 3v3" },
];

/** The heading each page shows in the top bar. */
export const TITLES: Record<Page, string> = {
  overview: "Winter plans",
  springs: "Past springs",
  compare: "Compare plans",
  plan: "Plan detail",
  rye: "Rye timing",
  calendar: "Calendar",
};

export const navIcon = (d: string) => (
  <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
    <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export function SideNav({
  page,
  only,
  onGo,
  onSummary,
  children,
}: {
  page: Page;
  /** Show just these pages (the dates-only mode keeps the calendar). */
  only?: Page[];
  onGo: (page: Page) => void;
  /** Leave out to hide the Extension summary button. */
  onSummary?: () => void;
  /** The foot of the sidebar. */
  children?: ReactNode;
}) {
  return (
    <aside className="db-side">
      <a className="db-brand" href="./" aria-label={`${APP_NAME} home`}>
        <span className="fb-mark" aria-hidden="true" />
        {APP_NAME}
      </a>
      <nav className="db-nav" aria-label="Pages">
        {(only ? NAV.filter((n) => only.includes(n.page)) : NAV).map((n) => (
          <button key={n.page} type="button" aria-current={page === n.page ? "page" : undefined} onClick={() => onGo(n.page)}>
            {navIcon(n.icon)}
            {n.label}
          </button>
        ))}
      </nav>
      {onSummary ? (
        <button type="button" className="db-summary" onClick={onSummary}>
          {navIcon("M5 2h6l3 3v11H5zM11 2v3h3M7.5 9h4M7.5 12h4")}
          <span>Extension summary</span>
          <svg className="db-summary-go" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M5 3l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      ) : null}
      {children}
    </aside>
  );
}
