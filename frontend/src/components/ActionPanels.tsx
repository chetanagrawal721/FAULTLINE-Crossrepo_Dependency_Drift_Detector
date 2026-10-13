import { useEffect, useRef, useState } from "react";
import { api, type Job } from "../api/client";
import { StateMessage } from "./StateMessage";

function useJob(start: () => Promise<Job>) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);
  const poll = (id: string) =>
    api.job(id).then((j) => {
      setJob(j);
      if (j.status === "QUEUED" || j.status === "RUNNING") timer.current = window.setTimeout(() => poll(id), 1500);
    }).catch((e: Error) => setError(e.message));
  const run = () => {
    setError(null);
    setJob(null);
    start().then((j) => { setJob(j); poll(j.job_id); }).catch((e: Error) => setError(e.message));
  };
  return { job, error, run, busy: job?.status === "QUEUED" || job?.status === "RUNNING" };
}

/** Live re-run of a witness: 3 fresh executions per world, never a cached result. */
export function RerunPanel({ witnessId, replay }: { witnessId: string; replay: boolean }) {
  const { job, error, run, busy } = useJob(() => api.rerunWitness(witnessId));
  const r = job?.result as Record<string, unknown> | null | undefined;
  return (
    <section className="panel" data-testid="rerun-panel">
      <h2>Re-run</h2>
      <p className="muted small">Runs the same check again right now, 3 fresh executions in each world. This is live, not a stored result.</p>
      <button className="btn" onClick={run} disabled={busy || replay} title={replay ? "Recorded results: re-run is disabled" : ""}>
        {busy ? "Running…" : "Re-run live (3 + 3)"}
      </button>
      {error && <p className="error-text" role="alert">{error}</p>}
      {job?.status === "FAILED" && <StateMessage view="rerun" kind="failed" detail={String(job.error?.message ?? "the re-run failed")} />}
      {job?.status === "DONE" && r && (
        <p data-testid="rerun-result" className={r.reproduced ? "callout bad" : "callout warn"}>
          <strong>{r.reproduced ? "Reproduced" : "Did not reproduce"}</strong>: reference passed {String(r.reference_passes)}/3, consumer failed {String(r.consumer_failures)}/3,
          fresh executions {String(r.fresh_runs)}/6, {String(r.seconds)} s. {String(r.reason)}
        </p>
      )}
    </section>
  );
}

/** Propose a constraint for the attributed cause, re-resolve, rebuild and re-run. The result is a diff only. */
export function FixPanel({ findingId, replay }: { findingId: string; replay: boolean }) {
  const { job, error, run, busy } = useJob(() => api.remediateFinding(findingId));
  const r = job?.result as Record<string, unknown> | null | undefined;
  return (
    <section className="panel" data-testid="fix-panel">
      <h2>Fix</h2>
      <p className="muted small">
        Proposes a version constraint for the attributed package, re-resolves with the native resolver, rebuilds the world and re-runs the check 3 + 3.
        The result is a diff. Nothing is pushed anywhere.
      </p>
      <button className="btn" onClick={run} disabled={busy || replay} title={replay ? "Recorded results: nothing can be started" : ""}>
        {busy ? "Working…" : "Propose and verify a fix"}
      </button>
      {error && <p className="error-text" role="alert">{error}</p>}
      {job?.status === "FAILED" && <StateMessage view="fix" kind="failed" detail={String(job.error?.message ?? "the remediation failed")} />}
      {job?.status === "DONE" && r && (
        <div data-testid="fix-result">
          <p className={`callout ${r.label === "VERIFIED" ? "" : "warn"}`}>
            <strong data-testid="fix-label">{String(r.label)}</strong> · {String(r.reason)}
          </p>
          {r.constraint ? <p className="small">Constraint: <code>{String(r.constraint)}</code> · fresh runs {String(r.fresh_runs)}</p> : null}
          {r.diff ? <pre className="code" data-testid="fix-diff">{String(r.diff)}</pre> : null}
        </div>
      )}
    </section>
  );
}
