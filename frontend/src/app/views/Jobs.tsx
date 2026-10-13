import { useState } from "react";
import { api } from "../../api/client";
import { fmtMs, useAsync, short } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { ErrorNote, Loading, StateBlock, jobTone } from "../shared";

type Go = (view: AppView, id?: string | null) => void;

/** Every background job with its status, how long it ran, how long it waited, and how it failed. Read straight from the job records. */
export function JobsView({ go }: { go: Go }) {
  const { replay } = useWorkspace();
  const [error, setError] = useState<string | null>(null);
  const q = useAsync(() => api.jobs(50), [], { pollMs: 3000, keepPolling: () => true });
  if (q.error && !q.data) return <ErrorNote error={q.error} />;
  if (!q.data) return <Loading what="jobs" />;
  const jobs = q.data;
  if (jobs.length === 0) return <StateBlock label="NO JOBS" title="No jobs have run yet." testid="jobs-empty">This is not a clean result: nothing has been started.</StateBlock>;
  const cancel = (id: string) => api.cancelJob(id).then(q.reload).catch((e: Error) => setError(e.message));
  return (
    <Panel title="Job history" meta={`${jobs.length} most recent · refreshes every 3 seconds`}>
      <div data-testid="jobs">
        <DataTable
          columns={["Job", "Status", "Ran for", "Waited", "Failure class", "Attempts", "Now"]}
          rowAttrs={(i) => ({ "data-testid": `job-${jobs[i].job_id}` })}
          rows={jobs.map((j) => [
            <span>
              <strong>{j.kind}</strong> <code>{short(j.job_id, 16)}</code>
            </span>,
            <span data-testid="job-status">
              <Status tone={jobTone(j.status)}>{j.status}</Status>
            </span>,
            fmtMs(j.duration_ms),
            fmtMs(j.queue_wait_ms),
            <span data-testid="job-failure">{j.failure_class ?? (j.retried_after ? `recovered after ${j.retried_after}` : "none")}</span>,
            `${j.attempts}/${j.max_attempts}`,
            j.status === "RUNNING" || j.status === "QUEUED" ? (
              <span>
                {Math.round(j.progress * 100)}% {j.message ?? ""}{" "}
                <AppAction quiet onClick={() => cancel(j.job_id)} disabled={replay}>
                  Cancel
                </AppAction>
              </span>
            ) : j.error ? (
              String((j.error as { message?: string }).message ?? "")
            ) : (
              ""
            ),
          ])}
          onRow={(i) => go("run", jobs[i].job_id)}
        />
      </div>
      {error && <p className="panel-note" role="alert">{error}</p>}
    </Panel>
  );
}
