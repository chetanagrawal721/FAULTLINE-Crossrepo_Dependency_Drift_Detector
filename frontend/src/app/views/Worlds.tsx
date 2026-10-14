import { useEffect, useState } from "react";
import type { AnalysisView, CellView } from "../../api/client";
import { short } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { EmptyInline, Loading, StateBlock, StateNote, VerdictStatus } from "../shared";

type Go = (view: AppView, id?: string | null) => void;

const UNSUPPORTED_REASONS = new Set(["needs_build", "non_registry_source", "private_index_without_lock", "setup_py_not_executed", "lock_unsupported", "private_packages"]);
const cellTone = (s: string) => (s === "NO_DRIFT" ? "good" : s === "ANALYZED" ? "copper" : s === "INCONCLUSIVE" ? "warn" : "neutral");

function OracleCell({ cell, oracle }: { cell: CellView; oracle: string }) {
  const step = cell.oracle_plan.find((s) => s.oracle === oracle);
  if (!step) return <Status tone="neutral">{cell.state === "NO_DRIFT" ? "NOTHING TO RUN" : "NOT RECORDED"}</Status>;
  return (
    <span title={step.reason || undefined}>
      <Status tone={step.status === "RAN" ? "good" : step.status === "BLOCKED" ? "warn" : "neutral"}>{step.status.replace("_", " ")}</Status>
    </span>
  );
}

function Attribution({ a }: { a: NonNullable<CellView["attribution"]> }) {
  return (
    <details data-testid="why-path" className="attribution-details">
      <summary>
        Attribution: {a.minimal.length > 0 ? a.minimal.join(" + ") : "no single cause established"} ({a.status}, {a.sidedness.replace("_", "-")})
      </summary>
      {a.minimal_claim ? (
        <p className="panel-copy">
          The cause is <strong>{a.minimal_claim}</strong>: adding it to the reference reproduces the failure, and reverting it in the consumer world removes it.
        </p>
      ) : (
        <p className="panel-copy">Not claimed as minimal: {a.notes.filter((n) => n.startsWith("missing") || n.includes("budget") || n.includes("necessity")).join(" ") || a.status}</p>
      )}
      <p className="panel-note">Every world below was forced by Faultline for this search. None of them is an environment a repository actually uses.</p>
      <ul className="why-items">
        {a.attempts.map((t, i) => (
          <li key={i}>
            <code>{t.label}</code> {t.direction}: {t.subset.join(", ") || "(none)"} → <strong>{t.outcome}</strong>
            {t.note ? ` · ${t.note}` : ""}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Matrix({ analysis, selected, onSelect, go }: { analysis: AnalysisView; selected: string | null; onSelect: (id: string) => void; go: Go }) {
  const f = analysis.funnel as Record<string, number>;
  const cells = analysis.cells;
  const failed = analysis.failed;
  const rows = [
    ...cells.map((c) => ({ kind: "cell" as const, c })),
    ...failed.map((x) => ({ kind: "failed" as const, x })),
  ];
  const total = Number(f.consumers_discovered ?? 0);
  const done = Number(f.consumers_analysed ?? 0);
  return (
    <Panel title="World matrix" meta={`${done} of ${total} discovered consumers analysed`}>
      <p className="panel-note" data-testid="coverage">
        Coverage: <strong>{done}</strong> of <strong>{total}</strong> discovered consumers analysed
        {failed.length > 0 ? ` · ${failed.length} could not be analysed (listed in the table, not hidden)` : ""}. This is a count, not a score.
      </p>
      <DataTable
        testid="matrix"
        columns={["Consumer(s)", "Cell", "Reference world", "Consumer world", "O-import", "O-tests", "O-bind", "Result"]}
        rowAttrs={(i) => {
          const r = rows[i];
          return r.kind === "cell"
            ? { "data-testid": "matrix-row", "data-cell-state": r.c.state }
            : { "data-testid": "matrix-failed-row", "data-cell-state": UNSUPPORTED_REASONS.has(r.x.reason) ? "UNSUPPORTED" : "FAILED" };
        }}
        rows={rows.map((r) =>
          r.kind === "cell"
            ? [
                <strong>{r.c.consumers.join(", ")}</strong>,
                <Status tone={cellTone(r.c.state)}>{r.c.state.replace("_", " ")}</Status>,
                <code data-testid="world-hash" title={r.c.ref_world_hash}>{short(r.c.ref_world_hash, 14)}</code>,
                <code title={r.c.test_world_hash}>{short(r.c.test_world_hash, 14)}</code>,
                <OracleCell cell={r.c} oracle="o_import" />,
                <OracleCell cell={r.c} oracle="o_tests" />,
                <OracleCell cell={r.c} oracle="o_bind" />,
                r.c.verdict ? <VerdictStatus verdict={r.c.verdict} /> : <Status>{r.c.state === "NO_DRIFT" ? "No drift: nothing to run" : "No oracle result"}</Status>,
              ]
            : (() => {
                const unsupported = UNSUPPORTED_REASONS.has(r.x.reason);
                return [
                  <strong>{r.x.consumer}</strong>,
                  <Status tone={unsupported ? "neutral" : "warn"}>{unsupported ? "UNSUPPORTED" : "FAILED"}</Status>,
                  <span className="matrix-failed-note">{r.x.side} world: {r.x.reason}. {r.x.text}</span>,
                  "—",
                  "—",
                  "—",
                  "—",
                  <Status>{unsupported ? "Not supported by the MVP" : "Could not be analysed"}</Status>,
                ];
              })(),
        )}
        onRow={(i) => {
          const r = rows[i];
          if (r.kind === "cell") onSelect(r.c.id);
        }}
      />
      {rows.length === 0 && <StateNote view="matrix" kind="empty" detail="No consumer produced a cell." />}
      {cells.some((c) => c.state === "INCONCLUSIVE" || c.verdict === "INCONCLUSIVE") && <StateNote view="matrix" kind="inconclusive" />}
      {cells.some((c) => c.state === "NOT_APPLICABLE") && <StateNote view="matrix" kind="not-applicable" />}
      {failed.some((x) => UNSUPPORTED_REASONS.has(x.reason)) && <StateNote view="matrix" kind="unsupported" detail={failed.filter((x) => UNSUPPORTED_REASONS.has(x.reason)).map((x) => `${x.consumer}: ${x.reason}`).join(" · ")} />}
      {failed.some((x) => !UNSUPPORTED_REASONS.has(x.reason)) && <StateNote view="matrix" kind="failed" detail={failed.filter((x) => !UNSUPPORTED_REASONS.has(x.reason)).map((x) => `${x.consumer}: ${x.side} world ${x.reason}`).join(" · ")} />}
      <div className="coverage-bar">
        <span />
        <strong>
          Coverage {done} / {total} consumers
        </strong>
        <small>
          {failed.filter((x) => UNSUPPORTED_REASONS.has(x.reason)).length} unsupported · {failed.filter((x) => !UNSUPPORTED_REASONS.has(x.reason)).length} failed · {cells.filter((c) => c.state === "INCONCLUSIVE").length} inconclusive
        </small>
      </div>
      {selected === null && cells.length > 0 && <p className="panel-note">Select a row to see its worlds, dependency delta and attribution.</p>}
      <div className="app-actions">
        <AppAction quiet onClick={() => go("relationships")}>
          Relationships
        </AppAction>
      </div>
    </Panel>
  );
}

export function WorldsView({ go }: { go: Go }) {
  const { analysis, analysisLoading, project } = useWorkspace();
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    // open on the cell that matters most: a witnessed one, then any with a verdict, then the first
    const cs = analysis?.cells ?? [];
    const first = cs.find((c) => c.verdict === "BREAK_WITNESSED" || c.verdict === "SILENT_DIVERGENCE_WITNESSED") ?? cs.find((c) => c.verdict && c.state !== "NO_DRIFT") ?? cs[0];
    setSelected(first?.id ?? null);
  }, [analysis?.id]);
  if (analysisLoading && !analysis) return <Loading what="the world matrix" />;
  if (!analysis) {
    return (
      <StateBlock label="NOT ANALYSED" title="No world matrix exists for this project." testid="matrix-empty">
        {project ? `${project.name} has not been analysed yet.` : "No project exists yet."} This is not a clean result: nothing has been analysed.
        <br />
        <AppAction onClick={() => go("new")}>New analysis</AppAction>
      </StateBlock>
    );
  }
  const cell = analysis.cells.find((c) => c.id === selected) ?? null;
  return (
    <>
      <Matrix analysis={analysis} selected={selected} onSelect={setSelected} go={go} />
      {cell && (
        <>
          <div className="work-grid equal">
            <Panel title="Reference world" meta={short(cell.ref_world_hash, 14)}>
              <dl className="key-values">
                <div>
                  <dt>Build state</dt>
                  <dd>
                    <Status tone="good">BUILT</Status>
                  </dd>
                </div>
                <div>
                  <dt>World hash</dt>
                  <dd>
                    <code>{short(cell.ref_world_hash, 20)}</code>
                  </dd>
                </div>
                <div>
                  <dt>Runtime</dt>
                  <dd data-testid="runtime">
                    {cell.runtime} · {cell.platform}
                  </dd>
                </div>
                <div>
                  <dt>Importer visibility</dt>
                  <dd>{cell.visibility}</dd>
                </div>
              </dl>
            </Panel>
            <Panel title="Consumer world" meta={short(cell.test_world_hash, 14)}>
              <dl className="key-values">
                <div>
                  <dt>Build state</dt>
                  <dd>
                    <Status tone="good">BUILT</Status>
                  </dd>
                </div>
                <div>
                  <dt>World hash</dt>
                  <dd>
                    <code>{short(cell.test_world_hash, 20)}</code>
                  </dd>
                </div>
                <div>
                  <dt>Modules exercised</dt>
                  <dd>{cell.imported_modules.join(", ") || "—"}</dd>
                </div>
                <div>
                  <dt>Consumers</dt>
                  <dd>{cell.consumers.join(", ")}</dd>
                </div>
              </dl>
            </Panel>
          </div>
          <Panel title="Exact delta against the reference" meta="Candidate causes only">
            {cell.delta.length === 0 ? (
              <EmptyInline title="No package differs">The consumer's world equals the reference world.</EmptyInline>
            ) : (
              <DataTable columns={["Package", "Reference", "Consumer", "Change"]} rows={cell.delta.map((d) => [<strong>{d.name}</strong>, <code>{d.reference ?? "absent"}</code>, <code>{d.consumer ?? "absent"}</code>, d.kind])} />
            )}
            {cell.attribution && <Attribution a={cell.attribution} />}
            <div className="app-actions">
              {cell.finding_id && <AppAction onClick={() => go("finding", cell.finding_id)}>Open the finding</AppAction>}
            </div>
          </Panel>
        </>
      )}
    </>
  );
}
