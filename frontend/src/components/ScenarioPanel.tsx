import { useEffect, useRef, useState } from "react";
import { api, type Job, type ScenarioInfo } from "../api/client";

type Props = { onFinished: () => void };

/** Fixture scenarios: each runs the real pipeline (worlds, sandbox, witness verification) on committed fixture repos. */
export function ScenarioPanel({ onFinished }: Props) {
  const [scenarios, setScenarios] = useState<ScenarioInfo[] | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    api.scenarios().then(setScenarios).catch((e: Error) => setError(e.message));
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, []);

  const poll = (id: string) => {
    api
      .job(id)
      .then((j) => {
        setJob(j);
        if (j.status === "QUEUED" || j.status === "RUNNING") {
          timer.current = window.setTimeout(() => poll(id), 1500);
        } else {
          setRunning(null);
          if (j.status === "DONE") onFinished();
        }
      })
      .catch((e: Error) => {
        setError(e.message);
        setRunning(null);
      });
  };

  const run = (id: string) => {
    setError(null);
    setRunning(id);
    api
      .runScenario(id)
      .then((j) => {
        setJob(j);
        poll(j.job_id);
      })
      .catch((e: Error) => {
        setError(e.message);
        setRunning(null);
      });
  };

  return (
    <section className="panel" aria-label="Fixture scenarios" data-testid="scenario-panel">
      <h2>Fixture scenarios</h2>
      <p className="muted small">
        Committed fixture repositories, pinned and prepared in advance. Running one executes the real pipeline: worlds are
        built offline, the oracle runs in the sandbox three times per side, and the result is recorded. The mode stays{" "}
        <strong>FIXTURE</strong>; this is not analysis of a live repository.
      </p>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {!scenarios && !error && <p className="muted">Loading scenarios…</p>}
      <ul className="scenarios">
        {scenarios?.map((s) => (
          <li key={s.id}>
            <div>
              <strong>
                {s.id}: {s.title}
              </strong>
              <div className="muted small">
                {s.consumers.map((c) => (
                  <span key={c.repo} className="expect">
                    {c.repo} expects {c.expected_state === "NO_DRIFT" ? "no drift" : (c.expected_verdict ?? c.expected_state).toLowerCase().replaceAll("_", " ")}
                  </span>
                ))}
              </div>
            </div>
            <button type="button" className="btn" disabled={running !== null} onClick={() => run(s.id)} data-testid={`run-${s.id}`}>
              {running === s.id ? "Running…" : "Run"}
            </button>
          </li>
        ))}
      </ul>
      {job && (
        <p className="job" data-testid="job-status">
          Job <code>{job.job_id.slice(-8)}</code>: <strong>{job.status}</strong>
          {job.status === "RUNNING" && ` · ${Math.round(job.progress * 100)}%`}
          {job.message ? ` · ${job.message}` : ""}
          {job.status === "FAILED" && job.error ? ` · ${String(job.error.message ?? job.error.code)}` : ""}
        </p>
      )}
    </section>
  );
}
