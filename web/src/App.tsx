import { useBundle } from "./state/useBundle";
import { Planner } from "./screens/Planner";
import { Gallery } from "./screens/Gallery";
import { Banner, Button } from "./ui/components";
import { APP_NAME } from "./config";

export function App() {
  const view = new URLSearchParams(window.location.search).get("view");
  if (view === "gallery") return <Gallery />;
  return <PlannerRoute />;
}

function PlannerRoute() {
  const { state, retry } = useBundle();

  if (state.status === "loading") {
    return (
      <main className="center-state" aria-busy="true">
        <p className="marker">{APP_NAME}</p>
        <p>Loading saved NASA weather for Union County…</p>
      </main>
    );
  }

  if (state.status === "error") {
    return (
      <main className="center-state">
        <p className="marker">{APP_NAME}</p>
        <Banner kind="error">
          <strong>{state.message}</strong>
          {state.detail ? <span className="error-detail"> {state.detail}</span> : null}
        </Banner>
        <Button variant="primary" onClick={retry}>
          Try again
        </Button>
      </main>
    );
  }

  return <Planner bundle={state.bundle} synthetic={state.origin === "fixture"} />;
}
