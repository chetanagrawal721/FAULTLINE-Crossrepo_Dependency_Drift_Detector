import type { CapabilityStatus } from "../../api/client";
import { DataTable, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { Loading } from "../shared";

const tone = (s: string) => (s === "enabled" ? "good" : s === "partial" ? "warn" : "neutral");

function Cell({ c }: { c: CapabilityStatus }) {
  return (
    <span title={c.reason ?? undefined}>
      <Status tone={tone(c.state)}>{c.state.toUpperCase()}</Status>
    </span>
  );
}

export function CoverageView() {
  const { caps } = useWorkspace();
  if (!caps) return <Loading what="what this deployment supports" />;
  const oracles = Object.entries(caps.oracles);
  const features = Object.entries(caps.features);
  return (
    <>
      <Panel title="Ecosystem support" meta={`Capability version ${caps.capability_version} · hover a status for the reason`}>
        <div data-testid="capabilities">
          <DataTable
            columns={["Ecosystem", "Inventory", "Resolution", "World construction", "Runtime witness"]}
            rows={caps.ecosystems.map((e) => [<strong>{e.ecosystem}</strong>, <Cell c={e.inventory} />, <Cell c={e.resolve} />, <Cell c={e.world} />, <Cell c={e.runtime_witness} />])}
          />
        </div>
        <p className="panel-note">Inventory support does not imply runtime execution support. Anything shown as unsupported or unavailable is not hidden: it is stated here and on every finding that depends on it.</p>
      </Panel>
      <div className="work-grid equal">
        <Panel title="Oracles" meta="What can observe behavior">
          <DataTable columns={["Oracle", "State", "What it does"]} rows={oracles.map(([name, c]) => [<strong>{name.replace("_", "-").toUpperCase()}</strong>, <Cell c={c} />, c.reason])} />
        </Panel>
        <Panel title="Features" meta="What this deployment does">
          <DataTable columns={["Feature", "State", "Detail"]} rows={features.map(([name, c]) => [<strong>{name.replaceAll("_", " ")}</strong>, <Cell c={c} />, c.reason])} />
        </Panel>
      </div>
      <Panel title="Sandbox" meta="Verified on the running deployment">
        <dl className="key-values">
          <div>
            <dt>State</dt>
            <dd>
              <Status tone={caps.sandbox.verified ? "good" : "warn"}>{caps.sandbox.state.toUpperCase()}</Status>
            </dd>
          </div>
          <div>
            <dt>Boundary checks</dt>
            <dd>{caps.sandbox.reason}</dd>
          </div>
        </dl>
        <p className="panel-note">If the boundary cannot be verified, execution is disabled rather than bypassed.</p>
      </Panel>
      <div className="release-gates">
        {[
          ["Gate D", "Every canonical requirement of the specification", "python scripts/conformance_report.py"],
          ["Gate E", "Release hardening: security gate, evaluation, clean-machine replay", "see docs/submission_checklist.md"],
        ].map(([gate, title, how]) => (
          <article key={gate}>
            <Status tone="neutral">CHECKED OUTSIDE THIS APP</Status>
            <span>{gate}</span>
            <h3>{title}</h3>
            <p>
              The result is produced by <code>{how}</code>, which runs each requirement's tests and checks that its evidence exists. This page does not claim a gate was reached.
            </p>
          </article>
        ))}
      </div>
    </>
  );
}
