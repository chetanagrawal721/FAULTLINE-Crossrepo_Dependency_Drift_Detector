import { useEffect, useState } from "react";
import { api, type WhyPath } from "../api/client";
import { StateMessage } from "./StateMessage";

/** The chain from evidence to verdict. A link that was not analysed says so; it is never invented. */
export function WhyPathPanel({ findingId }: { findingId: string }) {
  const [w, setW] = useState<WhyPath | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .whyPath(findingId)
      .then(setW)
      .catch((e: Error) => setError(e.message));
  }, [findingId]);
  if (error) return <StateMessage view="why-path" kind="failed" detail={error} />;
  if (!w) return <p className="muted">Loading why-path…</p>;
  return (
    <section className="panel" data-testid="why-path-panel">
      <h2>Why-path</h2>
      <ol className="plain-list">
        {w.steps.map((s) => (
          <li key={s.kind} className="panel" data-testid={`why-step-${s.kind}`} data-status={s.status}>
            <div className="row">
              <strong>{s.title}</strong>
              <span className={`pill ${s.status === "analysed" ? "pill-enabled" : "pill-partial"}`}>{s.status === "analysed" ? "analysed" : "not analysed"}</span>
            </div>
            <p className="small">{s.detail}</p>
            {s.items.length > 0 && (
              <ul className="small">
                {s.items.map((it, i) => (
                  <li key={i} className="mono">
                    {it}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
