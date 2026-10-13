import { useMemo, useState } from "react";
import { api, type InventoryGraph } from "../../api/client";
import { useAsync } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Icon, Panel } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { Loading, StateBlock, StateNote } from "../shared";

type Go = (view: AppView, id?: string | null) => void;
type GNode = InventoryGraph["nodes"][number];
type EdgeMode = "all" | "observed" | "candidate";

const NODE_W = 20; // percent of the canvas, as in the design
const COLS: Record<string, number> = { repository: 2, project: 26, manifest: 52, package: 52 };
const ROW = 100;
const TOP = 46;
const MAX_MANIFESTS = 4;
const MAX_PACKAGES = 4;

const TYPE_LABEL: Record<string, string> = { repository: "Repository", project: "Project", manifest: "Manifest", package: "Package" };
const TONE: Record<string, string> = { repository: "repo", project: "consumer", manifest: "manifest", package: "package" };

function stateText(n: GNode): string {
  if (n.status === "unsupported") return n.detail ?? "Unsupported input";
  if (n.status === "failed") return n.detail ?? "Failed";
  if (n.kind === "repository") return n.detail ?? "Source pinned";
  return n.detail ?? "Inventory record";
}

export function InventoryView({ go }: { go: Go }) {
  const { project } = useWorkspace();
  const q = useAsync(() => (project ? api.inventory(project.id) : Promise.resolve(null)), [project?.id, project?.repositories.map((r) => r.status).join(",")]);
  const [query, setQuery] = useState("");
  const [edgeMode, setEdgeMode] = useState<EdgeMode>("all");
  const [selected, setSelected] = useState<string | null>(null);

  const layout = useMemo(() => {
    const g = q.data;
    if (!g) return null;
    const pos = new Map<string, { x: number; y: number }>();
    let y = TOP;
    const shown = new Set<string>();
    for (const r of g.nodes.filter((n) => n.kind === "repository")) {
      pos.set(r.id, { x: COLS.repository, y });
      shown.add(r.id);
      const projects = g.edges.filter((e) => e.source === r.id && e.kind === "contains").map((e) => e.target);
      let blockTop = y;
      for (const pid of projects) {
        pos.set(pid, { x: COLS.project, y: blockTop });
        shown.add(pid);
        const kids = g.edges.filter((e) => e.source === pid && e.kind === "declares").map((e) => e.target);
        const byId = new Map(g.nodes.map((n) => [n.id, n]));
        const manifests = kids.filter((k) => byId.get(k)?.kind === "manifest").slice(0, MAX_MANIFESTS);
        const packages = kids.filter((k) => byId.get(k)?.kind === "package").slice(0, MAX_PACKAGES);
        let ky = blockTop;
        for (const k of [...manifests, ...packages]) {
          pos.set(k, { x: COLS.manifest, y: ky });
          shown.add(k);
          ky += ROW;
        }
        blockTop = Math.max(blockTop + ROW, ky);
      }
      y = Math.max(y + ROW, blockTop) + 24;
    }
    return { pos, shown, height: y + 70 };
  }, [q.data]);

  if (!project) return <StateBlock label="NOTHING ANALYSED" title="No project exists yet." testid="inventory-empty">Add repositories first. This is not a clean result.<br /><AppAction onClick={() => go("new")}>New analysis</AppAction></StateBlock>;
  if (q.error) return <StateNote view="inventory" kind="failed" detail={q.error} />;
  if (!q.data || !layout) return <Loading what="the inventory graph" />;
  const g = q.data;
  if (g.nodes.length === 0) return <StateNote view="inventory" kind="empty" detail="Repositories appear here once they are pinned and fetched." />;

  const nodes = g.nodes.filter((n) => layout.shown.has(n.id));
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const visible = (n: GNode) => `${n.label} ${n.kind} ${n.detail ?? ""} ${n.ecosystem ?? ""}`.toLowerCase().includes(query.toLowerCase());
  const kindOf = (k: string): "observed" | "candidate" => (k === "suspected" ? "candidate" : "observed");
  const edges = g.edges.filter((e) => layout.pos.has(e.source) && layout.pos.has(e.target) && (edgeMode === "all" || kindOf(e.kind) === edgeMode));
  const observed = g.edges.filter((e) => kindOf(e.kind) === "observed").length;
  const candidate = g.edges.length - observed;
  const active = (selected && byId.get(selected)) || nodes[0];
  const activeIndex = Math.max(0, nodes.findIndex((n) => n.id === active.id));
  const W = 1000;
  const H = layout.height;
  const px = (pct: number) => (pct / 100) * W;
  const nodeH = 82;

  const edgePath = (e: InventoryGraph["edges"][number], i: number) => {
    const a = layout.pos.get(e.source)!;
    const b = layout.pos.get(e.target)!;
    if (e.kind === "consumes" || e.kind === "suspected") {
      const x = px(a.x + NODE_W);
      const bow = 70 + (i % 3) * 22;
      return { d: `M ${x} ${a.y + nodeH / 2} C ${x + bow} ${a.y + nodeH / 2}, ${x + bow} ${b.y + nodeH / 2}, ${x} ${b.y + nodeH / 2}`, x: x + bow * 0.78, y: (a.y + b.y) / 2 + nodeH / 2 };
    }
    const x1 = px(a.x + NODE_W);
    const x2 = px(b.x);
    return { d: `M ${x1} ${a.y + nodeH / 2} C ${x1 + 30} ${a.y + nodeH / 2}, ${x2 - 30} ${b.y + nodeH / 2}, ${x2} ${b.y + nodeH / 2}`, x: (x1 + x2) / 2, y: (a.y + b.y) / 2 + nodeH / 2 - 8 };
  };

  return (
    <div className="dependency-page">
      <div className="dependency-toolbar">
        <label className="dependency-search">
          <Icon name="search" size={17} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search repositories, packages, manifests…" aria-label="Search the graph" />
        </label>
        <div className="dependency-toolbar-actions">
          <select aria-label="Edge filter" value={edgeMode} onChange={(e) => setEdgeMode(e.target.value as EdgeMode)}>
            <option value="all">All relationships</option>
            <option value="observed">Observed only</option>
            <option value="candidate">Candidate only</option>
          </select>
          <AppAction
            quiet
            onClick={() => {
              setQuery("");
              setEdgeMode("all");
              setSelected(null);
            }}
          >
            Reset view
          </AppAction>
        </div>
      </div>
      <div className="dependency-summary">
        <div>
          <span>VISIBLE NODES</span>
          <strong>{nodes.filter(visible).length.toString().padStart(2, "0")}</strong>
        </div>
        <div>
          <span>OBSERVED EDGES</span>
          <strong>{String(observed).padStart(2, "0")}</strong>
        </div>
        <div>
          <span>CANDIDATE EDGES</span>
          <strong>{String(candidate).padStart(2, "0")}</strong>
        </div>
        <div>
          <span>DATA SCOPE</span>
          <strong>{project.mode === "FIXTURE" ? "Fixture" : "Persisted"}</strong>
        </div>
      </div>
      <div className="dependency-layout">
        <Panel title="Dependency graph" meta={`${project.name} · persisted inventory`}>
          <div className="dependency-canvas" data-testid="inventory-graph" style={{ minHeight: H, height: H }}>
            <div className="dependency-lane lane-source" style={{ left: "2%" }}>REPOSITORIES</div>
            <div className="dependency-lane lane-consumer" style={{ left: "26%" }}>PROJECTS</div>
            <div className="dependency-lane lane-world" style={{ left: "52%" }}>MANIFESTS & RESOLVED PACKAGES</div>
            <svg className="dependency-edges" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
              {edges.map((e, i) => {
                const p = edgePath(e, i);
                return (
                  <g key={i} className={`dependency-edge ${kindOf(e.kind)}`} data-testid={`edge-${e.kind}`}>
                    <path d={p.d} />
                    {(e.kind === "consumes" || e.kind === "suspected") && (
                      <text x={p.x} y={p.y}>
                        {e.level} {e.kind}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
            {nodes.map((n) => {
              const p = layout.pos.get(n.id)!;
              return (
                <button
                  key={n.id}
                  className={`dependency-node ${TONE[n.kind] ?? "manifest"} ${active.id === n.id ? "selected" : ""} ${visible(n) ? "" : "filtered-out"}`}
                  style={{ left: `${p.x}%`, top: p.y, width: `${NODE_W}%`, ...(n.status === "unsupported" ? { borderStyle: "dashed" } : {}) }}
                  onClick={() => setSelected(n.id)}
                  aria-pressed={active.id === n.id}
                  data-testid={`node-${n.kind}`}
                  data-status={n.status}
                  title={`${n.kind}: ${n.label}${n.detail ? ` — ${n.detail}` : ""}`}
                >
                  <span className="dependency-node-type">{TYPE_LABEL[n.kind] ?? n.kind}</span>
                  <strong>{n.label}</strong>
                  <code>{n.ecosystem ?? ""}</code>
                  <small>
                    <i />
                    {stateText(n)}
                  </small>
                </button>
              );
            })}
            <div className="dependency-canvas-footer">
              <span>
                <i className="edge-key observed-key" />
                Observed relationship
              </span>
              <span>
                <i className="edge-key candidate-key" />
                Candidate relationship
              </span>
              <span>A connection is not a confirmed breakage</span>
            </div>
          </div>
        </Panel>
        <aside className="dependency-inspector">
          <div className="dependency-inspector-head">
            <span>SELECTED NODE</span>
            <span className="inspector-index">NODE / {String(activeIndex + 1).padStart(2, "0")}</span>
          </div>
          <span className={`dependency-type-chip ${TONE[active.kind] ?? "manifest"}`}>{TYPE_LABEL[active.kind] ?? active.kind}</span>
          <h3>{active.label}</h3>
          <code>{active.ecosystem ?? active.kind}</code>
          <div className="inspector-divider" />
          <span className="inspector-label">Inventory state</span>
          <p>{stateText(active)}</p>
          <span className="inspector-label">Interpretation</span>
          <p>This graph is read from persisted inventory and relationship records. A relationship shown here says what evidence was found; it does not say that anything is broken.</p>
          <div className="inspector-actions">
            <AppAction quiet onClick={() => go(active.kind === "repository" ? "repository" : "relationships", active.kind === "repository" ? active.id.replace(/^repo:/, "") : undefined)}>
              Inspect related records <Icon name="arrow" size={15} />
            </AppAction>
          </div>
        </aside>
      </div>
      <Panel title="Graph inventory" meta="Every node, including those not drawn">
        <div data-testid="inventory-legend">
          <DataTable columns={["Node", "Type", "State", "Detail"]} rows={g.nodes.map((n) => [n.label, `${TYPE_LABEL[n.kind] ?? n.kind}${n.ecosystem ? ` · ${n.ecosystem}` : ""}`, n.status, n.detail ?? ""])} />
        </div>
      </Panel>
    </div>
  );
}
