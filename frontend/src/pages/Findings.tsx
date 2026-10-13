import { useEffect, useState } from "react";
import { api, type AnalysisView, type FindingSummary, type RelationshipView } from "../api/client";
import { StateMessage } from "../components/StateMessage";
import { VerdictChip } from "../components/VerdictChip";

const VERDICTS = ["", "BREAK_WITNESSED", "SILENT_DIVERGENCE_WITNESSED", "NO_DIVERGENCE_OBSERVED", "EXPOSED", "POTENTIAL", "NOT_EXPOSED", "INCONCLUSIVE", "HYGIENE"];

function SuspectedTray({ rels }: { rels: RelationshipView[] }) {
  const tray = rels.filter((r) => r.status === "SUSPECTED");
  if (tray.length === 0) return <StateMessage view="tray" kind="empty" detail="No suspected relationships were found." />;
  return (
    <ul className="plain-list" data-testid="suspected-tray">
      {tray.map((r) => (
        <li key={r.id} className="panel" data-testid="suspected-item">
          <div className="row">
            <strong className="mono">
              {r.producer} ↔ {r.consumer}
            </strong>
            <span className="pill pill-partial">
              {r.level} · suspected · {r.confidence}
            </span>
          </div>
          <p className="small callout warn">A suspected candidate is not a finding. It stays here until a person confirms it with real evidence.</p>
          {r.notes.map((n) => (
            <p key={n} className="small muted">
              {n}
            </p>
          ))}
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
      ))}
    </ul>
  );
}

export function Findings() {
  const [verdict, setVerdict] = useState("");
  const [findings, setFindings] = useState<FindingSummary[] | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .findings(verdict || undefined)
      .then(setFindings)
      .catch((e: Error) => setError(e.message));
  }, [verdict]);

  useEffect(() => {
    api
      .projects()
      .then((ps) => (ps[0] ? api.projectAnalysis(ps[0].id) : null))
      .then(setAnalysis)
      .catch(() => setAnalysis(null));
  }, []);

  return (
    <section className="panel" aria-label="Findings" data-testid="findings-page">
      <h2>Findings</h2>
      <p className="muted small">Every verdict is scoped to what was exercised. Nothing here claims two repositories are compatible.</p>
      <label className="row">
        <span className="small">Filter by verdict</span>
        <select value={verdict} onChange={(e) => setVerdict(e.target.value)} aria-label="Filter by verdict">
          {VERDICTS.map((v) => (
            <option key={v} value={v}>
              {v ? v.replaceAll("_", " ") : "all verdicts"}
            </option>
          ))}
        </select>
      </label>
      {error && <StateMessage view="findings" kind="failed" detail={error} />}
      {!error && findings === null && <p className="muted">Loading…</p>}
      {findings && findings.length === 0 && <StateMessage view="findings" kind="empty" detail={verdict ? `No finding has the verdict ${verdict}.` : undefined} />}
      <ul className="plain-list" data-testid="findings-list">
        {findings?.map((f) => (
          <li key={f.finding_id} className="panel" data-testid="finding-row" data-verdict={f.verdict}>
            <div className="row">
              <VerdictChip verdict={f.verdict} />
              <span className="pill">{f.mode}</span>
              <strong className="mono">
                {f.artifact} → {f.consumer}
              </strong>
            </div>
            <p className="small">{f.headline}</p>
            {f.verdict === "INCONCLUSIVE" && <StateMessage view="finding" kind="inconclusive" />}
            {f.verdict === "NOT_APPLICABLE" && <StateMessage view="finding" kind="not-applicable" />}
            <a href={`#/finding/${f.finding_id}`}>Witness detail and why-path →</a>
          </li>
        ))}
      </ul>
      <h3>Suspected tray</h3>
      {analysis ? <SuspectedTray rels={analysis.relationships} /> : <StateMessage view="tray" kind="empty" detail="No analysis has been run." />}
    </section>
  );
}
