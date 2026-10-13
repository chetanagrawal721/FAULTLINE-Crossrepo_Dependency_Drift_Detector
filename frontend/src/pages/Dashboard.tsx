import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, type AnalysisView, type CellView, type Job, type RelationshipView } from "../api/client";
import { VerdictChip } from "../components/VerdictChip";

/** Everything on this page comes from persisted API records. There is no sample data and no client-side verdict logic. */

function Funnel({ a }: { a: AnalysisView }) {
  const f = a.funnel as Record<string, unknown>;
  const row = (label: string, v: unknown) => (
    <li>
      <span className="muted small">{label}</span> <strong data-testid={`funnel-${label}`}>{String(v)}</strong>
    </li>
  );
  return (
    <ul className="chips" data-testid="funnel" aria-label="Analysis funnel">
      {row("relationships found", f.relationships_discovered)}
      {row("actionable", f.relationships_actionable)}
      {row("suspected", f.suspected)}
      {row("consumers discovered", f.consumers_discovered)}
      {row("consumers analysed", f.consumers_analysed)}
      {row("cells", f.cells)}
    </ul>
  );
}

function Relationships({ rels }: { rels: RelationshipView[] }) {
  const actionable = rels.filter((r) => r.actionable);
  const suspected = rels.filter((r) => r.status === "SUSPECTED");
  const card = (r: RelationshipView) => (
    <li key={r.id} className="panel" data-testid="relationship">
      <div className="row">
        <strong className="mono">
          {r.producer} → {r.consumer}
        </strong>
        <span className={`pill ${r.actionable ? "pill-enabled" : "pill-partial"}`}>
          {r.level} · {r.confidence}
        </span>
      </div>
      {r.notes.map((n) => (
        <p key={n} className="muted small">
          {n}
        </p>
      ))}
      <p className="small muted">Why Faultline believes this (file and line at the pinned commit):</p>
      <ul className="small">
        {r.evidence.map((e, i) => (
          <li key={i}>
            <code>
              {e.repository}@{e.commit.slice(0, 10)} {e.file_path}:{e.line}
            </code>{" "}
            — {e.excerpt}
          </li>
        ))}
      </ul>
    </li>
  );
  return (
    <div>
      <h3>Relationships</h3>
      {actionable.length === 0 && <p className="muted">No actionable relationship has evidence on both sides.</p>}
      <ul className="plain-list">{actionable.map(card)}</ul>
      {suspected.length > 0 && (
        <details>
          <summary>Suspected tray ({suspected.length}) — never produces a finding on its own</summary>
          <ul className="plain-list">{suspected.map(card)}</ul>
        </details>
      )}
    </div>
  );
}

function WhyPath({ a }: { a: NonNullable<CellView["attribution"]> }) {
  return (
    <details data-testid="why-path">
      <summary>
        Why-path: {a.minimal.length > 0 ? a.minimal.join(" + ") : "no single cause established"} ({a.status}, {a.sidedness.replace("_", "-")})
      </summary>
      {a.minimal_claim ? (
        <p className="small">
          The cause is <strong>{a.minimal_claim}</strong>: adding it to the reference reproduces the failure, and reverting it in the consumer world removes it.
        </p>
      ) : (
        <p className="small callout warn">Not claimed as minimal: {a.notes.filter((n) => n.startsWith("missing") || n.includes("budget") || n.includes("necessity")).join(" ") || a.status}</p>
      )}
      <p className="small muted">Every world below was forced by Faultline for this search. None of them is an environment a repository actually uses.</p>
      <ul className="small">
        {a.attempts.map((t, i) => (
          <li key={i}>
            <span className="pill">{t.label}</span> {t.direction}: {t.subset.join(", ") || "(none)"} → <strong>{t.outcome}</strong>
            {t.note ? <span className="muted"> · {t.note}</span> : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Matrix({ cells }: { cells: CellView[] }) {
  if (cells.length === 0) return <p className="muted">No cells were built.</p>;
  return (
    <div className="table-wrap">
      <table data-testid="matrix">
        <thead>
          <tr>
            <th>Consumer(s)</th>
            <th>World</th>
            <th>Exact delta vs the reference</th>
            <th>Modules exercised</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {cells.map((c) => (
            <tr key={c.id} data-testid="matrix-row">
              <td className="mono">{c.consumers.join(", ")}</td>
              <td>
                <span className={`pill ${c.state === "NO_DRIFT" ? "pill-enabled" : c.state === "ANALYZED" ? "pill-partial" : "pill-bad"}`}>{c.state}</span>
                <div className="mono small" data-testid="world-hash" title={c.test_world_hash}>
                  {c.test_world_hash.slice(0, 14)}
                </div>
              </td>
              <td>
                {c.delta.length === 0 ? (
                  <span className="muted">none</span>
                ) : (
                  c.delta.map((d) => (
                    <div key={d.name} className="mono small">
                      {d.name}: {d.reference ?? "absent"} → {d.consumer ?? "absent"}
                    </div>
                  ))
                )}
              </td>
              <td className="mono small">{c.imported_modules.join(", ") || "—"}</td>
              <td>
                {c.verdict ? (
                  <>
                    <VerdictChip verdict={c.verdict} />
                    <div className="small">
                      <a href={`#/finding/${c.finding_id}`}>open finding</a>
                    </div>
                    {c.attribution && <WhyPath a={c.attribution} />}
                  </>
                ) : (
                  <span className="muted">no oracle needed</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Dashboard() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [repoCount, setRepoCount] = useState(0);
  const [analysis, setAnalysis] = useState<AnalysisView | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(() => {
    api
      .projects()
      .then(async (ps) => {
        const p = ps[0];
        setProjectId(p?.id ?? null);
        setRepoCount(p?.repositories.filter((r) => r.status === "INGESTED").length ?? 0);
        if (p) {
          try {
            setAnalysis(await api.projectAnalysis(p.id));
          } catch (e) {
            if (!(e instanceof ApiError && e.status === 404)) throw e;
            setAnalysis(null);
          }
        }
      })
      .catch((e: Error) => setError(e.message));
  }, []);

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
        if (j.status === "QUEUED" || j.status === "RUNNING") timer.current = window.setTimeout(() => poll(id), 3000);
        else load();
      })
      .catch((e: Error) => setError(e.message));

  const run = () => {
    if (!projectId) return;
    setError(null);
    api
      .analyzeProject(projectId)
      .then((j) => {
        setJob(j);
        poll(j.job_id);
      })
      .catch((e: Error) => setError(e.message));
  };

  const running = job?.status === "QUEUED" || job?.status === "RUNNING";
  return (
    <section className="panel" aria-label="Cross-repository analysis" data-testid="dashboard">
      <h2>Cross-repository analysis</h2>
      <p className="muted small">
        Relates the ingested repositories by evidence, builds the dependency world each consumer gives the shared code, runs the checks in the
        sandbox, and reports only what could be reproduced. Mode: <strong>LIVE</strong> (real pinned repositories).
      </p>
      <div className="row">
        <button className="btn" onClick={run} disabled={running || repoCount < 2} title={repoCount < 2 ? "Add and ingest at least two repositories" : ""}>
          {running ? "Analysing…" : "Run analysis"}
        </button>
        {repoCount < 2 && <span className="muted small">needs at least 2 ingested repositories ({repoCount} so far)</span>}
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
      {!analysis && !running && <p className="muted">No analysis yet.</p>}
      {analysis && (
        <div data-testid="analysis" data-analysis-id={analysis.id}>
          <Funnel a={analysis} />
          {analysis.failed.length > 0 && (
            <div className="callout warn" data-testid="failed-consumers">
              <strong>Discovered but not analysed</strong>
              {analysis.failed.map((f, i) => (
                <p key={i} className="small">
                  {f.consumer} ({f.side} world): {f.reason}. {f.text}
                </p>
              ))}
            </div>
          )}
          <Relationships rels={analysis.relationships} />
          <h3>World matrix</h3>
          <Matrix cells={analysis.cells} />
        </div>
      )}
    </section>
  );
}
