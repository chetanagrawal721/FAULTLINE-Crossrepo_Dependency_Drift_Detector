import { useEffect, useState } from "react";
import { api, type FindingDetail as Detail } from "../api/client";
import { VerdictChip } from "./VerdictChip";

const short = (h: string) => `${h.slice(0, 12)}…`;

function Evidence({ d }: { d: Detail }) {
  const w = d.witnesses[0];
  const failing = d.runs.find((r) => r.side === "test" && r.entries.some((e) => !e.passed && !e.skipped && !e.not_applicable));
  const bad = failing?.entries.find((e) => !e.passed && !e.skipped && !e.not_applicable);
  return (
    <>
      <section className="panel" data-testid="repeatability">
        <h2>Repeatability</h2>
        <p>
          Reference passed <strong>{w ? w.ref_pass : d.runs.filter((r) => r.side === "ref").length}/3</strong> · consumer failed{" "}
          <strong>{w ? w.test_fail : 0}/3</strong> · fresh executions <strong>{d.fresh_runs}/6</strong>
          {d.reused_runs > 0 && ` · reused results ${d.reused_runs} (not counted)`}
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>World</th>
                <th>Run</th>
                <th>Provenance</th>
                <th>Result</th>
                <th>ms</th>
                <th>Run id</th>
              </tr>
            </thead>
            <tbody data-testid="run-rows">
              {d.runs.map((r) => (
                <tr key={r.run_id}>
                  <td>{r.side === "ref" ? "reference" : "consumer"}</td>
                  <td>{r.run_index}</td>
                  <td>{r.provenance === "FRESH_EXECUTION" ? "fresh execution" : "reused result"}</td>
                  <td>
                    <span className={`pill ${r.failure_class === "NONE" ? "pill-enabled" : "pill-bad"}`}>
                      {r.failure_class === "NONE" ? "pass" : r.failure_class.toLowerCase().replaceAll("_", " ")}
                    </span>
                  </td>
                  <td>{r.duration_ms}</td>
                  <td>
                    <code>{r.run_id.slice(-10)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {w && (
        <section className="panel" data-testid="witness">
          <h2>Witness</h2>
          <dl className="kv">
            <dt>Interaction</dt>
            <dd>
              <code>{w.entry_point}</code> via <code>{w.oracle}</code> {w.oracle_version}
            </dd>
            <dt>Normalized failure</dt>
            <dd data-testid="signature">
              <code>
                {w.signature.exc_type}: {w.signature.message_norm}
              </code>
            </dd>
            <dt>Raised in</dt>
            <dd>
              <code>{w.signature.origin_module ?? "unknown"}</code>
            </dd>
            <dt>Evidence kind</dt>
            <dd>{w.divergence.replaceAll("_", " ").toLowerCase()}, same normalized signature on all three consumer runs</dd>
          </dl>
          {bad && (
            <details>
              <summary>Raw output of one failing run</summary>
              <pre className="code">
                {bad.exc_type}: {bad.message}
                {failing?.stderr_tail ? `\n\nstderr:\n${failing.stderr_tail}` : ""}
              </pre>
            </details>
          )}
          <p>
            <a className="btn" href={api.bundleUrl(w.witness_id)} data-testid="bundle-link">
              Download evidence bundle
            </a>{" "}
            <span className="muted small">zip with manifest, hashes, worlds, runs and the artifact source; verify it with python -m faultline.witnesses.bundle</span>
          </p>
        </section>
      )}
    </>
  );
}

export function FindingDetailView({ id }: { id: string }) {
  const [d, setD] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setD(null);
    api.finding(id).then(setD).catch((e: Error) => setError(e.message));
  }, [id]);

  if (error) return <div className="panel error" role="alert">Could not load the finding: {error}</div>;
  if (!d) return <p className="muted">Loading finding…</p>;

  return (
    <div className="stack" data-testid="finding-detail">
      <p>
        <a href="#/">← All findings</a>
      </p>
      <section className="panel">
        <div className="row">
          <VerdictChip verdict={d.verdict} />
          <span className={`badge badge-${d.mode.toLowerCase()}`}>{d.mode === "FIXTURE" ? "REPRODUCIBLE FIXTURE" : d.mode}</span>
          <span className="muted small">
            {d.artifact} → {d.consumer}
          </span>
        </div>
        <p className="headline big" data-testid="headline">
          {d.headline}
        </p>
      </section>

      <section className="panel" data-testid="worlds">
        <h2>What was compared</h2>
        <div className="two">
          <div>
            <h3>Reference world</h3>
            <p>
              The artifact's own dependencies
              <br />
              <code>{short(d.reference.world_hash)}</code> · {d.reference.runtime} · {d.reference.package_count} packages
            </p>
          </div>
          <div>
            <h3>Consumer world</h3>
            <p>
              What {d.consumer} resolves
              <br />
              <code>{short(d.consumer_world.world_hash)}</code> · {d.consumer_world.runtime} · {d.consumer_world.package_count} packages
            </p>
          </div>
        </div>
        <h3>Dependency difference</h3>
        <p className="muted small">Candidate causes only. This list is not a finding and not an attribution.</p>
        <div className="table-wrap">
          <table data-testid="delta">
            <thead>
              <tr>
                <th>Package</th>
                <th>Reference</th>
                <th>Consumer</th>
              </tr>
            </thead>
            <tbody>
              {d.delta.map((x) => (
                <tr key={x.name}>
                  <th scope="row">{x.name}</th>
                  <td>{x.reference ?? "absent"}</td>
                  <td>{x.consumer ?? "absent"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Evidence d={d} />

      <section className="panel" data-testid="scope">
        <h2>Scope of this result</h2>
        <h3>Exercised</h3>
        <p>{d.scope.exercised.length ? d.scope.exercised.map((e) => <code key={e} className="mod">{e}</code>) : "nothing"}</p>
        {d.scope.not_applicable.length > 0 && (
          <>
            <h3>Not applicable in this world</h3>
            <p>{d.scope.not_applicable.map((e) => <code key={e} className="mod">{e}</code>)}</p>
          </>
        )}
        <h3>Not checked</h3>
        <ul>
          {d.scope.not_checked.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
        {d.scope.reasons.length > 0 && (
          <>
            <h3>Why some interactions were not decided</h3>
            <ul>
              {d.scope.reasons.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </>
        )}
        <p className="muted small">Verdict policy {d.scope.policy} (Phase 1 subset of the full decision table).</p>
      </section>
    </div>
  );
}
