/** One distinct, truthful message per state, for every view. A state is never rendered as another state, and an empty or failed
 *  view is never rendered as a clean result. */
export type StateKind = "empty" | "failed" | "unsupported" | "inconclusive" | "not-applicable";

const COPY: Record<StateKind, { title: string; body: string; tone: string }> = {
  empty: { title: "Nothing to show yet", body: "No records exist for this view. This is not a clean result: nothing has been analysed.", tone: "muted" },
  failed: { title: "This could not be produced", body: "The step failed, so there is no result. Absence of a result is not a pass.", tone: "bad" },
  unsupported: { title: "Not supported", body: "Faultline does not analyse this kind of input yet. It is listed so it is not mistaken for a clean result.", tone: "warn" },
  inconclusive: { title: "Inconclusive", body: "The evidence was not sufficient to say anything. This is neither a break nor a pass.", tone: "warn" },
  "not-applicable": { title: "Not applicable", body: "The consumer does not use any part of the artifact that this check covers, so nothing was checked.", tone: "muted" },
};

export function StateMessage({ view, kind, detail }: { view: string; kind: StateKind; detail?: string }) {
  const c = COPY[kind];
  return (
    <div className={`callout ${c.tone === "bad" ? "bad" : c.tone === "warn" ? "warn" : ""}`} data-testid={`state-${view}-${kind}`} data-state={kind} role="status">
      <strong>{c.title}</strong>
      <p className="small">{c.body}</p>
      {detail && <p className="small mono">{detail}</p>}
    </div>
  );
}
