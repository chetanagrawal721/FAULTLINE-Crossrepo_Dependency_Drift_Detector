import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, type AnalysisView, type CellView, type Job, type RelationshipView } from "../api/client";
import { ModeBadge } from "../components/ModeBadge";
import { StateMessage } from "../components/StateMessage";
import { VerdictChip } from "../components/VerdictChip";

/** Everything on this page comes from persisted API records. There is no sample data and no client-side verdict logic. */

const UNSUPPORTED_REASONS = new Set(["needs_build", "non_registry_source", "private_index_without_lock", "setup_py_not_executed", "lock_unsupported", "private_packages"]);

function Funnel({ a }: { a: AnalysisView }) {
  const f = a.funnel as Record<string, unknown>;
  const byState = (f.cells_by_state ?? {}) as Record<string, number>;
  const unsupported = a.failed.filter((x) => UNSUPPORTED_REASONS.has(x.reason)).length;
  const row = (label: string, v: unknown) => (
    <li key={label}>
      <span className="muted small">{label}</span> <strong data-testid={`funnel-${label}`}>{String(v)}</strong>
    </li>
  );
  return (
    <div>
      <ul className="chips" data-testid="funnel" aria-label="Analysis funnel">
        {row("relationships found", f.relationships_discovered)}
        {row("actionable", f.relationships_actionable)}
        {row("suspected", f.suspected)}
        {row("consumers discovered", f.consumers_discovered)}
        {row("consumers analysed", f.consumers_analysed)}
        {row("cells", f.cells)}
        {row("no drift", byState.NO_DRIFT ?? 0)}
        {row("analysed cells", byState.ANALYZED ?? 0)}
        {row("inconclusive cells", byState.INCONCLUSIVE ?? 0)}
        {row("not applicable cells", byState.NOT_APPLICABLE ?? 0)}
        {row("unsupported consumers", unsupported)}
        {row("failed consumers", a.failed.length - unsupported)}
      </ul>
      {Number(f.consumers_discovered) === 0 && <StateMessage view="funnel" kind="empty" detail="No actionable relationship was found, so there is nothing to analyse." />}
    </div>
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


function Matrix({ cells, a }: { cells: CellView[]; a: AnalysisView }) {
  const f = a.funnel as Record<string, number>;
  if (cells.length === 0 && a.failed.length === 0) return <StateMessage view="matrix" kind="empty" detail="No consumer produced a cell." />;
  return (
    <div>
      <p className="small" data-testid="coverage">
        Coverage: <strong>{String(f.consumers_analysed)}</strong> of <strong>{String(f.consumers_discovered)}</strong> discovered consumers analysed
        {a.failed.length > 0 ? ` · ${a.failed.length} could not be analysed (listed below, not hidden)` : ""}. This is a count, not a compatibility score.
      </p>
      <div className="table-wrap">
        <table data-testid="matrix">
          <thead>
            <tr>
              <th>Consumer(s)</th>
              <th>Cell</th>
              <th>Runtime · platform</th>
              <th>Importer visibility</th>
              <th>Exact delta vs the reference</th>
              <th>Modules exercised</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {cells.map((c) => (
              <tr key={c.id} data-testid="matrix-row" data-cell-state={c.state}>
                <td className="mono">{c.consumers.join(", ")}</td>
                <td>
                  <span className={`pill ${c.state === "NO_DRIFT" ? "pill-enabled" : c.state === "ANALYZED" ? "pill-partial" : "pill-bad"}`}>{c.state}</span>
                  <div className="mono small" data-testid="world-hash" title={c.test_world_hash}>
                    {c.test_world_hash.slice(0, 14)}
                  </div>
                </td>
                <td className="small" data-testid="runtime">
                  {c.runtime}
                  <br />
                  {c.platform}
                </td>
                <td className="small">{c.visibility}</td>
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
                      {c.verdict === "INCONCLUSIVE" && <StateMessage view="matrix" kind="inconclusive" />}
                      <div className="small">
                        <a href={`#/finding/${c.finding_id}`}>open finding</a>
                      </div>
                      {c.attribution && <WhyPath a={c.attribution} />}
                    </>
                  ) : c.state === "NO_DRIFT" ? (
                    <span className="muted">no drift: nothing to run</span>
                  ) : c.state === "NOT_APPLICABLE" ? (
                    <StateMessage view="matrix" kind="not-applicable" />
                  ) : (
                    <span className="muted">no oracle result</span>
                  )}
                </td>
              </tr>
            ))}
            {a.failed.map((x, i) => {
              const unsupported = UNSUPPORTED_REASONS.has(x.reason);
              return (
                <tr key={`f${i}`} data-testid="matrix-failed-row" data-cell-state={unsupported ? "UNSUPPORTED" : "FAILED"}>
                  <td className="mono">{x.consumer}</td>
                  <td>
                    <span className={`pill ${unsupported ? "pill-partial" : "pill-bad"}`}>{unsupported ? "UNSUPPORTED" : "FAILED"}</span>
                  </td>
                  <td colSpan={5}>
                    <StateMessage view="matrix" kind={unsupported ? "unsupported" : "failed"} detail={`${x.side} world: ${x.reason}. ${x.text}`} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Dashboard({ replay = false }: { replay?: boolean }) {
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
        sandbox, and reports only what could be reproduced. {analysis ? <ModeBadge mode={analysis.mode as "LIVE" | "FIXTURE" | "REPLAY"} /> : null}
      </p>
      <div className="row">
        <button className="btn" onClick={run} disabled={replay || running || repoCount < 2} title={replay ? "Recorded results: re-run is disabled" : repoCount < 2 ? "Add and ingest at least two repositories" : ""}>
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
      {!analysis && !running && !error && <StateMessage view="funnel" kind="empty" detail="No analysis has been run for this project." />}
      {(error || job?.status === "FAILED") && <StateMessage view="funnel" kind="failed" detail={error ?? String(job?.error?.message ?? "the analysis job failed")} />}
      {analysis && (
        <div data-testid="analysis" data-analysis-id={analysis.id}>
          <Funnel a={analysis} />
          <Relationships rels={analysis.relationships} />
          <h3>World matrix</h3>
          <Matrix cells={analysis.cells} a={analysis} />
        </div>
      )}
    </section>
  );
}
