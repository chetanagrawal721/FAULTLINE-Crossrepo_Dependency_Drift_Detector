import { useState } from "react";
import { api, type RelationshipView } from "../../api/client";
import { useAsync, short, words } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Icon, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { Loading, ModeStatus, StateNote, VerdictStatus } from "../shared";

type Go = (view: AppView, id?: string | null) => void;
const VERDICTS = ["BREAK_WITNESSED", "SILENT_DIVERGENCE_WITNESSED", "NO_DIVERGENCE_OBSERVED", "EXPOSED", "POTENTIAL", "NOT_EXPOSED", "INCONCLUSIVE", "HYGIENE"];

function EvidenceLines({ r }: { r: RelationshipView }) {
  return (
    <>
      {r.evidence.map((e, i) => (
        <div className="evidence-row" key={i}>
          <Icon name="check" />
          <span>
            <code>
              {e.repository}@{e.commit.slice(0, 10)} {e.file_path}:{e.line}
            </code>{" "}
            {e.excerpt}
          </span>
          <Status tone="good">Observed</Status>
        </div>
      ))}
    </>
  );
}

export function SuspectedTray({ rels }: { rels: RelationshipView[] }) {
  const tray = rels.filter((r) => r.status === "SUSPECTED");
  return (
    <Panel title="Suspected tray" meta="Never produces a finding on its own">
      {tray.length === 0 ? (
        <StateNote view="tray" kind="empty" detail="No suspected relationships were found. A suspected candidate stays here until a person confirms it with real evidence." />
      ) : (
        <div data-testid="suspected-tray">
          {tray.map((r) => (
            <div key={r.id} data-testid="suspected-item" className="suspected-item">
              <p className="panel-copy">
                <strong>
                  {r.producer} ↔ {r.consumer}
                </strong>{" "}
                <Status tone="warn">
                  {r.level} · suspected · {r.confidence}
                </Status>
              </p>
              <p className="panel-note">A suspected candidate is not a finding. Names and version similarities can suggest a connection, but they do not establish consumption on their own.</p>
              {r.notes.map((n) => (
                <p key={n} className="panel-note">
                  {n}
                </p>
              ))}
              <EvidenceLines r={r} />
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

export function FindingsView({ go }: { go: Go }) {
  const { analysis } = useWorkspace();
  const [query, setQuery] = useState("");
  const [verdict, setVerdict] = useState("");
  const [mode, setMode] = useState("");
  const list = useAsync(() => api.findings(verdict || undefined), [verdict, analysis?.id]);
  const rows = (list.data ?? []).filter((f) => (!mode || f.mode === mode) && `${f.artifact} ${f.consumer} ${f.finding_id} ${f.headline}`.toLowerCase().includes(query.toLowerCase()));
  const filtering = Boolean(query || verdict || mode);

  return (
    <>
      <div className="filter-bar">
        <label>
          <Icon name="search" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search repository, finding ID or text…" aria-label="Search findings" />
        </label>
        <select className="filter-select" value={verdict} onChange={(e) => setVerdict(e.target.value)} aria-label="Filter by verdict">
          <option value="">All verdicts</option>
          {VERDICTS.map((v) => (
            <option key={v} value={v}>
              {words(v)}
            </option>
          ))}
        </select>
        <select className="filter-select" value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Filter by mode">
          <option value="">All modes</option>
          <option value="LIVE">Live</option>
          <option value="FIXTURE">Fixture</option>
          <option value="REPLAY">Replay</option>
        </select>
      </div>
      <Panel title="Findings" meta={list.data ? `${rows.length} of ${list.data.length} records` : "Loading"}>
        {list.error && !list.data && <StateNote view="findings" kind="failed" detail={list.error} />}
        {list.loading && !list.data && <Loading what="findings" />}
        {list.data && rows.length > 0 && (
          <DataTable
            testid="findings-list"
            columns={["Finding", "Artifact → consumer", "Verdict", "Mode", "Scoped statement"]}
            rowAttrs={(i) => ({ "data-testid": "finding-row", "data-verdict": rows[i].verdict })}
            rows={rows.map((f) => [<code>{short(f.finding_id.replace(/^fnd_/, ""), 10)}</code>, `${f.artifact} → ${f.consumer}`, <VerdictStatus verdict={f.verdict} />, <ModeStatus mode={f.mode} />, <span className="clamp-3" title={f.headline}>{f.headline}</span>])}
            onRow={(i) => go("finding", rows[i].finding_id)}
          />
        )}
        {list.data && rows.some((f) => f.verdict === "INCONCLUSIVE") && <StateNote view="finding" kind="inconclusive" />}
        {list.data && rows.length === 0 && (
          <div className="empty-inline" data-testid="state-findings-empty" data-state="empty">
            <h3>{filtering ? "No findings match these filters" : "No findings have been recorded"}</h3>
            <p>{filtering ? "Clear one or more filters or search a broader term." : "This is not a clean result: nothing has been analysed yet, or no cell produced a finding."}</p>
            {filtering ? (
              <AppAction
                onClick={() => {
                  setQuery("");
                  setVerdict("");
                  setMode("");
                }}
              >
                Clear filters
              </AppAction>
            ) : (
              <AppAction onClick={() => go("new")}>New analysis</AppAction>
            )}
          </div>
        )}
      </Panel>
      <SuspectedTray rels={analysis?.relationships ?? []} />
    </>
  );
}
