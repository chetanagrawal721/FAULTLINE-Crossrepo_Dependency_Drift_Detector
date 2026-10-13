import { useCallback, useEffect, useState } from "react";
import { api, type Capabilities, type FindingSummary, type Health } from "./api/client";
import { CapabilityBanner } from "./components/CapabilityBanner";
import { FindingDetailView } from "./components/FindingDetail";
import { FindingsList } from "./components/FindingsList";
import { ModeBadge } from "./components/ModeBadge";
import { Dashboard } from "./pages/Dashboard";
import { Findings } from "./pages/Findings";
import { Inventory } from "./pages/Inventory";
import { Jobs } from "./pages/Jobs";
import { RepositoriesPanel } from "./components/RepositoriesPanel";
import { WorldInspector } from "./pages/WorldInspector";
import { ScenarioPanel } from "./components/ScenarioPanel";

function useRoute(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

export default function App() {
  const route = useRoute();
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [findings, setFindings] = useState<FindingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadFindings = useCallback(() => {
    api.findings().then(setFindings).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    let alive = true;
    Promise.all([api.capabilities(), api.health()])
      .then(([c, h]) => {
        if (alive) {
          setCaps(c);
          setHealth(h);
        }
      })
      .catch((e: Error) => alive && setError(e.message));
    loadFindings();
    return () => {
      alive = false;
    };
  }, [loadFindings]);

  const page = route.startsWith("#/findings") ? "findings" : route.startsWith("#/inventory") ? "inventory" : route.startsWith("#/jobs") ? "jobs" : "home";
  const repoId = route.startsWith("#/repo/") ? route.slice("#/repo/".length) : null;
  const findingId = route.startsWith("#/finding/") ? route.slice("#/finding/".length) : null;

  return (
    <div className="shell">
      <header className="top">
        <div>
          <h1>
            <a href="#/" className="plain">
              Faultline
            </a>
          </h1>
          <p className="tag">Witnesses, not warnings.</p>
        </div>
        <div className="top-right">
          {caps && <ModeBadge mode={caps.mode} />}
          {health && (
            <span className={`status status-${health.status}`} data-testid="health">
              API {health.status} · schema v{health.schema_version}
            </span>
          )}
        </div>
      </header>

      <nav className="row" aria-label="Views" data-testid="nav">
        {[["#/", "Dashboard", "home"], ["#/findings", "Findings", "findings"], ["#/inventory", "Inventory graph", "inventory"], ["#/jobs", "Jobs", "jobs"]].map(([href, label, id]) => (
          <a key={id} href={href} className={page === id && !repoId && !findingId ? "btn" : "plain"} aria-current={page === id ? "page" : undefined}>
            {label}
          </a>
        ))}
      </nav>

      {error && (
        <div className="panel error" role="alert">
          Could not reach the API: {error}
        </div>
      )}

      {repoId ? (
        <WorldInspector key={repoId} repositoryId={repoId} />
      ) : findingId ? (
        <FindingDetailView id={findingId} replay={caps?.mode === "REPLAY"} />
      ) : page === "findings" ? (
        <Findings />
      ) : page === "inventory" ? (
        <Inventory />
      ) : page === "jobs" ? (
        <Jobs />
      ) : (
        <>
          <RepositoriesPanel replay={caps?.mode === "REPLAY"} />
          <Dashboard replay={caps?.mode === "REPLAY"} />
          <ScenarioPanel onFinished={loadFindings} />
          <FindingsList findings={findings} />
          {caps ? <CapabilityBanner caps={caps} /> : !error && <p className="muted">Loading capabilities…</p>}
        </>
      )}
    </div>
  );
}
