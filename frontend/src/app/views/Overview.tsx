import { ApiError, api, type AnalysisView, type ProjectView } from "../../api/client";
import { useAsync, short } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { Bars, Donut, type Slice } from "../../ui/charts";
import { AppAction, DataTable, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { Loading, ModeStatus, StateBlock, StateNote, VerdictStatus } from "../shared";

type Go = (view: AppView, id?: string | null) => void;

const METRIC_NOTE = "Counted from persisted records";

async function analysisOf(p: ProjectView): Promise<AnalysisView | null> {
  try {
    return await api.projectAnalysis(p.id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export function OverviewView({ go }: { go: Go }) {
  const { project, projects, analysis, analysisError, replay, setProjectId } = useWorkspace();
  const findings = useAsync(() => api.findings(), [analysis?.id]);
  const jobs = useAsync(() => api.jobs(50), [analysis?.id]);
  const recent = useAsync(() => Promise.all(projects.slice(0, 8).map(async (p) => ({ p, a: await analysisOf(p) }))), [projects.map((p) => p.id).join(",")]);

  const f = findings.data ?? [];
  const reviewCount = f.filter((x) => x.verdict === "BREAK_WITNESSED" || x.verdict === "SILENT_DIVERGENCE_WITNESSED").length;
  const inconclusive = f.filter((x) => x.verdict === "INCONCLUSIVE");
  const failedJobs = (jobs.data ?? []).filter((j) => j.status === "FAILED");
  const metrics: [string, string | number, string][] = [
    ["Investigations", projects.length, METRIC_NOTE],
    ["Findings requiring review", findings.data ? reviewCount : "—", findings.data ? "Break or silent divergence witnessed" : "Loading"],
    ["Inconclusive", findings.data ? inconclusive.length : "—", findings.data ? "Not enough evidence either way" : "Loading"],
    ["Jobs needing attention", jobs.data ? failedJobs.length : "—", jobs.data ? "Failed jobs among the latest 50" : "Loading"],
  ];

  const count = (pred: (v: string) => boolean) => f.filter((x) => pred(x.verdict)).length;
  const outcomes: Slice[] = [
    { key: "break", label: "Break witnessed", value: count((v) => v === "BREAK_WITNESSED"), tone: "break" },
    { key: "silent", label: "Silent divergence", value: count((v) => v === "SILENT_DIVERGENCE_WITNESSED"), tone: "silent" },
    { key: "inconclusive", label: "Inconclusive", value: count((v) => v === "INCONCLUSIVE"), tone: "warn" },
    { key: "none", label: "No divergence observed", value: count((v) => v === "NO_DIVERGENCE_OBSERVED"), tone: "ok" },
    { key: "other", label: "Other", value: count((v) => !["BREAK_WITNESSED", "SILENT_DIVERGENCE_WITNESSED", "INCONCLUSIVE", "NO_DIVERGENCE_OBSERVED"].includes(v)), tone: "neutral" },
  ];
  const jobRows = jobs.data ?? [];
  const jobSlices: Slice[] = [
    { key: "DONE", label: "Completed", value: jobRows.filter((j) => j.status === "DONE").length, tone: "ok" },
    { key: "FAILED", label: "Failed", value: jobRows.filter((j) => j.status === "FAILED").length, tone: "break" },
    { key: "ACTIVE", label: "Running or queued", value: jobRows.filter((j) => j.status === "RUNNING" || j.status === "QUEUED").length, tone: "run" },
    { key: "CANCELLED", label: "Cancelled", value: jobRows.filter((j) => j.status === "CANCELLED").length, tone: "neutral" },
  ];

  const fn = (analysis?.funnel ?? {}) as Record<string, unknown>;
  const byState = (fn.cells_by_state ?? {}) as Record<string, number>;
  const repos = project?.repositories ?? [];
  const witnessed = analysis ? analysis.cells.filter((c) => c.verdict === "BREAK_WITNESSED" || c.verdict === "SILENT_DIVERGENCE_WITNESSED").length : 0;
  const verdicts = analysis ? analysis.cells.filter((c) => c.verdict).length : 0;
  const stages: [string, string, number | string, AppView][] = [
    ["submitted", "Submitted", repos.length, "repository"],
    ["pinned", "Pinned", repos.filter((r) => r.pinned_sha).length, "repository"],
    ["inventoried", "Inventoried", repos.filter((r) => r.status === "INGESTED").length, "repository"],
    ["relationships", "Relationships", analysis ? String(fn.relationships_discovered ?? 0) : "—", "relationships"],
    ["worlds", "Worlds built", analysis ? String(fn.cells ?? 0) : "—", "worlds"],
    ["oracles", "Oracles run", analysis ? (byState.ANALYZED ?? 0) + (byState.INCONCLUSIVE ?? 0) : "—", "worlds"],
    ["witness", "Witness", analysis ? witnessed : "—", "findings"],
    ["verdict", "Verdict", analysis ? verdicts : "—", "findings"],
  ];

  const attention: { key: string; tone: "warn" | "neutral"; label: string; text: string; hint: string; view: AppView; id?: string }[] = [
    ...inconclusive.slice(0, 3).map((x) => ({ key: x.finding_id, tone: "warn" as const, label: "Inconclusive", text: `${x.artifact} → ${x.consumer}`, hint: "Open the finding", view: "finding" as AppView, id: x.finding_id })),
    ...(analysis?.failed ?? []).slice(0, 3).map((x, i) => ({ key: `f${i}`, tone: "warn" as const, label: "Could not analyse", text: `${x.consumer}: ${x.reason}`, hint: "Open the world matrix", view: "worlds" as AppView })),
    ...failedJobs.slice(0, 2).map((j) => ({ key: j.job_id, tone: "neutral" as const, label: "Job failed", text: `${j.kind} · ${j.failure_class ?? "unknown"}`, hint: "Open jobs", view: "jobs" as AppView })),
  ];

  return (
    <>
      <div className="metric-strip" data-testid="metrics">
        {metrics.map(([label, value, note]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{note}</small>
          </div>
        ))}
      </div>

      {projects.length === 0 && !recent.loading ? (
        <StateBlock label="NOTHING ANALYSED" title="No investigation exists yet." testid="overview-empty">
          Add two or more public GitHub repositories, or run a committed fixture scenario, to see the funnel, findings and evidence here. This is not a clean result: nothing has been analysed.
          <br />
          <AppAction onClick={() => go("new")} disabled={replay}>
            Start a new analysis
          </AppAction>
        </StateBlock>
      ) : (
        <>
          <div className="work-grid equal" data-testid="charts">
            <Panel title="Outcomes" meta={findings.data ? `${f.length} finding${f.length === 1 ? "" : "s"}` : "Loading"}>
              {findings.data ? <Donut slices={outcomes} centerLabel="findings" onSlice={() => go("findings")} testid="chart-outcomes" /> : <Loading what="findings" />}
            </Panel>
            <Panel title="Jobs by status" meta={jobs.data ? `latest ${jobRows.length}` : "Loading"}>
              {jobs.data ? <Bars slices={jobSlices} onBar={() => go("jobs")} testid="chart-jobs" /> : <Loading what="jobs" />}
            </Panel>
          </div>
          <div className="work-grid two-one">
            <div data-testid="dashboard">
              <Panel title="Analysis funnel" meta={project ? `${project.name} · persisted stages` : "Persisted stages"}>
                <div className={analysis ? "funnel" : "funnel"} data-testid="funnel" {...(analysis ? { "data-analysis-id": analysis.id } : {})}>
                  {stages.map(([key, label, count, view], index) => (
                    <button key={key} onClick={() => go(view)} data-testid={`funnel-${key}`}>
                      <span>0{index + 1}</span>
                      <strong>{label}</strong>
                      <small>{typeof count === "number" ? `${count} recorded` : count === "—" ? "No analysis yet" : `${count} recorded`}</small>
                    </button>
                  ))}
                </div>
                {analysis && (
                  <p className="panel-note" data-testid="analysis" data-analysis-id={analysis.id}>
                    Latest analysis <code>{short(analysis.id, 14)}</code> · {analysis.status}
                    {analysis.outcome ? ` · ${analysis.outcome}` : ""} · {analysis.mode}. {analysis.partial_note ?? ""}
                  </p>
                )}
                {analysisError && <StateNote view="funnel" kind="failed" detail={analysisError} />}
                {!analysis && !analysisError && project && <StateNote view="funnel" kind="empty" detail="No analysis has been run for this project yet. Open New analysis to run one." />}
                {analysis && Number(fn.consumers_discovered ?? 0) === 0 && <StateNote view="funnel" kind="empty" detail="No actionable relationship was found, so there is nothing to analyse." />}
              </Panel>
            </div>
            <Panel title="Needs attention" meta={attention.length ? `${attention.length} item${attention.length === 1 ? "" : "s"}` : "Nothing flagged"}>
              {attention.length === 0 ? (
                <p className="panel-copy">Nothing in the persisted records needs attention. That is a statement about these records, not about the repositories.</p>
              ) : (
                <div className="attention-list">
                  {attention.map((a) => (
                    <button key={a.key} onClick={() => go(a.view, a.id)}>
                      <Status tone={a.tone}>{a.label}</Status>
                      <strong>{a.text}</strong>
                      <small>{a.hint}</small>
                    </button>
                  ))}
                </div>
              )}
            </Panel>
          </div>
          <Panel title="Recent investigations" meta={`${recent.data?.length ?? 0} project${recent.data?.length === 1 ? "" : "s"}`}>
            {recent.loading && !recent.data ? (
              <Loading what="investigations" />
            ) : (
              <DataTable
                columns={["Investigation", "Repositories", "Pinned revisions", "Mode", "Stage", "Result"]}
                rows={(recent.data ?? []).map(({ p, a }) => [
                  <strong>{p.name}</strong>,
                  p.repositories.map((r) => `${r.owner}/${r.name}`).join(", ") || "none yet",
                  <code>{p.repositories.map((r) => short(r.pinned_sha, 7)).join(" → ") || "—"}</code>,
                  <ModeStatus mode={a?.mode ?? p.mode} />,
                  a ? `${a.status}${a.outcome ? ` · ${a.outcome}` : ""}` : "No analysis",
                  a && a.cells.some((c) => c.verdict) ? (
                    <VerdictStatus verdict={a.cells.find((c) => c.verdict === "BREAK_WITNESSED")?.verdict ?? a.cells.find((c) => c.verdict)?.verdict ?? "INCONCLUSIVE"} />
                  ) : (
                    <Status>{a ? "No finding" : "—"}</Status>
                  ),
                ])}
                onRow={(i) => {
                  const row = recent.data?.[i]
                  if (row) setProjectId(row.p.id)
                  go("findings")
                }}
              />
            )}
          </Panel>
        </>
      )}
    </>
  );
}
