import { useData } from "./state/useData";
import { Planner } from "./screens/Planner";
import { Gallery } from "./screens/Gallery";
import { CreditsPage, MethodsPage } from "./screens/Pages";
import { Banner, Button } from "./ui/components";
import { APP_NAME } from "./config";

export function App() {
  const view = new URLSearchParams(window.location.search).get("view");
  if (view === "gallery") return <Gallery />;
  if (view === "methods") return <MethodsPage />;
  if (view === "credits") return <CreditsPage />;
  return <PlannerRoute />;
}

function PlannerRoute() {
  const { state, retry, apply, applying, hasLiveApi, client } = useData();

  if (state.status === "loading") {
    return (
      <main className="center-state" aria-busy="true">
        <p className="marker">{APP_NAME}</p>
        <p>Loading the saved NASA weather sample for Union County…</p>
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

  return <Planner data={state.data} apply={apply} applying={applying} hasLiveApi={hasLiveApi} client={client} />;
}
