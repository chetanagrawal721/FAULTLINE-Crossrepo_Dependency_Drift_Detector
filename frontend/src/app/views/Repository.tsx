import { useState } from "react";
import { api, type InventoryDep, type PackageView, type ProjectDetail, type RepositoryView, type WorldDetail } from "../../api/client";
import { useAsync, short } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { EmptyInline, ErrorNote, Loading, StateBlock } from "../shared";

type Go = (view: AppView, id?: string | null) => void;
const TABS = ["Overview", "Inventory", "Dependency worlds", "Relationships"] as const;
const repoTone = (s: string) => (s === "INGESTED" ? "good" : s === "FAILED" ? "warn" : "copper");

function Packages({ packages }: { packages: PackageView[] }) {
  const npm = packages.some((p) => p.locator);
  const columns = ["Package", ...(npm ? ["Instance (path)"] : []), "Declared range", "Resolved version", npm ? "Visible to (importers)" : "Visible version", ...(npm ? [] : ["Artifact (sha256)"])];
  return (
    <DataTable
      testid="packages"
      columns={columns}
      rows={packages.map((p) => [
        <code>{p.name}</code>,
        ...(npm ? [<code>{p.locator}</code>] : []),
        p.declared.length === 0 ? "transitive (not declared)" : p.declared.map((d) => `${d.spec || "any"} · ${d.group}`).join("; "),
        <code>{p.resolved ?? "—"}</code>,
        npm ? (p.visible_to && p.visible_to.length > 0 ? p.visible_to.join(", ") : "no importer depends on it directly") : `${p.visible ?? "not observed"}${p.visible_source ? ` · ${p.visible_source.replace("_", " ")}` : ""}`,
        ...(npm ? [] : [<code>{p.artifact_sha256 ? p.artifact_sha256.slice(0, 12) : ""}</code>]),
      ])}
    />
  );
}

function DepInventory({ items }: { items: InventoryDep[] }) {
  return (
    <DataTable
      testid="inventory-deps"
      columns={["Dependency (group:artifact)", "Version", "Scope", "Where the version comes from"]}
      rows={items.map((d) => [<code>{d.name}</code>, <code>{d.version ?? "unresolved"}</code>, d.scope, `${d.version_source}${d.note ? ` · ${d.note}` : ""}`])}
    />
  );
}

function World({ w }: { w: WorldDetail }) {
  const r = w.reproducibility as Record<string, unknown>;
  const lock = r.lockfile as { kind?: string; path?: string; sha256?: string } | null | undefined;
  if (w.status === "FAILED") {
    return (
      <div className="state-panel compact" role="alert" data-testid="world-failed">
        <Status tone="warn">RESOLUTION FAILED</Status>
        <h2>No world: {String(w.failure?.reason ?? "unknown")}</h2>
        <p>
          {String(w.failure?.code ?? "")}: {String(w.failure?.detail ?? "")} A failed resolution is not an empty or clean world. Nothing from this project can be compared until this is resolved.
        </p>
      </div>
    );
  }
  return (
    <div>
      <p className="panel-copy">
        <Status tone={w.status === "OK" ? "good" : "warn"}>{w.status === "OK_PARTIAL" ? "PARTIAL (private packages)" : w.status}</Status> from {w.source === "lockfile" ? `a lockfile (${lock?.kind ?? "lock"})` : `${w.resolver ?? "resolver"} at a recorded cutoff`}
        {w.world_hash && (
          <>
            {" "}
            · world <code title={w.world_hash}>{w.world_hash.slice(0, 14)}</code>
          </>
        )}
      </p>
      {w.warnings.map((x) => (
        <p key={x} className="panel-note">
          {x}
        </p>
      ))}
      <details className="attribution-details">
        <summary>Reproducibility</summary>
        <ul className="why-items">
          <li>Resolution cutoff: <code>{String(r.cutoff)}</code></li>
          <li>Platform: <code>{String(r.platform)}</code> · Python <code>{String(r.python)}</code></li>
          <li>Resolver: <code>{String(r.resolver_version)}</code> · flags <code>{Array.isArray(r.flags) ? r.flags.join(" ") : ""}</code></li>
          <li>Index: <code>{String(r.index)}</code></li>
          {lock?.path && <li>Lockfile: <code>{lock.path}</code> sha256 <code>{lock.sha256?.slice(0, 16)}</code></li>}
          <li>Cache key: <code>{String(r.cache_key)}</code></li>
        </ul>
      </details>
      <Packages packages={w.packages} />
    </div>
  );
}

function Worlds({ repo, replay }: { repo: RepositoryView; replay: boolean }) {
  const q = useAsync(() => api.repositoryProjects(repo.id), [repo.id]);
  const [job, setJob] = useState<{ status: string; message: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const poll = (id: string) =>
    api
      .job(id)
      .then((j) => {
        setJob({ status: j.status, message: j.message ?? null });
        if (j.status === "QUEUED" || j.status === "RUNNING") window.setTimeout(() => poll(id), 2000);
        else q.reload();
      })
      .catch((e: Error) => setError(e.message));
  const run = () => {
    setError(null);
    api
      .analyzeRepository(repo.id)
      .then((j) => {
        setJob({ status: j.status, message: j.message ?? null });
        poll(j.job_id);
      })
      .catch((e: Error) => setError(e.message));
  };
  const running = job?.status === "QUEUED" || job?.status === "RUNNING";
  const projects: ProjectDetail[] = q.data ?? [];
  return (
    <div data-testid="world-inspector">
      <p className="panel-copy">For each project in the pinned snapshot: what its manifests declare, what the lockfile or resolver chose, and what an importer can see in the built world. These are three different things. Nothing from the repository is executed.</p>
      <AppAction onClick={run} disabled={running || replay}>
        {running ? "Resolving…" : "Resolve worlds"}
      </AppAction>
      {job && <span className="panel-note"> job {job.status}{job.message ? ` · ${job.message}` : ""}</span>}
      {error && <p className="panel-note" role="alert">{error}</p>}
      {q.error && <ErrorNote error={q.error} />}
      {q.data && projects.length === 0 && <EmptyInline title="No projects resolved yet">Press “Resolve worlds”.</EmptyInline>}
      {projects.map((p) => (
        <div key={p.project_id} data-testid="project-card" className="project-card">
          <h3 className="project-card-title">
            <code>{p.name ?? p.rel_path}</code> <span className="panel-note">{p.ecosystem} · {p.rel_path} · {p.origin}</span>
          </h3>
          {p.notes.map((n) => (
            <p className="panel-note" key={n}>
              {n}
            </p>
          ))}
          <p className="panel-note">Manifests: {p.manifests.map((m) => `${m.path} (${m.kind}, ${m.parse_status})`).join(", ") || "none"}</p>
          {p.world ? (
            <World w={p.world} />
          ) : p.ecosystem === "maven" ? (
            <>
              <p className="panel-note">Declared-dependency inventory only. Maven is never run and nothing is resolved.</p>
              {p.inventory.length > 0 ? <DepInventory items={p.inventory} /> : <p className="panel-note">No dependencies declared in this POM.</p>}
            </>
          ) : (
            <p className="panel-note">Not resolved yet.</p>
          )}
        </div>
      ))}
    </div>
  );
}

function Files({ repo }: { repo: RepositoryView }) {
  const [only, setOnly] = useState<"manifest" | "all">("manifest");
  const q = useAsync(() => api.repositoryFiles(repo.id, only === "manifest" ? "manifest" : undefined), [repo.id, repo.pinned_sha, only]);
  return (
    <div>
      <div className="inline-choice">
        <label>
          <input type="radio" checked={only === "manifest"} onChange={() => setOnly("manifest")} /> Manifests and lockfiles
        </label>
        <label>
          <input type="radio" checked={only === "all"} onChange={() => setOnly("all")} /> All files
        </label>
      </div>
      {q.error && <ErrorNote error={q.error} />}
      {!q.data && !q.error && <Loading what="files" />}
      {q.data && q.data.length === 0 && <EmptyInline title={`No ${only === "manifest" ? "manifests or lockfiles" : "files"} found`} />}
      {q.data && q.data.length > 0 && (
        <>
          <DataTable
            testid="inventory"
            columns={["Path", "Kind", "Role", "Size", "SHA-256"]}
            rows={q.data.slice(0, 300).map((f) => [<code>{f.path}</code>, `${f.kind}${f.reason ? ` (${f.reason})` : ""}`, `${f.role ?? ""}${f.tags.length ? ` · ${f.tags.join(", ")}` : ""}`, f.size ?? "", <code>{f.sha256 ? f.sha256.slice(0, 12) : ""}</code>])}
          />
          {q.data.length > 300 && <p className="panel-note">Showing the first 300 of {q.data.length}.</p>}
        </>
      )}
    </div>
  );
}

function RepoDetail({ id, go }: { id: string; go: Go }) {
  const { analysis, replay } = useWorkspace();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const q = useAsync(() => api.repository(id), [id], { pollMs: 2000, keepPolling: (r) => r.status === "PENDING" || r.status === "INGESTING" });
  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <Loading what="the repository" />;
  const r = q.data;
  const label = `${r.owner}/${r.name}`;
  const rels = (analysis?.relationships ?? []).filter((x) => x.producer.startsWith(label) || x.consumer.startsWith(label));
  return (
    <>
      <div className="repository-title">
        <div>
          <Status tone={repoTone(r.status)}>{r.status === "INGESTED" && r.snapshot?.status === "PARTIAL" ? "INGESTED (partial)" : r.status}</Status>
          <h2>{label}</h2>
          <code>
            {short(r.pinned_sha, 12)} · requested ref: {r.requested_ref ?? "default branch"}
          </code>
        </div>
      </div>
      <div className="app-tabs">
        {TABS.map((name) => (
          <button className={tab === name ? "active" : ""} onClick={() => setTab(name)} key={name}>
            {name}
          </button>
        ))}
      </div>
      <Panel title={tab} meta="Persisted repository record">
        {tab === "Overview" && (
          <>
            <dl className="manifest-grid">
              {(
                [
                  ["Repository URL", r.url],
                  ["Pinned SHA", <code key="p" data-testid="pinned-sha" title={r.pinned_sha ?? ""}>{short(r.pinned_sha, 12)}</code>],
                  ["Committed", r.committed_at ?? "Not recorded"],
                  ["Ingestion state", r.status],
                  ["Snapshot", r.snapshot ? `${r.snapshot.file_count} entries · ${r.snapshot.stored_files} stored · ${r.snapshot.manifests} manifest or lockfile${r.snapshot.manifests === 1 ? "" : "s"}` : "None yet"],
                  ["Default branch", r.default_branch ?? "Not recorded"],
                  ["Fork / archived", `${r.is_fork ? "fork" : "not a fork"} · ${r.is_archived ? "archived" : "not archived"}`],
                  ["Warnings", r.snapshot?.warnings.length ? r.snapshot.warnings.join(" · ") : "None recorded"],
                ] as [string, React.ReactNode][]
              ).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
            {r.status === "FAILED" && r.error && (
              <p className="panel-note" role="alert">
                Ingestion failed: {String(r.error.code)}: {String(r.error.message)} {r.error.retryable ? "" : "Not retryable."}
              </p>
            )}
            <p className="panel-note">Every later step uses this exact commit, never the branch name. Nothing in the repository is executed or installed.</p>
          </>
        )}
        {tab === "Inventory" && <Files repo={r} />}
        {tab === "Dependency worlds" && (r.status === "INGESTED" ? <Worlds repo={r} replay={replay} /> : <EmptyInline title="The repository is not fetched yet">Worlds are resolved from the pinned snapshot.</EmptyInline>)}
        {tab === "Relationships" &&
          (rels.length === 0 ? (
            <EmptyInline title="No relationship involves this repository">{analysis ? "None was found in the latest analysis." : "No analysis has been run."}</EmptyInline>
          ) : (
            <DataTable columns={["Candidate", "Level", "Status"]} rows={rels.map((x) => [`${x.producer} → ${x.consumer}`, `${x.level} · ${x.confidence}`, x.status])} onRow={() => go("relationships")} />
          ))}
      </Panel>
    </>
  );
}

export function RepositoryView({ go, id }: { go: Go; id: string | null }) {
  const { project } = useWorkspace();
  if (id) return <RepoDetail id={id} go={go} />;
  const repos = project?.repositories ?? [];
  if (!project || repos.length === 0) {
    return (
      <StateBlock label="NO REPOSITORIES" title="No repository has been added to this project." testid="repos-empty">
        Add repositories from New analysis. This is not a clean result.
        <br />
        <AppAction onClick={() => go("new")}>New analysis</AppAction>
      </StateBlock>
    );
  }
  return (
    <Panel title="Repositories" meta={project.name}>
      <div data-testid="repositories-panel">
        <DataTable
          columns={["Repository", "Pinned", "State", "Snapshot"]}
          rowAttrs={() => ({ "data-testid": "repo-card" })}
          rows={repos.map((r) => [
            <strong>{r.owner}/{r.name}</strong>,
            <code>{short(r.pinned_sha, 10)}</code>,
            <Status tone={repoTone(r.status)}>{r.status}</Status>,
            r.snapshot ? `${r.snapshot.file_count} entries · ${r.snapshot.manifests} manifest or lockfile${r.snapshot.manifests === 1 ? "" : "s"}` : "none",
          ])}
          onRow={(i) => go("repository", repos[i].id)}
        />
      </div>
    </Panel>
  );
}
