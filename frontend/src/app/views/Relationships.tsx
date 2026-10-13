import { useEffect, useState } from "react";
import type { RelationshipView } from "../../api/client";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Icon, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { Loading, StateBlock } from "../shared";

type Go = (view: AppView, id?: string | null) => void;

const signalNames: Record<string, string> = {
  published_name: "Published package name",
  git_dependency: "Git dependency on the repository",
  declared: "User-declared comparison",
};

export function RelationshipsView({ go }: { go: Go }) {
  const { analysis, analysisLoading, project } = useWorkspace();
  const rels: RelationshipView[] = analysis?.relationships ?? [];
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => setSelected(rels[0]?.id ?? null), [analysis?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (analysisLoading && !analysis) return <Loading what="relationships" />;
  if (!analysis) {
    return (
      <StateBlock label="NOT ANALYSED" title="No relationships have been evaluated for this project." testid="relationships-empty">
        {project ? `${project.name} has not been analysed yet.` : "No project exists yet."} This is not a clean result.
        <br />
        <AppAction onClick={() => go("new")}>New analysis</AppAction>
      </StateBlock>
    );
  }
  const active = rels.find((r) => r.id === selected) ?? null;
  return (
    <div className="work-grid two-one">
      <Panel title="Relationships" meta={`${rels.filter((r) => r.actionable).length} actionable · ${rels.filter((r) => r.status === "SUSPECTED").length} suspected`}>
        {rels.length === 0 ? (
          <p className="panel-copy">No relationship has evidence on both sides, so no consumer was analysed. This is not a statement that the repositories are unrelated.</p>
        ) : (
          <DataTable
            columns={["Candidate", "Signals", "Evidence level", "Status"]}
            rowAttrs={(i) => ({ "data-testid": "relationship", "data-actionable": String(rels[i].actionable) })}
            rows={rels.map((r) => [
              <strong>
                {r.producer} → {r.consumer}
              </strong>,
              r.kind.replaceAll("_", " ").toLowerCase(),
              <Status tone={r.actionable ? "good" : "warn"}>
                {r.level} · {r.confidence}
              </Status>,
              r.status === "SUSPECTED" ? <Status tone="warn">SUSPECTED</Status> : <Status tone="copper">{r.actionable ? "ACTIONABLE" : r.status}</Status>,
            ])}
            onRow={(i) => setSelected(rels[i].id)}
          />
        )}
      </Panel>
      <Panel title="Relationship detail" meta={active ? `${active.level} · ${active.confidence}` : "Select a candidate"}>
        {!active ? (
          <p className="panel-copy">Select a relationship to see the evidence behind it.</p>
        ) : (
          <>
            <p className="panel-copy">
              {active.actionable
                ? "This relationship has evidence in the files at the pinned commits, so the consumer was analysed."
                : "Names and version similarities can suggest a connection, but they do not establish consumption on their own. A suspected candidate never produces a finding."}
            </p>
            {active.notes.map((n) => (
              <p className="panel-note" key={n}>
                {n}
              </p>
            ))}
            {active.evidence.length === 0 && <p className="panel-note">No file-level evidence is recorded for this candidate.</p>}
            {active.evidence.map((e, i) => (
              <div className="evidence-row" key={i}>
                <Icon name="check" />
                <span>
                  <strong>{signalNames[e.signal] ?? e.signal.replaceAll("_", " ")}</strong>
                  <br />
                  <code>
                    {e.repository}@{e.commit.slice(0, 10)} {e.file_path}
                    {e.line ? `:${e.line}` : ""}
                  </code>{" "}
                  {e.excerpt}
                </span>
                <Status tone="good">Observed</Status>
              </div>
            ))}
            <AppAction onClick={() => go("inventory")}>Inspect inventory</AppAction>
          </>
        )}
      </Panel>
    </div>
  );
}
