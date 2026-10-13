import { useCallback, useEffect, useRef, useState } from "react";
import { api, type InventoryDep, type Job, type PackageView, type ProjectDetail, type WorldDetail } from "../api/client";

function WorldStatus({ w }: { w: WorldDetail }) {
  const cls = w.status === "OK" ? "enabled" : w.status === "OK_PARTIAL" ? "partial" : "bad";
  const label = w.status === "OK_PARTIAL" ? "PARTIAL (private packages)" : w.status;
  return <span className={`pill pill-${cls}`}>{label}</span>;
}

/** The three views of a version are separate columns with their own labels: a range is not a version, and a chosen version
 *  is not necessarily what an importer sees. */
function Packages({ packages }: { packages: PackageView[] }) {
  const npm = packages.some((p) => p.locator);
  return (
    <div className="table-wrap">
      <table data-testid="packages">
        <thead>
          <tr>
            <th>Package</th>
            {npm && <th title="Where this exact instance sits in node_modules">Instance (path)</th>}
            <th title="The range written in a manifest, if any manifest names this package">Declared range</th>
            <th title="The version the lockfile or resolver chose">Resolved version</th>
            <th title={npm ? "Importers whose lookup finds THIS instance" : "The version an importer actually sees, read from the built world"}>
              {npm ? "Visible to (importers)" : "Visible version"}
            </th>
            {!npm && <th>Artifact (sha256)</th>}
          </tr>
        </thead>
        <tbody>
          {packages.map((p) => (
            <tr key={p.locator ?? p.name}>
              <td className="mono">{p.name}</td>
              {npm && <td className="mono">{p.locator}</td>}
              <td>
                {p.declared.length === 0 ? (
                  <span className="muted">transitive (not declared)</span>
                ) : (
                  p.declared.map((d, i) => (
                    <div key={i} className="mono">
                      {d.spec || "any"}
                      <span className="muted small"> · {d.group}</span>
                    </div>
                  ))
                )}
              </td>
              <td className="mono">{p.resolved ?? "—"}</td>
              <td className="mono">
                {npm ? (
                  p.visible_to && p.visible_to.length > 0 ? p.visible_to.join(", ") : <span className="muted">no importer depends on it directly</span>
                ) : (
                  <>
                    {p.visible ?? <span className="muted">not observed</span>}
                    {p.visible_source && <span className="muted small"> · {p.visible_source.replace("_", " ")}</span>}
                  </>
                )}
              </td>
              {!npm && <td className="mono">{p.artifact_sha256 ? p.artifact_sha256.slice(0, 12) : ""}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Inventory({ items }: { items: InventoryDep[] }) {
  return (
    <div className="table-wrap">
      <table data-testid="inventory-deps">
        <thead>
          <tr>
            <th>Dependency (group:artifact)</th>
            <th>Version</th>
            <th>Scope</th>
            <th>Where the version comes from</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d, i) => (
            <tr key={i}>
              <td className="mono">{d.name}</td>
              <td className="mono">{d.version ?? <span className="muted">unresolved</span>}</td>
              <td>{d.scope}</td>
              <td>
                {d.version_source}
                {d.note && <span className="muted small"> · {d.note}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function World({ w }: { w: WorldDetail }) {
  const r = w.reproducibility as Record<string, unknown>;
  const lock = r.lockfile as { kind?: string; path?: string; sha256?: string } | null | undefined;
  if (w.status === "FAILED") {
    return (
      <div className="callout bad" role="alert" data-testid="world-failed">
        <strong>No world: resolution failed ({String(w.failure?.reason ?? "unknown")})</strong>
        <p>
          {String(w.failure?.code ?? "")}: {String(w.failure?.detail ?? "")}
        </p>
        <p className="muted small">
          A failed resolution is not an empty or clean world. Nothing from this project can be compared until this is resolved.
        </p>
      </div>
    );
  }
  return (
    <div>
      <p className="small">
        <WorldStatus w={w} /> from {w.source === "lockfile" ? `a lockfile (${lock?.kind ?? "lock"})` : `${w.resolver ?? "resolver"} at a recorded cutoff`}
        {w.world_hash && (
          <>
            {" "}
            · world <code title={w.world_hash}>{w.world_hash.slice(0, 14)}</code>
          </>
        )}
      </p>
      {w.warnings.map((x) => (
        <p key={x} className="callout warn small">
          {x}
        </p>
      ))}
      <details>
        <summary>Reproducibility</summary>
        <ul className="small">
          <li>Resolution cutoff: <code>{String(r.cutoff)}</code></li>
          <li>Platform: <code>{String(r.platform)}</code> · Python <code>{String(r.python)}</code></li>
          <li>Resolver: <code>{String(r.resolver_version)}</code> · flags <code>{Array.isArray(r.flags) ? r.flags.join(" ") : ""}</code></li>
          <li>Index: <code>{String(r.index)}</code></li>
          {lock?.path && (
            <li>Lockfile: <code>{lock.path}</code> sha256 <code>{lock.sha256?.slice(0, 16)}</code></li>
          )}
          <li>Cache key: <code>{String(r.cache_key)}</code></li>
        </ul>
      </details>
      <Packages packages={w.packages} />
    </div>
  );
}

export function WorldInspector({ repositoryId }: { repositoryId: string }) {
  const [projects, setProjects] = useState<ProjectDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(() => {
    api
      .repositoryProjects(repositoryId)
      .then(setProjects)
      .catch((e: Error) => setError(e.message));
  }, [repositoryId]);

  useEffect(() => {
    load();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [load]);

  const poll = (id: string) =>
    api
      .job(id)
      .then((j) => {
        setJob(j);
        if (j.status === "QUEUED" || j.status === "RUNNING") timer.current = window.setTimeout(() => poll(id), 2000);
        else load();
      })
      .catch((e: Error) => setError(e.message));

  const run = () => {
    setError(null);
    api
      .analyzeRepository(repositoryId)
      .then((j) => {
        setJob(j);
        poll(j.job_id);
      })
      .catch((e: Error) => setError(e.message));
  };

  const running = job?.status === "QUEUED" || job?.status === "RUNNING";
  return (
    <section className="panel" aria-label="World inspector" data-testid="world-inspector">
      <p>
        <a href="#/">← Back</a>
      </p>
      <h2>Dependency worlds</h2>
      <p className="muted small">
        For each project in the pinned snapshot: what its manifests declare, what the lockfile or resolver chose, and what an
        importer can see in the built world. These are three different things. Nothing from the repository is executed.
      </p>
      <div className="row">
        <button className="btn" onClick={run} disabled={running}>
          {running ? "Resolving…" : "Resolve worlds"}
        </button>
        {job && (
          <span className="muted small">
            job {job.status}
            {job.message ? ` · ${job.message}` : ""}
          </span>
        )}
      </div>
      {job?.status === "FAILED" && (
        <p className="error-text" role="alert">
          Analysis failed: {String(job.error?.message ?? job.error?.code ?? "unknown error")}
        </p>
      )}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {projects && projects.length === 0 && <p className="muted">No projects resolved yet. Press “Resolve worlds”.</p>}
      <ul className="plain-list">
        {projects?.map((p) => (
          <li key={p.project_id} className="panel" data-testid="project-card">
            <div className="row">
              <strong className="mono">{p.name ?? p.rel_path}</strong>
              <span className="muted small">
                {p.ecosystem} · {p.rel_path} · {p.origin}
              </span>
            </div>
            {p.notes.map((n) => (
              <p key={n} className="muted small">
                {n}
              </p>
            ))}
            <p className="small muted">
              Manifests: {p.manifests.map((m) => `${m.path} (${m.kind}, ${m.parse_status})`).join(", ") || "none"}
            </p>
            {p.world ? (
              <World w={p.world} />
            ) : p.ecosystem === "maven" ? (
              <div>
                <p className="muted small">Declared-dependency inventory only. Maven is never run and nothing is resolved.</p>
                {p.inventory.length > 0 ? <Inventory items={p.inventory} /> : <p className="muted">No dependencies declared in this POM.</p>}
              </div>
            ) : (
              <p className="muted">Not resolved yet.</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
