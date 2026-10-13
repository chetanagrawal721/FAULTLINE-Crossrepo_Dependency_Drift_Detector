import type { Capabilities, CapabilityStatus } from "../api/client";

function Pill({ s }: { s: CapabilityStatus }) {
  return (
    <span className={`pill pill-${s.state}`} title={s.reason ?? undefined}>
      {s.state}
    </span>
  );
}

const DIMS = [
  ["inventory", "Inventory"],
  ["resolve", "Resolve"],
  ["world", "World"],
  ["runtime_witness", "Runtime witness"],
] as const;

/** Shows what Faultline can and cannot do right now, with the reason for every disabled capability. */
export function CapabilityBanner({ caps }: { caps: Capabilities }) {
  return (
    <section className="panel" aria-label="Capabilities" data-testid="capability-banner">
      <h2>Capabilities</h2>
      <p className={`sandbox sandbox-${caps.sandbox.state}`} data-testid="sandbox-state">
        <strong>Sandbox: {caps.sandbox.state}</strong>
        {" · "}
        {caps.sandbox.verified ? "isolation verified" : "isolation not verified"}
        <span className="muted"> — {caps.sandbox.reason}</span>
      </p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ecosystem</th>
              {DIMS.map(([, label]) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {caps.ecosystems.map((e) => (
              <tr key={e.ecosystem}>
                <th scope="row">{e.ecosystem}</th>
                {DIMS.map(([key]) => (
                  <td key={key}>
                    <Pill s={e[key]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Oracles</h3>
      <ul className="chips">
        {Object.entries(caps.oracles).map(([name, s]) => (
          <li key={name} title={s.reason ?? undefined}>
            <code>{name}</code> <Pill s={s} />
          </li>
        ))}
      </ul>

      <h3>Features</h3>
      <ul className="chips">
        {Object.entries(caps.features).map(([name, s]) => (
          <li key={name} title={s.reason ?? undefined}>
            <code>{name.replaceAll("_", " ")}</code> <Pill s={s} />
          </li>
        ))}
      </ul>
      <p className="muted small">Hover a status for the reason. Capability version {caps.capability_version}.</p>
    </section>
  );
}
