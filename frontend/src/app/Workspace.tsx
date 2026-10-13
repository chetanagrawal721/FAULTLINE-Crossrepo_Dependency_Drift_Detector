import { useState } from "react";
import { AppAction, Icon, Logo, Status, ThemeToggle } from "../ui/primitives";
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

const appNavigation: { id: AppView; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "new", label: "New analysis" },
  { id: "findings", label: "Findings" },
  { id: "worlds", label: "World matrix" },
  { id: "relationships", label: "Relationships" },
  { id: "inventory", label: "Inventory graph" },
  { id: "evidence", label: "Evidence" },
  { id: "jobs", label: "Jobs" },
  { id: "repository", label: "Repositories" },
  { id: "coverage", label: "Capabilities" },
  { id: "settings", label: "Settings" },
];

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
  coverage: ["Capabilities & coverage", "Support reported per ecosystem, oracle and feature by this deployment."],
  settings: ["Settings", "Manage preferences and access, and inspect application information."],
};

function ModeBanner() {
  const { caps, apiError } = useWorkspace();
  if (apiError && !caps) {
    return (
      <div className="prototype-banner" role="alert">
        <span className="pulse-dot" />
        The API did not respond: {apiError}
      </div>
    );
  }
  const mode = caps?.mode;
  const text =
    mode === "REPLAY"
      ? "Recorded evidence: nothing can be started or re-run in this mode"
      : mode === "FIXTURE"
        ? "Reproducible fixtures: committed repositories run through the real pipeline. Submitted repositories are analysed live."
        : mode === "LIVE"
          ? "Live analysis of public repositories you submit"
          : "Checking what this deployment can do…";
  return (
    <div className="prototype-banner" data-testid="mode-banner">
      <span className="pulse-dot" />
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
  const [sidebar, setSidebar] = useState(false);
  const view = route.view;
  const go = (next: AppView, id?: string | null) => {
    setSidebar(false);
    goApp(next, id);
  };
  const [title, subtitle] = viewMeta[view];
  const active = view === "finding" || view === "witness" ? "findings" : view === "run" ? "new" : view;
  return (
    <main className="workspace">
      <aside className={sidebar ? "app-sidebar open" : "app-sidebar"}>
        <button className="app-brand" onClick={() => navigate("home")}>
          <Logo />
        </button>
        <nav aria-label="Application navigation" data-testid="nav">
          <span>Workbench</span>
          {appNavigation.map((item) => (
            <button className={active === item.id ? "active" : ""} onClick={() => go(item.id)} key={item.id} aria-current={active === item.id ? "page" : undefined} data-view={item.id}>
              <Icon name="grid" size={15} />
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          {caps && <ModeStatus mode={caps.mode} />}
          <small>{health ? `API ${health.status} · schema v${health.schema_version}${health.auth === "token" ? " · token required to start work" : ""}` : "API not reached yet"}</small>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="app-topbar">
          <button className="sidebar-toggle" onClick={() => setSidebar(!sidebar)} aria-label="Toggle application navigation">
            <Icon name="menu" />
          </button>
          <div>
            <span>FAULTLINE / {title}</span>
          </div>
          <div className="topbar-actions">
            <ProjectPicker />
            {caps && <ModeStatus mode={caps.mode} />}
            <ThemeToggle theme={theme} onToggle={onTheme} />
            <button className="exit-app" onClick={() => navigate("home")}>
              Exit workspace
            </button>
          </div>
        </header>
        <ModeBanner />
        <div className="workspace-content">
          <div className="app-page-heading">
            <div>
              <span className="micro-label">Application workbench</span>
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
