import type { FindingSummary } from "../api/client";
import { VerdictChip } from "./VerdictChip";

export function FindingsList({ findings }: { findings: FindingSummary[] | null }) {
  return (
    <section className="panel" aria-label="Findings" data-testid="findings">
      <h2>Findings</h2>
      {findings === null && <p className="muted">Loading…</p>}
      {findings?.length === 0 && (
        <p className="muted" data-testid="no-findings">
          No findings yet. Nothing has been analysed, so Faultline makes no compatibility claims. Run a fixture scenario above.
        </p>
      )}
      <ul className="finding-list">
        {findings?.map((f) => (
          <li key={f.finding_id}>
            <a href={`#/finding/${f.finding_id}`} className="finding-link" data-testid="finding-link">
              <div className="row">
                <VerdictChip verdict={f.verdict} />
                <span className={`badge badge-${f.mode.toLowerCase()}`}>{f.mode === "FIXTURE" ? "REPRODUCIBLE FIXTURE" : f.mode}</span>
                <span className="muted small">
                  {f.artifact} → {f.consumer}
                </span>
              </div>
              <p className="headline">{f.headline}</p>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
