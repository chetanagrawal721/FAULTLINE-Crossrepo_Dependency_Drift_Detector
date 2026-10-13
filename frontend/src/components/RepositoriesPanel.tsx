import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, type FileView, type RepositoryView } from "../api/client";

const DEFAULT_PROJECT = "My analysis";

/** What went wrong, in words a person can act on. Distinct states for distinct causes. */
function describe(e: unknown): { title: string; body: string; retryable: boolean } {
  const err = e instanceof ApiError ? e : null;
  const body = err?.message ?? (e instanceof Error ? e.message : "Unknown error");
  switch (err?.code) {
    case "REPOSITORY_NOT_FOUND":
      return { title: "Repository not found", body: "It does not exist, or it was deleted. Check the owner and name.", retryable: false };
    case "REPOSITORY_NOT_ACCESSIBLE":
      return { title: "Repository not accessible", body: "It is private or access-restricted. Only public repositories are supported.", retryable: false };
    case "GITHUB_RATE_LIMITED":
      return { title: "GitHub rate limit reached", body: "This is temporary. Wait a minute and submit again. Setting GITHUB_TOKEN on the server raises the limit.", retryable: true };
    case "REF_NOT_FOUND":
      return { title: "Branch, tag or commit not found", body: body, retryable: false };
    case "INVALID_REPOSITORY":
      return { title: "Not a GitHub repository URL", body: body, retryable: false };
    case "FETCH_FAILED":
      return { title: "Could not reach GitHub", body: body, retryable: true };
    default:
      return { title: "Request failed", body: body, retryable: Boolean(err?.retryable) };
  }
}

const short = (sha: string | null | undefined) => (sha ? sha.slice(0, 10) : "—");

function StatusChip({ repo }: { repo: RepositoryView }) {
  const cls = repo.status === "INGESTED" ? "enabled" : repo.status === "FAILED" ? "bad" : "partial";
  const label = repo.status === "INGESTED" && repo.snapshot?.status === "PARTIAL" ? "INGESTED (partial)" : repo.status;
  return <span className={`pill pill-${cls}`}>{label}</span>;
}

function Inventory({ repo }: { repo: RepositoryView }) {
  const [files, setFiles] = useState<FileView[] | null>(null);
  const [only, setOnly] = useState<"manifest" | "all">("manifest");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setFiles(null);
    api
      .repositoryFiles(repo.id, only === "manifest" ? "manifest" : undefined)
      .then(setFiles)
      .catch((e: Error) => setError(e.message));
  }, [repo.id, repo.pinned_sha, only]);

  return (
    <div>
      <div className="row">
        <label>
          <input type="radio" checked={only === "manifest"} onChange={() => setOnly("manifest")} /> Manifests and lockfiles
        </label>
        <label>
          <input type="radio" checked={only === "all"} onChange={() => setOnly("all")} /> All files
        </label>
      </div>
      {error && <p className="error-text">{error}</p>}
      {files && files.length === 0 && <p className="muted small">No {only === "manifest" ? "manifests or lockfiles" : "files"} found.</p>}
      {files && files.length > 0 && (
        <div className="table-wrap"><table data-testid="inventory">
          <thead>
            <tr>
              <th>Path</th>
              <th>Kind</th>
              <th>Role</th>
              <th>Size</th>
              <th>SHA-256</th>
            </tr>
          </thead>
          <tbody>
            {files.slice(0, 300).map((f) => (
              <tr key={f.path}>
                <td className="mono">{f.path}</td>
                <td>{f.kind}{f.reason ? ` (${f.reason})` : ""}</td>
                <td>{f.role ?? ""}{f.tags.length ? ` · ${f.tags.join(", ")}` : ""}</td>
                <td>{f.size ?? ""}</td>
                <td className="mono">{f.sha256 ? f.sha256.slice(0, 12) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
      {files && files.length > 300 && <p className="muted small">Showing the first 300 of {files.length}.</p>}
    </div>
  );
}

function RepoCard({ repo, onRetry }: { repo: RepositoryView; onRetry: (id: string) => void }) {
  const snap = repo.snapshot;
  return (
    <li className="panel" data-testid="repo-card">
      <div className="row">
        <strong className="mono">
          {repo.owner}/{repo.name}
        </strong>
        <StatusChip repo={repo} />
        {repo.requested_ref && <span className="muted small">ref: {repo.requested_ref}</span>}
      </div>
      <p className="small">
        Pinned commit <code title={repo.pinned_sha ?? ""} data-testid="pinned-sha">{short(repo.pinned_sha)}</code>
        {repo.committed_at ? <> · committed {repo.committed_at}</> : null}
        {repo.is_fork ? " · fork" : ""}
        {repo.is_archived ? " · archived" : ""}
        <span className="muted"> — every later step uses this exact commit, never the branch name.</span>
      </p>
      {(repo.status === "PENDING" || repo.status === "INGESTING") && <p className="muted">Fetching the pinned commit in the sandbox…</p>}
      {repo.status === "FAILED" && repo.error && (
        <div className="callout bad" role="alert">
          <strong>Ingestion failed: {String(repo.error.code)}</strong>
          <p>{String(repo.error.message)}</p>
          {repo.error.retryable ? (
            <button className="btn" onClick={() => onRetry(repo.id)}>
              Retry same commit
            </button>
          ) : (
            <p className="muted small">Not retryable.</p>
          )}
        </div>
      )}
      {snap && (
        <div>
          <p className="small" data-testid="snapshot-summary">
            Snapshot: {snap.file_count} entries, {snap.stored_files} stored, {snap.manifests} manifest or lockfile
            {snap.manifests === 1 ? "" : "s"}.
          </p>
          {snap.warnings.map((w) => (
            <p key={w} className="callout warn small">
              {w}
            </p>
          ))}
          {repo.status === "INGESTED" && (
            <p>
              <a href={`#/repo/${repo.id}`} data-testid="inspect-link">
                Inspect dependency worlds →
              </a>
            </p>
          )}
          <details>
            <summary>File inventory</summary>
            <Inventory repo={repo} />
          </details>
        </div>
      )}
    </li>
  );
}

/** Submit a public GitHub repository. Faultline pins it to one commit and records what is in it. Nothing is executed. */
export function RepositoriesPanel({ replay = false }: { replay?: boolean }) {
  const [repos, setRepos] = useState<RepositoryView[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ReturnType<typeof describe> | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(() => {
    api
      .projects()
      .then((ps) => {
        const p = ps[0];
        setProjectId(p?.id ?? null);
        const all = p?.repositories ?? [];                      // the newest project: the same one the analysis dashboard shows
        setRepos(all);
        const active = all.some((r) => r.status === "PENDING" || r.status === "INGESTING");
        if (timer.current) window.clearTimeout(timer.current);
        if (active) timer.current = window.setTimeout(load, 2000);
      })
      .catch((e: unknown) => setProblem(describe(e)));
  }, []);

  useEffect(() => {
    load();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [load]);

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setProblem(null);
    setBusy(true);
    try {
      const pid = projectId ?? (await api.createProject(DEFAULT_PROJECT)).id;
      setProjectId(pid);
      await api.addRepository(pid, url.trim(), ref.trim() || null);
      setUrl("");
      setRef("");
      load();
    } catch (e: unknown) {
      setProblem(describe(e));
    } finally {
      setBusy(false);
    }
  };

  const retry = (id: string) => {
    api
      .retryRepository(id)
      .then(load)
      .catch((e: unknown) => setProblem(describe(e)));
  };

  return (
    <section className="panel" aria-label="Repositories" data-testid="repositories-panel">
      <h2>Repositories</h2>
      <p className="muted small">
        Public GitHub repositories only. Faultline resolves the branch, tag or commit to one immutable SHA, fetches it inside the
        sandbox, and records every file with a hash. Nothing in the repository is executed or installed.
      </p>
      <form onSubmit={submit} className="row" aria-label="Add a repository">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://github.com/owner/repo"
          aria-label="GitHub repository URL"
          required
          size={42}
        />
        <input type="text" value={ref} onChange={(e) => setRef(e.target.value)} placeholder="branch, tag or SHA (optional)" aria-label="Ref" size={26} />
        <button className="btn" type="submit" disabled={replay || busy || !url.trim()} title={replay ? "Recorded results: nothing can be started" : ""}>
          {busy ? "Resolving…" : "Add repository"}
        </button>
      </form>
      {problem && (
        <div className="callout bad" role="alert" data-testid="repo-problem">
          <strong>{problem.title}</strong>
          <p>{problem.body}</p>
          <p className="muted small">{problem.retryable ? "This may work if you try again." : "Retrying will not help until the input changes."}</p>
        </div>
      )}
      {repos.length === 0 ? (
        <p className="muted">No repositories yet.</p>
      ) : (
        <ul className="plain-list">
          {repos.map((r) => (
            <RepoCard key={r.id} repo={r} onRetry={retry} />
          ))}
        </ul>
      )}
    </section>
  );
}
