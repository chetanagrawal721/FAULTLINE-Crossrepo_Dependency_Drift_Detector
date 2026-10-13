import { useEffect, useState } from "react";
import { AppAction, Icon, Logo, Status, ThemeToggle, type IconName } from "../ui/primitives";
import { goApp, navigate, type AppView, type Route } from "../lib/route";
import { WorkspaceProvider, useWorkspace } from "./context";
import { ModeStatus } from "./shared";
import { OverviewView } from "./views/Overview";
import { NewAnalysisView } from "./views/NewAnalysis";
import { RunView } from "./views/Run";
import { FindingsView } from "./views/Findings";
import { FindingView } from "./views/Finding";
import { WorldsView } from "./views/Worlds";
import { WitnessView } from "./views/Witness";
import { RelationshipsView } from "./views/Relationships";
import { InventoryView } from "./views/Inventory";
import { EvidenceView } from "./views/Evidence";
import { JobsView } from "./views/Jobs";
import { RepositoryView } from "./views/Repository";
import { CoverageView } from "./views/Coverage";
import { SettingsView } from "./views/Settings";

const appNavigation: { id: AppView; label: string; icon: IconName }[] = [
  { id: "overview", label: "Overview", icon: "overview" },
  { id: "new", label: "New analysis", icon: "plus" },
  { id: "findings", label: "Findings", icon: "findings" },
  { id: "worlds", label: "World matrix", icon: "matrix" },
  { id: "relationships", label: "Relationships", icon: "link" },
  { id: "inventory", label: "Inventory graph", icon: "graph" },
  { id: "evidence", label: "Evidence", icon: "evidence" },
  { id: "jobs", label: "Jobs", icon: "jobs" },
  { id: "repository", label: "Repositories", icon: "repo" },
  { id: "coverage", label: "Capabilities", icon: "sliders" },
  { id: "settings", label: "Settings", icon: "gear" },
];

const COLLAPSE_KEY = "faultline-sidebar-collapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

const viewMeta: Record<AppView, [string, string]> = {
  overview: ["Overview", "Follow investigations from pinned repository inputs to evidence-backed findings."],
  new: ["New analysis", "Choose the repositories and review the investigation boundary before anything runs."],
  run: ["Analysis run", "Inspect persisted stages without fabricated percentages or progress."],
  findings: ["Findings", "Review verdicts and follow each one to its witness and evidence."],
  finding: ["Finding detail", "Trace a scoped conclusion through its Why-Path."],
  worlds: ["World matrix", "Compare reference and consumer worlds across the cells that were built."],
  witness: ["Witness detail", "Inspect the six runs and the failure signature behind a witness."],
  relationships: ["Relationships", "Review how repositories are related, and the suspected connections that are not findings."],
  inventory: ["Inventory graph", "Explore repositories, projects, manifests, packages, and evidence-backed edges."],
  evidence: ["Evidence", "Inspect the bundle behind a witness and its integrity checks."],
  jobs: ["Jobs", "Review every background job with its status, run time and failure class."],
  repository: ["Repository detail", "Inspect a pinned repository snapshot and its available inventory."],
  coverage: ["Capabilities and coverage", "Support reported per ecosystem, oracle and feature by this deployment."],
  settings: ["Settings", "Manage preferences and access, and inspect application information."],
};

function ModeBanner() {
  const { caps, apiError } = useWorkspace();
  if (apiError && !caps) {
    return (
      <div className="mode-note is-error" role="alert">
        The API did not respond: {apiError}
      </div>
    );
  }
  const mode = caps?.mode;
  const text =
    mode === "REPLAY"
      ? "Recorded evidence: nothing can be started or re-run in this mode."
      : mode === "FIXTURE"
        ? "Committed fixture repositories run through the real pipeline. Submitted repositories are analysed live."
        : mode === "LIVE"
          ? "Live analysis of public repositories you submit."
          : "Checking what this deployment can do.";
  return (
    <div className={mode === "REPLAY" ? "mode-note is-replay" : "mode-note"} data-testid="mode-banner">
      {text}
    </div>
  );
}

function ProjectPicker() {
  const { projects, project, setProjectId, caps } = useWorkspace();
  if (projects.length === 0) return null;
  const kind = (mode: string) => (caps?.mode === "REPLAY" ? "Recorded" : mode === "FIXTURE" ? "Fixture" : "Live");
  return (
    <select className="project-select" aria-label="Active project" value={project?.id ?? ""} onChange={(e) => setProjectId(e.target.value)} data-testid="project-picker">
      {projects.map((p) => (
        <option key={p.id} value={p.id}>
          {kind(p.mode)} · {p.name}
        </option>
      ))}
    </select>
  );
}

function Shell({ route, theme, onTheme }: { route: Route; theme: "light" | "dark"; onTheme: () => void }) {
  const { caps, health, replay } = useWorkspace();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawer, setDrawer] = useState(false);
  const view = route.view;
  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
    } catch {
      /* storage can be blocked; the choice then lasts until the page reloads */
    }
  }, [collapsed]);
  const go = (next: AppView, id?: string | null) => {
    setDrawer(false);
    goApp(next, id);
  };
  const toggle = () => (window.matchMedia("(max-width: 900px)").matches ? setDrawer(!drawer) : setCollapsed(!collapsed));
  const [title, subtitle] = viewMeta[view];
  const active = view === "finding" || view === "witness" ? "findings" : view === "run" ? "new" : view;
  return (
    <main className={`workspace shell${collapsed ? " is-collapsed" : ""}${drawer ? " is-drawer-open" : ""}`}>
      <aside className="app-sidebar" aria-label="Application navigation">
        <button className="app-brand" onClick={() => navigate("home")} title="FAULTLINE home">
          <Logo compact={collapsed} />
        </button>
        <nav data-testid="nav">
          <span className="nav-heading">Workbench</span>
          {appNavigation.map((item) => (
            <button
              className={active === item.id ? "active" : ""}
              onClick={() => go(item.id)}
              key={item.id}
              aria-current={active === item.id ? "page" : undefined}
              data-view={item.id}
              title={collapsed ? item.label : undefined}
            >
              <Icon name={item.icon} size={17} />
              <span className="nav-label">{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <small className="foot-status">{health ? `API ${health.status} · schema v${health.schema_version}${health.auth === "token" ? " · token required to start work" : ""}` : "API not reached yet"}</small>
          <button className="foot-exit" onClick={() => navigate("home")} title="Back to the product site">
            <Icon name="exit" size={16} />
            <span className="nav-label">Exit workspace</span>
          </button>
        </div>
      </aside>
      {drawer && <div className="drawer-scrim" onClick={() => setDrawer(false)} aria-hidden="true" />}
      <div className="workspace-main">
        <header className="app-topbar">
          <button className="sidebar-toggle" onClick={toggle} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} aria-expanded={!collapsed} title={collapsed ? "Expand navigation" : "Collapse navigation"}>
            <Icon name="panel" size={18} />
          </button>
          <nav className="crumbs" aria-label="Breadcrumb">
            <span>Workbench</span>
            <i aria-hidden="true">/</i>
            <b>{title}</b>
          </nav>
          <div className="topbar-actions">
            <ProjectPicker />
            {caps && <ModeStatus mode={caps.mode} />}
            <ThemeToggle theme={theme} onToggle={onTheme} />
          </div>
        </header>
        <div className="workspace-content">
          <ModeBanner />
          <div className="app-page-heading">
            <div>
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>
            <div className="app-actions">
              {view !== "overview" && (
                <AppAction quiet onClick={() => go("overview")}>
                  Overview
                </AppAction>
              )}
              {view === "overview" && (
                <AppAction quiet onClick={() => go("jobs")}>
                  View all jobs
                </AppAction>
              )}
              {view === "overview" && (
                <AppAction onClick={() => go("new")} disabled={replay}>
                  New analysis
                </AppAction>
              )}
            </div>
          </div>
          {view === "overview" && <OverviewView go={go} />}
          {view === "new" && <NewAnalysisView go={go} />}
          {view === "run" && <RunView go={go} jobId={route.id} />}
          {view === "findings" && <FindingsView go={go} />}
          {view === "finding" && <FindingView go={go} id={route.id} />}
          {view === "worlds" && <WorldsView go={go} />}
          {view === "witness" && <WitnessView go={go} id={route.id} />}
          {view === "relationships" && <RelationshipsView go={go} />}
          {view === "inventory" && <InventoryView go={go} />}
          {view === "evidence" && <EvidenceView go={go} id={route.id} />}
          {view === "jobs" && <JobsView go={go} />}
          {view === "repository" && <RepositoryView go={go} id={route.id} />}
          {view === "coverage" && <CoverageView />}
          {view === "settings" && <SettingsView theme={theme} onTheme={onTheme} />}
        </div>
      </div>
    </main>
  );
}

export function Workspace({ route, theme, onTheme }: { route: Route; theme: "light" | "dark"; onTheme: () => void }) {
  return (
    <WorkspaceProvider>
      <Shell route={route} theme={theme} onTheme={onTheme} />
    </WorkspaceProvider>
  );
}

export { Status };
