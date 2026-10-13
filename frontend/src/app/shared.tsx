import type { ReactNode } from "react";
import { Status } from "../ui/primitives";
import { words } from "../lib/hooks";

type Tone = "neutral" | "copper" | "warn" | "good";

/** How a verdict is shown. The words are the verdict words themselves; the tone only helps the eye. */
export function verdictTone(verdict: string): Tone {
  switch (verdict) {
    case "BREAK_WITNESSED":
    case "SILENT_DIVERGENCE_WITNESSED":
      return "copper";
    case "NO_DIVERGENCE_OBSERVED":
    case "NOT_EXPOSED":
      return "good";
    case "INCONCLUSIVE":
    case "EXPOSED":
    case "POTENTIAL":
      return "warn";
    default:
      return "neutral";
  }
}

/** WITNESSED verdicts were reproduced by running code (3 + 3); STATIC ones were read from source and API changes and nothing was run for the claim. */
export function evidenceKind(verdict: string): "WITNESSED" | "STATIC" | "OTHER" {
  switch (verdict) {
    case "BREAK_WITNESSED":
    case "SILENT_DIVERGENCE_WITNESSED":
      return "WITNESSED";
    case "EXPOSED":
    case "POTENTIAL":
    case "NOT_EXPOSED":
      return "STATIC";
    default:
      return "OTHER";
  }
}

export function VerdictStatus({ verdict }: { verdict: string }) {
  const kind = evidenceKind(verdict);
  return (
    <span className="verdict-with-kind">
      <Status tone={verdictTone(verdict)}>{words(verdict)}</Status>
      {kind === "STATIC" && (
        <span className="evidence-kind static" data-testid="evidence-kind" title="Static analysis: read from source and API changes. Nothing was executed for this claim.">
          static
        </span>
      )}
    </span>
  );
}

export function ModeStatus({ mode }: { mode: string }) {
  return (
    <span data-testid="mode-badge" title={mode === "FIXTURE" ? "Committed fixture repositories run through the real pipeline" : mode === "REPLAY" ? "Recorded evidence: nothing can be started" : "Public repositories you submitted"}>
      <Status tone={mode === "LIVE" ? "copper" : "neutral"}>{mode === "REPLAY" ? "RECORDED" : mode}</Status>
    </span>
  );
}

export function jobTone(status: string): Tone {
  return status === "DONE" ? "good" : status === "FAILED" ? "warn" : status === "RUNNING" || status === "QUEUED" ? "copper" : "neutral";
}

/** A distinct, truthful message for an empty, failed or unsupported view. An empty view is never drawn as a clean result. */
export function StateBlock({ tone = "neutral", label, title, children, testid }: { tone?: Tone; label: string; title: string; children?: ReactNode; testid?: string }) {
  return (
    <div className="state-panel compact" data-testid={testid}>
      <Status tone={tone}>{label}</Status>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
    </div>
  );
}

export type StateKind = "empty" | "failed" | "unsupported" | "inconclusive" | "not-applicable";

const COPY: Record<StateKind, { title: string; body: string }> = {
  empty: { title: "Nothing to show yet", body: "No records exist for this view. This is not a clean result: nothing has been analysed." },
  failed: { title: "This could not be produced", body: "The step failed, so there is no result. Absence of a result is not a pass." },
  unsupported: { title: "Not supported", body: "Faultline does not analyse this kind of input yet. It is listed so it is not mistaken for a clean result." },
  inconclusive: { title: "Inconclusive", body: "The evidence was not sufficient to say anything. This is neither a break nor a pass." },
  "not-applicable": { title: "Not applicable", body: "The consumer does not use any part of the artifact that this check covers, so nothing was checked." },
};

/** One distinct message per state, for every view. A state is never drawn as another state, and an empty or failed view is never drawn as a clean result. */
export function StateNote({ view, kind, detail }: { view: string; kind: StateKind; detail?: string }) {
  const c = COPY[kind];
  return (
    <div className={`empty-inline state-note state-note-${kind}`} data-testid={`state-${view}-${kind}`} data-state={kind} role="status">
      <h3>{c.title}</h3>
      <p>{c.body}</p>
      {detail && <p className="state-note-detail">{detail}</p>}
    </div>
  );
}

export function EmptyInline({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty-inline">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}

export const Loading = ({ what = "records" }: { what?: string }) => <p className="panel-note" role="status">Loading {what}…</p>;

export const ErrorNote = ({ error }: { error: string }) => (
  <div className="state-panel compact" role="alert">
    <Status tone="warn">REQUEST FAILED</Status>
    <h2>The API did not return this record.</h2>
    <p>{error}</p>
  </div>
);
