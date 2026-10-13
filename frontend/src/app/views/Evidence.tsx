import { useState } from "react";
import { api } from "../../api/client";
import { useAsync, short } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { EmptyInline, ErrorNote, Loading, StateBlock, VerdictStatus } from "../shared";

type Go = (view: AppView, id?: string | null) => void;
const TABS = ["Artifacts", "Bundle manifest", "Integrity", "Replay"] as const;

const kind = (path: string) => (path.endsWith(".json") ? "JSON" : path.endsWith(".md") ? "Markdown" : path.endsWith(".txt") ? "Text" : path.includes("tree/") ? "Source file" : "File");

export function EvidenceView({ go, id }: { go: Go; id: string | null }) {
  const { analysis, caps } = useWorkspace();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Artifacts");
  const pick = useAsync(async () => {
    const all = await api.findings();
    const withWitness = all.filter((f) => f.witness_ids.length > 0);
    return { all, chosen: (id ? all.find((f) => f.finding_id === id) : null) ?? withWitness[0] ?? null, withWitness };
  }, [id, analysis?.id]);
  const f = pick.data?.chosen ?? null;
  const witnessId = f?.witness_ids[0] ?? null;
  const manifest = useAsync(() => (witnessId ? api.bundleManifest(witnessId) : Promise.resolve(null)), [witnessId]);

  if (pick.loading && !pick.data) return <Loading what="evidence" />;
  if (pick.error) return <ErrorNote error={pick.error} />;
  if (!f || !witnessId) {
    return (
      <StateBlock label="NO WITNESS" title="No evidence bundle exists yet." testid="evidence-empty">
        An evidence bundle is exported for a witness: three fresh reference passes and three fresh consumer failures with the same signature. No finding has one, so there is nothing to export. This is not a statement that nothing is wrong.
        <br />
        <AppAction onClick={() => go("findings")}>Open findings</AppAction>
      </StateBlock>
    );
  }
  const m = manifest.data;
  return (
    <>
      <p className="panel-note">
        <VerdictStatus verdict={f.verdict} /> {f.artifact} → {f.consumer}{" "}
        {pick.data && pick.data.withWitness.length > 1 && (
          <select className="filter-select" value={f.finding_id} onChange={(e) => go("evidence", e.target.value)} aria-label="Choose a finding">
            {pick.data.withWitness.map((x) => (
              <option key={x.finding_id} value={x.finding_id}>
                {x.artifact} → {x.consumer} · {x.verdict.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        )}
      </p>
      <div className="app-tabs">
        {TABS.map((name) => (
          <button className={tab === name ? "active" : ""} onClick={() => setTab(name)} key={name}>
            {name}
          </button>
        ))}
      </div>
      <Panel title={tab} meta={`Witness ${short(witnessId.replace(/^wit_/, ""), 12)}`}>
        {manifest.error && <ErrorNote error={manifest.error} />}
        {manifest.loading && !m && <Loading what="the bundle" />}
        {m && tab === "Artifacts" && (
          <>
            <DataTable
              testid="bundle-files"
              columns={["Artifact", "Type", "Size", "SHA-256"]}
              rows={m.files.map((x) => [<code>{x.path}</code>, kind(x.path), `${x.size} B`, <code title={x.sha256}>{x.sha256.slice(0, 16)}</code>])}
            />
            <p className="panel-note">
              {m.files.length} file(s) are listed in the manifest.{" "}
              <a className="back-link" href={api.bundleUrl(witnessId)} data-testid="bundle-link">
                Download the bundle (zip)
              </a>
            </p>
          </>
        )}
        {m && tab === "Bundle manifest" && (
          <>
            <dl className="manifest-grid">
              {(
                [
                  ["Bundle schema version", m.schema_version],
                  ["Bundle id", m.bundle_id],
                  ["Created", m.created_at],
                  ["Mode", m.mode],
                  ["Finding / witness", `${short(f.finding_id.replace(/^fnd_/, ""), 12)} / ${short(witnessId.replace(/^wit_/, ""), 12)}`],
                  ["Oracle", m.oracle ? `${m.oracle.name} ${m.oracle.version}` : null],
                  ["Interaction", m.oracle?.entry_point ?? null],
                  ["Reference world", m.worlds?.reference ? short(m.worlds.reference, 20) : null],
                  ["Consumer world", m.worlds?.consumer ? short(m.worlds.consumer, 20) : null],
                  ["Artifact hash", m.artifact?.content_hash ? short(m.artifact.content_hash, 20) : null],
                  ["Six-run witness", m.run_summary ? `${m.run_summary.reference_passes} reference passes · ${m.run_summary.consumer_failures} consumer failures · all fresh: ${m.run_summary.all_fresh ? "yes" : "no"}` : null],
                  ["Signature", m.run_summary ? `${m.run_summary.signature.exc_type}: ${m.run_summary.signature.message_norm}` : null],
                ] as [string, string | null][]
              ).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v ?? "Not recorded"}</dd>
                </div>
              ))}
            </dl>
            {m.claim && (
              <>
                <p className="panel-copy">
                  <strong>What the bundle claims:</strong> {m.claim.statement}
                </p>
                <p className="panel-note">
                  <strong>What it does not claim:</strong> {m.claim.not_claimed.join(" · ")}
                </p>
              </>
            )}
          </>
        )}
        {m && tab === "Integrity" && (
          <div data-testid="integrity">
            <StateBlock tone={m.verified ? "good" : "warn"} label={m.verified ? "VERIFIED" : "NOT VERIFIED"} title={m.verified ? "The bundle passes every integrity check." : "The bundle failed verification."}>
              {m.verified
                ? `The verifier re-hashed all ${m.files.length} files against the manifest, checked the path rules and size limits, and confirmed that the recorded witness agrees with the contents.`
                : m.errors.join(" · ")}
            </StateBlock>
            <AppAction onClick={manifest.reload}>Validate again</AppAction>
          </div>
        )}
        {tab === "Replay" && (
          <div className="state-panel compact" data-testid="replay-note">
            <Status tone="neutral">{caps?.mode === "REPLAY" ? "RECORDED" : "COMMAND LINE"}</Status>
            <h2>Replay runs outside this interface.</h2>
            <p>
              Replaying a bundle re-executes its check in the sandbox and reports EXACT_REPRODUCTION, ENVIRONMENT_LIMITED or NON_REPRODUCIBLE with reasons. Run{" "}
              <code>python -m faultline.witnesses.replay bundle.zip</code> on a machine with Docker. The live re-run of a witness is available from the finding page.
            </p>
            <AppAction onClick={() => go("finding", f.finding_id)}>Open the finding</AppAction>
          </div>
        )}
        {!m && !manifest.loading && !manifest.error && <EmptyInline title="No bundle manifest is available" />}
      </Panel>
    </>
  );
}
