import { useRef, useState } from "react";
import { api, type FindingDetail, type Job } from "../../api/client";
import { useAsync, short, words } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { EmptyInline, ErrorNote, Loading, ModeStatus, StateBlock, StateNote, VerdictStatus } from "../shared";

type Go = (view: AppView, id?: string | null) => void;

/** Start a job and follow it until it settles. */
function useJobAction(start: () => Promise<Job>) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const poll = (id: string) =>
    api
      .job(id)
      .then((j) => {
        setJob(j);
        if (j.status === "QUEUED" || j.status === "RUNNING") timer.current = window.setTimeout(() => poll(id), 1500);
      })
      .catch((e: Error) => setError(e.message));
  const run = () => {
    setError(null);
    setJob(null);
    start()
      .then((j) => {
        setJob(j);
        poll(j.job_id);
      })
      .catch((e: Error) => setError(e.message));
  };
  return { job, error, run, busy: job?.status === "QUEUED" || job?.status === "RUNNING" };
}

/** Live re-run of a witness: 3 fresh executions per world, never a cached result. */
function RerunPanel({ witnessId, replay }: { witnessId: string; replay: boolean }) {
  const { job, error, run, busy } = useJobAction(() => api.rerunWitness(witnessId));
  const r = job?.result as Record<string, unknown> | null | undefined;
  return (
    <Panel title="Re-run" meta="Live, 3 + 3 fresh executions">
      <div data-testid="rerun-panel">
        <p className="panel-copy">Runs the same check again right now, three fresh executions in each world. This is live, not a stored result.</p>
        <AppAction onClick={run} disabled={busy || replay}>
          {busy ? "Running…" : "Re-run live (3 + 3)"}
        </AppAction>
        {replay && <p className="panel-note">Recorded results: re-run is disabled.</p>}
        {error && <p className="panel-note" role="alert">{error}</p>}
        {job?.status === "FAILED" && <p className="panel-note" role="alert">The re-run failed: {String(job.error?.message ?? job.error?.code ?? "unknown error")}</p>}
        {job?.status === "DONE" && r && (
          <p className="panel-note" data-testid="rerun-result">
            <Status tone={r.reproduced ? "copper" : "warn"}>{r.reproduced ? "Reproduced" : "Did not reproduce"}</Status> Reference passed {String(r.reference_passes)}/3, consumer failed {String(r.consumer_failures)}/3, fresh executions {String(r.fresh_runs)}/6, {String(r.seconds)} s. {String(r.reason)}
          </p>
        )}
      </div>
    </Panel>
  );
}

/** Propose a constraint for the attributed cause, re-resolve, rebuild and re-run. The result is a diff. */
function FixPanel({ findingId, replay }: { findingId: string; replay: boolean }) {
  const { job, error, run, busy } = useJobAction(() => api.remediateFinding(findingId));
  const r = job?.result as Record<string, unknown> | null | undefined;
  return (
    <Panel title="Fix" meta="Diff only · nothing is pushed">
      <div data-testid="fix-panel">
        <p className="panel-copy">Proposes a version constraint for the attributed package, re-resolves with the native resolver, rebuilds the world and re-runs the check 3 + 3. The result is a diff.</p>
        <AppAction onClick={run} disabled={busy || replay}>
          {busy ? "Working…" : "Propose and verify a fix"}
        </AppAction>
        {error && <p className="panel-note" role="alert">{error}</p>}
        {job?.status === "FAILED" && <p className="panel-note" role="alert">The remediation failed: {String(job.error?.message ?? job.error?.code ?? "unknown error")}</p>}
        {job?.status === "DONE" && r && (
          <div data-testid="fix-result">
            <p className="panel-note">
              <Status tone={r.label === "VERIFIED" ? "good" : "warn"}><span data-testid="fix-label">{String(r.label)}</span></Status> {String(r.reason)}
            </p>
            {r.constraint ? <p className="panel-note">Constraint <code>{String(r.constraint)}</code> · fresh runs {String(r.fresh_runs)}</p> : null}
            {r.diff ? <pre className="code-block" data-testid="fix-diff">{String(r.diff)}</pre> : null}
          </div>
        )}
      </div>
    </Panel>
  );
}

function WhyPath({ id }: { id: string }) {
  const w = useAsync(() => api.whyPath(id), [id]);
  if (w.error) return <StateNote view="why-path" kind="failed" detail={w.error} />;
  if (!w.data) return <Loading what="the why-path" />;
  return (
    <Panel title="Why-path" meta="Each link says whether it was analysed">
      <div className="pipeline" data-testid="why-path-panel">
        {w.data.steps.map((s, i) => (
          <details key={s.kind} data-testid={`why-step-${s.kind}`} data-status={s.status} open={s.kind === "verdict" || s.kind === "attribution"}>
            <summary>
              <span>{i + 1}</span>
              <strong>{s.title}</strong>
              <Status tone={s.status === "analysed" ? "good" : "neutral"}>{s.status === "analysed" ? "Analysed" : "Not analysed"}</Status>
            </summary>
            <p>{s.detail}</p>
            {s.items.length > 0 && (
              <ul className="why-items">
                {s.items.map((it, k) => (
                  <li key={k}>
                    <code>{it}</code>
                  </li>
                ))}
              </ul>
            )}
          </details>
        ))}
      </div>
    </Panel>
  );
}

function Repeatability({ d }: { d: FindingDetail }) {
  const w = d.witnesses[0];
  return (
    <Panel title="Repeatability" meta={`${d.fresh_runs} of 6 fresh executions`}>
      <div data-testid="repeatability">
        <p className="panel-copy">
          Reference passed <strong>{w ? w.ref_pass : d.runs.filter((r) => r.side === "ref").length}/3</strong> · consumer failed <strong>{w ? w.test_fail : 0}/3</strong> · fresh executions <strong>{d.fresh_runs}/6</strong>
          {d.reused_runs > 0 ? ` · reused results ${d.reused_runs} (not counted)` : ""}
        </p>
        <DataTable
          testid="run-rows"
          columns={["World", "Run", "Provenance", "Result", "ms", "Run id"]}
          rows={d.runs.map((r) => [
            r.side === "ref" ? "reference" : "consumer",
            r.run_index,
            r.provenance === "FRESH_EXECUTION" ? "fresh execution" : "reused result",
            <Status tone={r.failure_class === "NONE" ? "good" : "warn"}>{r.failure_class === "NONE" ? "pass" : words(r.failure_class).toLowerCase()}</Status>,
            r.duration_ms,
            <code>{r.run_id.slice(-10)}</code>,
          ])}
        />
      </div>
    </Panel>
  );
}

export function FindingView({ go, id }: { go: Go; id: string | null }) {
  const { replay } = useWorkspace();
  const q = useAsync(() => (id ? api.finding(id) : Promise.resolve(null)), [id]);
  if (!id) return <EmptyInline title="No finding is selected">Open one from the findings list.</EmptyInline>;
  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <Loading what="the finding" />;
  const d = q.data;
  const w = d.witnesses[0];
  const attributed = d.verdict === "BREAK_WITNESSED" && d.mode !== "FIXTURE";
  return (
    <div data-testid="finding-detail">
      <div className="verdict-summary">
        <div>
          <VerdictStatus verdict={d.verdict} /> <ModeStatus mode={d.mode} />
          <h2>
            Scoped verdict · {d.artifact} → {d.consumer}
          </h2>
          <p data-testid="headline">{d.headline}</p>
        </div>
        <div className="app-actions">
          <AppAction quiet onClick={() => go("worlds")}>
            World matrix
          </AppAction>
          {w && <AppAction onClick={() => go("witness", d.finding_id)}>Open witness</AppAction>}
        </div>
      </div>

      {d.verdict === "INCONCLUSIVE" && (
        <StateBlock tone="warn" label="INCONCLUSIVE" title="This is not a pass." testid="inconclusive-note">
          The evidence is not sufficient for a conclusion either way. The reasons are listed under the scope of this result; an infrastructure, setup or timeout problem is never counted as a witness.
        </StateBlock>
      )}

      <Panel title="What the evidence establishes" meta={`Finding ${short(d.finding_id.replace(/^fnd_/, ""), 12)}`}>
        <div className="finding-summary-grid">
          <div>
            <span>What was observed</span>
            <p>{d.headline}</p>
          </div>
          <div>
            <span>What remains uncertain</span>
            <p>{d.scope.reasons.length ? d.scope.reasons.join(" · ") : d.scope.not_checked.slice(0, 2).join(" · ")}</p>
          </div>
          <div>
            <span>Scope</span>
            <p>
              <code>
                {short(d.reference.world_hash, 12)} → {short(d.consumer_world.world_hash, 12)}
              </code>
              <br />
              Policy {d.scope.policy} · {d.fresh_runs} fresh run(s)
            </p>
          </div>
        </div>
      </Panel>

      <WhyPath id={id} />

      <div className="work-grid equal" data-testid="worlds">
        <Panel title="Reference world" meta="The artifact's own dependencies">
          <dl className="key-values">
            <div>
              <dt>World hash</dt>
              <dd>
                <code>{short(d.reference.world_hash, 16)}</code>
              </dd>
            </div>
            <div>
              <dt>Runtime</dt>
              <dd>{d.reference.runtime}</dd>
            </div>
            <div>
              <dt>Packages</dt>
              <dd>{d.reference.package_count}</dd>
            </div>
          </dl>
        </Panel>
        <Panel title="Consumer world" meta={`What ${d.consumer} resolves`}>
          <dl className="key-values">
            <div>
              <dt>World hash</dt>
              <dd>
                <code>{short(d.consumer_world.world_hash, 16)}</code>
              </dd>
            </div>
            <div>
              <dt>Runtime</dt>
              <dd>{d.consumer_world.runtime}</dd>
            </div>
            <div>
              <dt>Packages</dt>
              <dd>{d.consumer_world.package_count}</dd>
            </div>
          </dl>
        </Panel>
      </div>

      <Panel title="Dependency delta" meta="Candidate causes only · not an attribution">
        {d.delta.length === 0 ? (
          <EmptyInline title="No package differs between the two worlds" />
        ) : (
          <DataTable testid="delta" columns={["Package", "Reference", "Consumer"]} rows={d.delta.map((x) => [<strong>{x.name}</strong>, <code>{x.reference ?? "absent"}</code>, <code>{x.consumer ?? "absent"}</code>])} />
        )}
      </Panel>

      <Repeatability d={d} />

      <div className="work-grid equal">
        <Panel title="Scope of this result" meta={`Verdict policy ${d.scope.policy}`}>
          <div data-testid="scope">
            <dl className="key-values">
              <div>
                <dt>Exercised</dt>
                <dd>{d.scope.exercised.length ? d.scope.exercised.map((e) => <code key={e} className="mod">{e} </code>) : "nothing"}</dd>
              </div>
              {d.scope.not_applicable.length > 0 && (
                <div>
                  <dt>Not applicable in this world</dt>
                  <dd>{d.scope.not_applicable.map((e) => <code key={e}>{e} </code>)}</dd>
                </div>
              )}
            </dl>
            <p className="panel-note"><strong>Not checked</strong></p>
            <ul className="why-items">
              {d.scope.not_checked.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
            {d.scope.reasons.length > 0 && (
              <>
                <p className="panel-note"><strong>Why some interactions were not decided</strong></p>
                <ul className="why-items">
                  {d.scope.reasons.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </Panel>
        <div>
          {w && <RerunPanel witnessId={w.witness_id} replay={replay} />}
          {attributed && <FixPanel findingId={d.finding_id} replay={replay} />}
        </div>
      </div>
    </div>
  );
}
