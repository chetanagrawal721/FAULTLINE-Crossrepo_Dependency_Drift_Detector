import { useEffect, useState } from "react";
import { api, type Job } from "../../api/client";
import { fmtMs, useAsync, short } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { Loading, ModeStatus, StateBlock, jobTone } from "../shared";

type Go = (view: AppView, id?: string | null) => void;
type StageState = "Complete" | "Attention" | "In progress" | "Not started" | "Not applicable" | "Not recorded";

const ANALYSIS_KINDS = new Set(["live_analysis", "analyze_repository", "ingest_repository", "fixture_scenario"]);
const running = (j: Job | null) => j?.status === "QUEUED" || j?.status === "RUNNING";

export function RunView({ go, jobId }: { go: Go; jobId: string | null }) {
  const { project, analysis, replay, reload } = useWorkspace();
  const [cancelError, setCancelError] = useState<string | null>(null);
  const latest = useAsync(async () => (jobId ? null : (await api.jobs(20)).find((j) => ANALYSIS_KINDS.has(j.kind)) ?? null), [jobId]);
  const id = jobId ?? latest.data?.job_id ?? null;
  const job = useAsync(() => (id ? api.job(id) : Promise.resolve(null)), [id], { pollMs: 1500, keepPolling: (j) => running(j) });
  const finished = job.data && !running(job.data);
  useEffect(() => {
    if (finished) reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished, job.data?.job_id]);

  if ((latest.loading && !jobId) || (id && job.loading && !job.data)) return <Loading what="the run" />;
  if (!id || !job.data) {
    return (
      <StateBlock label="NO RUN RECORDED" title="No analysis run has been recorded yet." testid="run-empty">
        Start one from New analysis. Nothing is shown here until a job exists, so this is not a clean result.
        <br />
        <AppAction onClick={() => go("new")}>New analysis</AppAction>
      </StateBlock>
    );
  }
  const j = job.data;
  const repos = project?.repositories ?? [];
  const fn = (analysis?.funnel ?? {}) as Record<string, number>;
  const cells = analysis?.cells ?? [];
  const failed = analysis?.failed ?? [];
  const ranOracle = cells.filter((c) => c.oracle_plan.some((s) => s.status === "RAN"));
  const witnessed = cells.filter((c) => c.verdict === "BREAK_WITNESSED" || c.verdict === "SILENT_DIVERGENCE_WITNESSED");
  const attributed = cells.filter((c) => c.attribution);
  const withVerdict = cells.filter((c) => c.verdict);

  const stages: [string, StageState, string][] = [
    ["Request accepted", "Complete", `Job ${short(j.job_id, 16)} was persisted at ${new Date(j.created_at).toLocaleString()}.`],
    [
      "Repository fetch and pinning",
      repos.length === 0 ? "Not recorded" : repos.some((r) => r.status === "FAILED") ? "Attention" : repos.every((r) => r.status === "INGESTED") ? "Complete" : "In progress",
      repos.length === 0 ? "This job is not attached to a project with repositories." : repos.map((r) => `${r.owner}/${r.name} ${short(r.pinned_sha, 7)} ${r.status}`).join(" · "),
    ],
    ["Inventory", repos.some((r) => r.snapshot) ? "Complete" : "Not recorded", repos.filter((r) => r.snapshot).map((r) => `${r.name}: ${r.snapshot?.manifests} manifest or lockfile`).join(" · ") || "No snapshot is recorded."],
    ["Parse and resolve", analysis ? (failed.some((x) => x.reason.includes("resol") || x.reason.includes("manifest")) ? "Attention" : "Complete") : "Not recorded", analysis ? "Recorded per consumer in the world matrix, including projects that could not be resolved." : "No analysis exists yet."],
    ["Relationship evaluation", analysis ? "Complete" : "Not recorded", analysis ? `${fn.relationships_discovered ?? 0} relationship(s) found, ${fn.relationships_actionable ?? 0} actionable, ${fn.suspected ?? 0} suspected.` : "No analysis exists yet."],
    ["World construction", analysis ? (failed.length > 0 ? "Attention" : "Complete") : "Not recorded", analysis ? `${fn.cells ?? 0} cell(s) built${failed.length ? `; ${failed.length} consumer(s) could not be analysed (see the world matrix)` : ""}.` : "No analysis exists yet."],
    ["Oracle planning and execution", analysis ? (ranOracle.length ? "Complete" : cells.length ? "Not applicable" : "Not started") : "Not recorded", analysis ? `${ranOracle.length} of ${cells.length} cell(s) ran an oracle.` : "No analysis exists yet."],
    ["Witness evaluation", analysis ? (witnessed.length ? "Complete" : ranOracle.length ? "Not applicable" : "Not started") : "Not recorded", analysis ? `${witnessed.length} witness(es) under the 3 + 3 rule.` : "No analysis exists yet."],
    ["Attribution", analysis ? (attributed.length ? "Complete" : "Not applicable") : "Not recorded", analysis ? (attributed.length ? "Two-sided search over the dependency delta." : "Only witnessed breaks are attributed.") : "No analysis exists yet."],
    ["Verdict and evidence persistence", analysis ? (withVerdict.length ? "Complete" : "Not started") : "Not recorded", analysis ? `${withVerdict.length} finding(s) persisted.` : "No analysis exists yet."],
  ];
  const attention = stages.findIndex(([, s]) => s === "Attention");
  const openIndex = running(j) ? stages.findIndex(([, s]) => s === "In progress" || s === "Not started") : attention;

  const cancel = () => {
    setCancelError(null);
    api.cancelJob(j.job_id).then(job.reload).catch((e: Error) => setCancelError(e.message));
  };

  return (
    <div className="work-grid two-one" data-testid="run-view">
      <Panel title="Pipeline timeline" meta={running(j) ? "Updating while the job runs" : "Persisted state"}>
        <div className="pipeline">
          {stages.map(([title, state, detail], index) => (
            <details key={title} open={index === openIndex}>
              <summary>
                <span>{index + 1}</span>
                <strong>{title}</strong>
                <Status tone={state === "Attention" ? "warn" : state === "Complete" ? "good" : state === "In progress" ? "copper" : "neutral"}>{state}</Status>
              </summary>
              <p>{detail}</p>
            </details>
          ))}
        </div>
      </Panel>
      <div>
        <Panel title="Run context" meta={short(j.job_id, 18)}>
          <dl className="key-values">
            <div>
              <dt>Job</dt>
              <dd>
                <Status tone={jobTone(j.status)}>{j.status}</Status> <span data-testid="job-status-text">{j.kind}</span>
              </dd>
            </div>
            <div>
              <dt>Mode</dt>
              <dd>{project ? <ModeStatus mode={project.mode} /> : "Unknown"}</dd>
            </div>
            <div>
              <dt>Ran for</dt>
              <dd>{fmtMs(j.duration_ms)}</dd>
            </div>
            <div>
              <dt>Attempts</dt>
              <dd>
                {j.attempts} of {j.max_attempts}
                {j.retried_after ? ` · recovered after ${j.retried_after}` : ""}
              </dd>
            </div>
            <div>
              <dt>Failure class</dt>
              <dd>{j.failure_class ?? "none"}</dd>
            </div>
            {running(j) && (
              <div>
                <dt>Worker reports</dt>
                <dd>
                  {Math.round(j.progress * 100)}% · {j.message ?? "working"}
                </dd>
              </div>
            )}
            {repos.map((r, i) => (
              <div key={r.id}>
                <dt>{i === 0 ? "Pinned" : ""}</dt>
                <dd>
                  <code>{short(r.pinned_sha, 7)}</code> {r.name}
                </dd>
              </div>
            ))}
          </dl>
          {running(j) && (
            <AppAction quiet onClick={cancel} disabled={replay}>
              Cancel job
            </AppAction>
          )}
          {cancelError && <p className="panel-note">{cancelError}</p>}
        </Panel>
        {j.status === "FAILED" && (
          <Panel title="The job failed" meta={j.failure_class ?? "failure"}>
            <p className="panel-copy">{String(j.error?.message ?? j.error?.code ?? "No error text was recorded.")}</p>
          </Panel>
        )}
        {j.status === "CANCELLED" && analysis?.outcome && (
          <Panel title="Cancelled with partial evidence" meta={analysis.outcome}>
            <p className="panel-copy">{analysis.partial_note ?? "The analysis was closed early; the evidence recorded so far is kept and labelled."}</p>
          </Panel>
        )}
        {j.status === "DONE" && analysis && (
          <Panel title="Result available" meta={analysis.mode}>
            <p className="panel-copy">
              {withVerdict.length} finding(s) were recorded. Each states what was exercised and what was not checked.
            </p>
            <AppAction onClick={() => go("findings")}>Open findings</AppAction>{" "}
            <AppAction quiet onClick={() => go("worlds")}>
              World matrix
            </AppAction>
          </Panel>
        )}
      </div>
    </div>
  );
}
