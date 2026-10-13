import { useEffect, useState } from "react";
import { api, type InventoryGraph } from "../api/client";
import { StateMessage } from "../components/StateMessage";

type Node = InventoryGraph["nodes"][number];
const COLUMNS: Record<string, number> = { repository: 20, project: 280, manifest: 560, package: 560 };
const COLOR: Record<string, string> = { ok: "var(--good)", unsupported: "var(--warn)", failed: "var(--bad)" };
const ROW = 34;

/** Repositories, their projects, manifests and top packages, producer/consumer edges with their evidence level, and unsupported
 *  nodes drawn dashed. Positions are computed from the persisted nodes; nothing is hard-coded. */
export function Inventory() {
  const [g, setG] = useState<InventoryGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    api
      .projects()
      .then((ps) => {
        if (!ps[0]) {
          setEmpty(true);
          return null;
        }
        return api.inventory(ps[0].id);
      })
      .then((x) => x && setG(x))
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <StateMessage view="inventory" kind="failed" detail={error} />;
  if (empty || (g && g.nodes.length === 0)) return <StateMessage view="inventory" kind="empty" detail="Add and ingest repositories first." />;
  if (!g) return <p className="muted">Loading…</p>;

  const pos = new Map<string, { x: number; y: number }>();
  let y = 20;
  const projectsOf = (rid: string) => g.edges.filter((e) => e.source === rid && e.kind === "contains").map((e) => e.target);
  const childrenOf = (pid: string) => g.edges.filter((e) => e.source === pid && e.kind === "declares").map((e) => e.target);
  for (const r of g.nodes.filter((n) => n.kind === "repository")) {
    pos.set(r.id, { x: COLUMNS.repository, y });
    for (const pid of projectsOf(r.id)) {
      pos.set(pid, { x: COLUMNS.project, y });
      const kids = childrenOf(pid);
      for (const k of kids) {
        pos.set(k, { x: COLUMNS.manifest, y });
        y += ROW;
      }
      if (kids.length === 0) y += ROW;
    }
    y += ROW / 2;
  }
  const byId = new Map<string, Node>(g.nodes.map((n) => [n.id, n]));
  const height = y + 20;
  return (
    <section className="panel" aria-label="Inventory graph" data-testid="inventory-graph">
      <h2>Inventory graph</h2>
      <p className="muted small">
        Repositories → projects → manifests and packages. Arcs on the left are producer → consumer relationships with their evidence level. Dashed nodes are
        unsupported or unreadable inputs: they are listed, not hidden.
      </p>
      <div className="table-wrap">
        <svg width={900} height={height} role="img" aria-label="Inventory graph">
          {g.edges
            .filter((e) => e.kind === "contains" || e.kind === "declares")
            .map((e, i) => {
              const a = pos.get(e.source);
              const b = pos.get(e.target);
              if (!a || !b) return null;
              return <line key={i} x1={a.x + 190} y1={a.y} x2={b.x} y2={b.y} stroke="var(--rule)" />;
            })}
          {g.edges
            .filter((e) => e.kind === "consumes" || e.kind === "suspected")
            .map((e, i) => {
              const a = pos.get(e.source);
              const b = pos.get(e.target);
              if (!a || !b) return null;
              const bow = 60 + (i % 3) * 20;
              return (
                <g key={`r${i}`} data-testid={`edge-${e.kind}`}>
                  <path d={`M ${a.x + 190} ${a.y} C ${a.x + 190 + bow} ${a.y} ${b.x - bow + 0} ${b.y} ${b.x} ${b.y}`} fill="none"
                    stroke={e.kind === "consumes" ? "var(--accent)" : "var(--warn)"} strokeWidth={2} strokeDasharray={e.kind === "suspected" ? "5 4" : undefined} />
                  <text x={(a.x + b.x) / 2 + 100} y={(a.y + b.y) / 2 - 4} fontSize="11" fill="var(--ink)">
                    {e.kind === "consumes" ? `${e.level} consumes` : `${e.level} suspected`}
                  </text>
                </g>
              );
            })}
          {[...pos.entries()].map(([id, p]) => {
            const n = byId.get(id)!;
            return (
              <g key={id} data-testid={`node-${n.kind}`} data-status={n.status}>
                <title>{`${n.kind}: ${n.label}${n.detail ? ` — ${n.detail}` : ""}`}</title>
                <rect x={p.x} y={p.y - 12} width={190} height={24} rx={5} fill="var(--surface)" stroke={COLOR[n.status] ?? "var(--rule)"}
                  strokeDasharray={n.status === "unsupported" ? "4 3" : undefined} strokeWidth={n.kind === "repository" ? 2 : 1} />
                <text x={p.x + 6} y={p.y + 4} fontSize="11" fill="var(--ink)">
                  {n.label.length > 28 ? n.label.slice(0, 27) + "…" : n.label}
                  {n.status === "unsupported" ? " · unsupported" : n.status === "failed" ? " · failed" : ""}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <ul className="small" data-testid="inventory-legend">
        {g.nodes
          .filter((n) => n.status !== "ok" || n.kind === "repository")
          .map((n) => (
            <li key={n.id}>
              <strong>{n.label}</strong> ({n.kind}
              {n.ecosystem ? `, ${n.ecosystem}` : ""}) — {n.status}
              {n.detail ? `: ${n.detail}` : ""}
            </li>
          ))}
      </ul>
    </section>
  );
}
