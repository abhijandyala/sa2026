import { useData } from "./state/useData";
import { Planner } from "./screens/Planner";
import { Gallery } from "./screens/Gallery";
import { CreditsPage, MethodsPage, PrivacyPage } from "./screens/Pages";
import { Banner, Button } from "./ui/components";
import { APP_NAME } from "./config";
import { Landing } from "./site/Landing";
import { AboutPage, EvidencePage, GrowersPage, ProductPage, ResourcesPage } from "./site/pages";

/*
  Routes (query `view`): the marketing site is the front door; `?view=app` is the planner.
  A link that carries planner state in its hash (older shared links have no `view`) still
  opens the planner, so nothing shared before the site existed breaks.
*/
export function App() {
  const view = new URLSearchParams(window.location.search).get("view");
  if (view === "gallery") return <Gallery />;
  if (view === "methods") return <MethodsPage />;
  if (view === "credits") return <CreditsPage />;
  if (view === "privacy") return <PrivacyPage />;
  if (view === "product") return <ProductPage />;
  if (view === "growers") return <GrowersPage />;
  if (view === "evidence") return <EvidencePage />;
  if (view === "resources") return <ResourcesPage />;
  if (view === "about") return <AboutPage />;
  const plannerHash = /(^|[#&])(s|pg|y|l|r|p|e|v|loc)=/.test(window.location.hash);
  if (view === "app" || plannerHash) return <PlannerRoute />;
  return <Landing />;
}

function PlannerRoute() {
  const { state, retry, apply, applying, hasLiveApi, client, place, chooseLocation } = useData();

  if (state.status === "loading") {
    return (
      <main className="skeleton-page" aria-busy="true">
        <p className="skeleton-status" role="status">
          {APP_NAME} · Loading the saved NASA weather sample for Union County…
        </p>
        {/* Placeholders in the planner's own layout, so nothing jumps when the data arrives. */}
        <div className="skeleton-row" aria-hidden="true">
          <span className="sk sk-title" />
          <span className="sk sk-chip" />
        </div>
        <div className="skeleton-hero" aria-hidden="true">
          <span className="sk sk-world" />
          <span className="sk sk-almanac" />
        </div>
        <div className="skeleton-cards" aria-hidden="true">
          <span className="sk sk-card" />
          <span className="sk sk-card" />
          <span className="sk sk-card" />
        </div>
      </main>
    );
  }

  if (state.status === "error") {
    const f = state.failure;
    return (
      <main className="center-state">
        <p className="marker">{APP_NAME}</p>
        <Banner kind="error">
          <strong>{f.kind === "timeout" ? "Loading the saved sample took too long." : f.message}</strong>
          {f.detail ? <span className="error-detail"> {f.detail}</span> : null}
        </Banner>
        <Button variant="primary" onClick={retry}>
          Try again
        </Button>
      </main>
    );
  }

  return (
    <Planner
      data={state.data}
      apply={apply}
      applying={applying}
      hasLiveApi={hasLiveApi}
      client={client}
      place={place}
      chooseLocation={chooseLocation}
    />
  );
}
