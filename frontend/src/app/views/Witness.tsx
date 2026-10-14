import { useState } from "react";
import { api, type FindingDetail, type RunView } from "../../api/client";
import { useAsync, words } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { EmptyInline, ErrorNote, Loading, StateBlock, VerdictStatus } from "../shared";

type Go = (view: AppView, id?: string | null) => void;

const failing = (r: RunView) => r.entries.find((e) => !e.passed && !e.skipped && !e.not_applicable);

function RunCard({ title, run, expectPass }: { title: string; run: RunView | undefined; expectPass: boolean }) {
  const bad = run && failing(run);
  const fresh = run?.provenance === "FRESH_EXECUTION";
  return (
    <article data-testid="run-card" data-side={expectPass ? "ref" : "test"}>
      <div>
        <span>{title}</span>
        {run ? <Status tone={run.failure_class === "NONE" ? "good" : "warn"}>{run.failure_class === "NONE" ? "PASS" : words(run.failure_class)}</Status> : <Status tone="neutral">NOT RECORDED</Status>}
      </div>
      <strong>{expectPass ? "Expected passing behavior" : "Observed failing behavior"}</strong>
      <dl>
        <div>
          <dt>Fresh execution</dt>
          <dd>{run ? (fresh ? "Yes" : "No · reused result, not counted") : "No"}</dd>
        </div>
        <div>
          <dt>Run ID</dt>
          <dd>{run ? <code>{run.run_id.slice(-12)}</code> : "Not recorded"}</dd>
        </div>
        <div>
          <dt>Outcome</dt>
          <dd>{run ? (run.failure_class === "NONE" ? "Passed" : words(run.failure_class).toLowerCase()) : "Unavailable"}</dd>
        </div>
        <div>
          <dt>Signature</dt>
          <dd>{bad ? `${bad.exc_type}: ${(bad.message ?? "").slice(0, 120)}` : run ? "None (no failure)" : "Unavailable"}</dd>
        </div>
      </dl>
    </article>
  );
}

function Board({ d, go }: { d: FindingDetail; go: Go }) {
  const [pick, setPick] = useState(0);
  const w = d.witnesses[Math.min(pick, d.witnesses.length - 1)];
  // a witness is judged on its own six runs: a finding can have several witnesses (one per oracle), and their runs must not be added together
  const mine = w ? d.runs.filter((r) => w.ref_run_ids.includes(r.run_id) || w.test_run_ids.includes(r.run_id)) : d.runs;
  const slot = (side: string, i: number) => mine.filter((r) => r.side === side).sort((a, b) => a.run_index - b.run_index)[i];
  const refFresh = mine.filter((r) => r.side === "ref" && r.provenance === "FRESH_EXECUTION" && r.failure_class === "NONE").length;
  const testFresh = mine.filter((r) => r.side === "test" && r.provenance === "FRESH_EXECUTION" && r.failure_class !== "NONE").length;
  const satisfied = Boolean(w) && refFresh >= 3 && testFresh >= 3;
  const bad = mine.find((r) => r.side === "test" && failing(r));
  const fresh = mine.filter((r) => r.provenance === "FRESH_EXECUTION").length;
  return (
    <>
      {d.witnesses.length > 1 && (
        <div className="app-tabs" role="tablist" aria-label="Witnesses of this finding" data-testid="witness-tabs">
          {d.witnesses.map((x, i) => (
            <button key={x.witness_id} role="tab" aria-selected={i === pick} className={i === pick ? "active" : ""} onClick={() => setPick(i)} title={x.entry_point}>
              {x.oracle.replace("o_", "O-")}: {x.entry_point.length > 34 ? `${x.entry_point.slice(0, 33)}…` : x.entry_point}
            </button>
          ))}
        </div>
      )}
      <div className="witness-rule" data-testid="witness-rule">
        {[
          ["Reference", `${refFresh} / 3 fresh passes`],
          ["Consumer", `${testFresh} / 3 fresh failures`],
          ["Signature", w ? `${w.signature.exc_type}: ${w.signature.message_norm}` : "None: no witness"],
          ["Protocol", satisfied ? "Satisfied" : "Not satisfied"],
        ].map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong data-testid={label === "Signature" ? "signature" : undefined}>{value}</strong>
          </div>
        ))}
      </div>
      <Panel title="Six-run witness board" meta={`${fresh} fresh · ${mine.length - fresh} reused`}>
        <div className="run-board" data-testid="run-board">
          {[0, 1, 2].map((i) => (
            <RunCard key={`r${i}`} title={`Reference ${i + 1}`} run={slot("ref", i)} expectPass />
          ))}
          {[0, 1, 2].map((i) => (
            <RunCard key={`t${i}`} title={`Consumer ${i + 1}`} run={slot("test", i)} expectPass={false} />
          ))}
        </div>
      </Panel>
      {w ? (
        <div className="work-grid equal" data-testid="witness">
          <Panel title="Witness" meta={w.witness_class.replaceAll("_", " ").toLowerCase()}>
            <dl className="key-values">
              <div>
                <dt>Interaction</dt>
                <dd>
                  <code>{w.entry_point}</code> via <code>{w.oracle}</code> {w.oracle_version}
                </dd>
              </div>
              <div>
                <dt>Normalized failure</dt>
                <dd>
                  <code>
                    {w.signature.exc_type}: {w.signature.message_norm}
                  </code>
                </dd>
              </div>
              <div>
                <dt>Raised in</dt>
                <dd>
                  <code>{w.signature.origin_module ?? "unknown"}</code>
                </dd>
              </div>
              <div>
                <dt>Re-verifications</dt>
                <dd>{w.reverifications}</dd>
              </div>
            </dl>
            <AppAction onClick={() => go("evidence", d.finding_id)}>Inspect the evidence bundle</AppAction>{" "}
            <a className="app-action quiet" href={api.bundleUrl(w.witness_id)} data-testid="bundle-link">
              Download bundle
            </a>
          </Panel>
          {bad && (
            <Panel title="Raw output of one failing run" meta="Bounded, secrets removed">
              <pre className="code-block">
                {failing(bad)?.exc_type}: {failing(bad)?.message}
                {bad.stderr_tail ? `\n\nstderr:\n${bad.stderr_tail}` : ""}
              </pre>
            </Panel>
          )}
        </div>
      ) : (
        <StateBlock tone="warn" label={words(d.verdict)} title="No witness exists for this finding." testid="no-witness">
          The witness protocol requires three fresh reference passes and three fresh consumer failures with the same normalized signature. A reused world is not a fresh run, and infrastructure, setup, timeout, resource and harness failures cannot be counted as witnesses.
        </StateBlock>
      )}
    </>
  );
}

export function WitnessView({ go, id }: { go: Go; id: string | null }) {
  const { analysis } = useWorkspace();
  const pick = useAsync(async () => {
    if (id) return id;
    const all = await api.findings();
    return (all.find((f) => f.witness_ids.length > 0) ?? all[0])?.finding_id ?? null;
  }, [id, analysis?.id]);
  const fid = pick.data;
  const q = useAsync(() => (fid ? api.finding(fid) : Promise.resolve(null)), [fid]);
  if (pick.loading && !pick.data) return <Loading what="the witness" />;
  if (!fid) return <EmptyInline title="No finding exists yet">A witness belongs to a finding. Run an analysis first.</EmptyInline>;
  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <Loading what="the witness" />;
  return (
    <>
      <p className="panel-note">
        <VerdictStatus verdict={q.data.verdict} /> {q.data.artifact} → {q.data.consumer}{" "}
        <button className="back-link" onClick={() => go("finding", q.data?.finding_id)}>
          Back to the finding
        </button>
      </p>
      <Board d={q.data} go={go} />
    </>
  );
}
