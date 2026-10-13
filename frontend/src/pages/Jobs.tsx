import { useEffect, useState } from "react";
import { api, type Job } from "../api/client";
import { StateMessage } from "../components/StateMessage";

const fmt = (ms: number | null | undefined) =>
  ms === null || ms === undefined ? "n/a" : ms < 1000 ? `${ms} ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.floor(ms / 60000)} min ${Math.round((ms % 60000) / 1000)} s`;

/** Every background job with its status, how long it ran, how long it waited, and how it failed. Read straight from the job records. */
export function Jobs() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .jobs()
        .then((j) => alive && setJobs(j))
        .catch((e: Error) => alive && setError(e.message));
    load();
    const t = window.setInterval(load, 3000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);

  if (error) return <StateMessage view="jobs" kind="failed" detail={error} />;
  if (!jobs) return <p className="muted">Loading…</p>;
  if (jobs.length === 0) return <StateMessage view="jobs" kind="empty" detail="No jobs have run yet." />;

  return (
    <section className="panel" aria-label="Jobs" data-testid="jobs">
      <h2>Jobs</h2>
      <p className="muted">Status, run time, queue wait and failure class for every background job. Refreshes every 3 seconds.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Status</th>
              <th>Ran for</th>
              <th>Waited</th>
              <th>Failure class</th>
              <th>Attempts</th>
              <th>Now</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.job_id} data-testid={`job-${j.job_id}`}>
                <td>
                  <strong>{j.kind}</strong> <span className="muted">{j.job_id.slice(0, 16)}</span>
                </td>
                <td data-testid="job-status">{j.status}</td>
                <td>{fmt(j.duration_ms)}</td>
                <td>{fmt(j.queue_wait_ms)}</td>
                <td data-testid="job-failure">{j.failure_class ?? (j.retried_after ? `recovered after ${j.retried_after}` : "none")}</td>
                <td>
                  {j.attempts}/{j.max_attempts}
                </td>
                <td className="muted">{j.status === "RUNNING" ? `${Math.round(j.progress * 100)}% ${j.message ?? ""}` : j.error ? String((j.error as { message?: string }).message ?? "") : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
