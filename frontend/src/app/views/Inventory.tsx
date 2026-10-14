import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { api, type InventoryGraph } from "../../api/client";
import { useAsync } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Icon, Panel } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { Loading, StateBlock, StateNote } from "../shared";

type Go = (view: AppView, id?: string | null) => void;
type GNode = InventoryGraph["nodes"][number];
type GEdge = InventoryGraph["edges"][number];
type EdgeMode = "all" | "observed" | "candidate";
type View = { x: number; y: number; k: number; animate: boolean };

const NODE_W = 196;
const NODE_H = 60;
const COL_GAP = 64;
const ROW_GAP = 12;
const PAD = 36;
const HEAD = 30;
const MIN_K = 0.15;
const MAX_K = 2.5;
const MIN_FIT = 0.5;
const MINIMAP_W = 190;
const MINIMAP_H = 120;
const LAYERS = ["repository", "project", "manifest", "package"] as const;
const LAYER_TITLE: Record<string, string> = { repository: "Repositories", project: "Projects", manifest: "Manifests", package: "Resolved packages" };
const TYPE_LABEL: Record<string, string> = { repository: "Repository", project: "Project", manifest: "Manifest", package: "Package" };

function stateText(n: GNode): string {
  if (n.status === "unsupported") return n.detail ?? "Unsupported input";
  if (n.status === "failed") return n.detail ?? "Failed";
  if (n.kind === "repository") return n.detail ?? "Source pinned";
  return n.detail ?? "Inventory record";
}

const kindOf = (k: string): "observed" | "candidate" => (k === "suspected" ? "candidate" : "observed");

type Placed = { id: string; x: number; y: number };
type Layout = { pos: Map<string, Placed>; width: number; height: number; heads: { title: string; x: number }[]; rows: number };

/** Layers left to right (repository, project, manifest, package). A layer with many nodes is wrapped into several columns of at most `rows`
 *  nodes, and nodes are ordered so that children sit next to their parent. */
function layoutGraph(nodes: GNode[], edges: GEdge[], rows: number): Layout {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const children = new Map<string, string[]>();
  for (const e of edges) {
    if (e.kind === "contains" || e.kind === "declares") children.set(e.source, [...(children.get(e.source) ?? []), e.target]);
  }
  const order: string[] = [];
  const seen = new Set<string>();
  const visit = (id: string) => {
    if (seen.has(id) || !byId.has(id)) return;
    seen.add(id);
    order.push(id);
    for (const c of children.get(id) ?? []) visit(c);
  };
  for (const n of nodes.filter((n) => n.kind === "repository")) visit(n.id);
  for (const n of nodes) visit(n.id);
  const layers = LAYERS.map((kind) => order.filter((id) => byId.get(id)?.kind === kind)).filter((l) => l.length > 0);
  const pos = new Map<string, Placed>();
  const heads: { title: string; x: number }[] = [];
  const maxRows = Math.max(1, ...layers.map((l) => Math.min(rows, l.length)));
  let x = PAD;
  for (const ids of layers) {
    const cols = Math.ceil(ids.length / rows);
    const per = Math.ceil(ids.length / cols);
    const top = PAD + HEAD + ((maxRows - per) * (NODE_H + ROW_GAP)) / 2;
    heads.push({ title: LAYER_TITLE[byId.get(ids[0])!.kind] ?? "", x });
    ids.forEach((id, i) => pos.set(id, { id, x: x + Math.floor(i / per) * (NODE_W + 28), y: top + (i % per) * (NODE_H + ROW_GAP) }));
    x += cols * NODE_W + (cols - 1) * 28 + COL_GAP;
  }
  return { pos, width: x - COL_GAP + PAD, height: PAD + HEAD + maxRows * (NODE_H + ROW_GAP) - ROW_GAP + PAD, heads, rows: maxRows };
}

/** Pick the wrapping that lets the whole graph be shown at the largest scale in a canvas of this shape. */
function bestLayout(nodes: GNode[], edges: GEdge[], cw: number, ch: number): Layout {
  let best: { l: Layout; k: number } | null = null;
  for (let rows = 5; rows <= 24; rows++) {
    const l = layoutGraph(nodes, edges, rows);
    const k = Math.min(cw / l.width, ch / l.height);
    if (!best || k > best.k + 0.005) best = { l, k };
  }
  return best!.l;
}

function edgeGeometry(a: Placed, b: Placed, i: number) {
  const ay = a.y + NODE_H / 2;
  const by = b.y + NODE_H / 2;
  if (b.x > a.x + NODE_W / 2 + 10) {
    const x1 = a.x + NODE_W;
    const x2 = b.x;
    const dx = Math.max(24, Math.abs(x2 - x1) / 2);
    return { d: `M ${x1} ${ay} C ${x1 + dx} ${ay}, ${x2 - dx} ${by}, ${x2} ${by}`, lx: (x1 + x2) / 2, ly: (ay + by) / 2 - 5 };
  }
  const x = Math.max(a.x, b.x) + NODE_W;                       // same layer: an arc on the right-hand side
  const bow = 46 + (i % 3) * 14;
  return { d: `M ${x} ${ay} C ${x + bow} ${ay}, ${x + bow} ${by}, ${x} ${by}`, lx: x + bow * 0.78, ly: (ay + by) / 2 };
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function InventoryView({ go }: { go: Go }) {
  const { project, replay } = useWorkspace();
  const q = useAsync(() => (project ? api.inventory(project.id) : Promise.resolve(null)), [project?.id, project?.repositories.map((r) => r.status).join(",")]);
  const [query, setQuery] = useState("");
  const [edgeMode, setEdgeMode] = useState<EdgeMode>("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [focusOn, setFocusOn] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1, animate: false });
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [dragging, setDragging] = useState(false);
  const canvas = useRef<HTMLDivElement>(null);
  const drag = useRef<{ sx: number; sy: number; vx: number; vy: number; moved: boolean } | null>(null);
  const fittedFor = useRef<string | null>(null);
  const noticeTimer = useRef<number | null>(null);

  const say = useCallback((text: string) => {
    setNotice(text);
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 4500);
  }, []);
  useEffect(() => () => { if (noticeTimer.current) window.clearTimeout(noticeTimer.current); }, []);

  const data = q.data;
  const layout = useMemo(() => (data && size.w > 0 ? bestLayout(data.nodes, data.edges, size.w - 24, size.h - 24) : null), [data, size.w > 0, Math.round(size.w / 80), Math.round(size.h / 80)]); // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const read = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    read();
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, [data]);

  const fitBox = useCallback((x: number, y: number, w: number, h: number, minK: number, maxK: number, animate = true) => {
    if (size.w === 0) return;
    const k = clamp(Math.min((size.w - 32) / w, (size.h - 32) / h), minK, maxK);
    setView({ k, x: size.w / 2 - (x + w / 2) * k, y: size.h / 2 - (y + h / 2) * k, animate });
  }, [size.w, size.h]);

  const fitAll = useCallback((animate = true) => {
    if (!layout || size.w === 0) return;
    const k = clamp(Math.min((size.w - 24) / layout.width, (size.h - 24) / layout.height), MIN_FIT, 1);
    const fitsW = layout.width * k <= size.w;
    const fitsH = layout.height * k <= size.h;
    setView({ k, animate, x: fitsW ? (size.w - layout.width * k) / 2 : 12, y: fitsH ? (size.h - layout.height * k) / 2 : 12 });
  }, [layout, size.w, size.h]);

  useEffect(() => {
    if (layout && project && fittedFor.current !== `${project.id}:${layout.width}x${layout.height}`) {
      fittedFor.current = `${project.id}:${layout.width}x${layout.height}`;
      fitAll(false);
    }
  }, [layout, project, fitAll]);

  const zoomAt = useCallback((factor: number, cx: number, cy: number) => {
    setView((v) => {
      const k = clamp(v.k * factor, MIN_K, MAX_K);
      return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k, animate: false };
    });
  }, []);
  const zoomBy = (factor: number) => {
    setView((v) => {
      const k = clamp(v.k * factor, MIN_K, MAX_K);
      const cx = size.w / 2;
      const cy = size.h / 2;
      return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k, animate: true };
    });
  };

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;                          // a plain wheel keeps scrolling the page
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomAt(Math.exp(-e.deltaY * 0.0022), e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt, data]);

  if (!project) return <StateBlock label="NOTHING ANALYSED" title="No project exists yet." testid="inventory-empty">Add repositories first. This is not a clean result.<br /><AppAction onClick={() => go("new")}>New analysis</AppAction></StateBlock>;
  if (q.error) return <StateNote view="inventory" kind="failed" detail={q.error} />;
  if (!data) return <Loading what="the inventory graph" />;
  const g = data;
  if (g.nodes.length === 0) return <StateNote view="inventory" kind="empty" detail="Repositories appear here once they are pinned and fetched." />;

  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const edgesAll = g.edges.filter((e) => byId.has(e.source) && byId.has(e.target));
  const edges = edgesAll.filter((e) => edgeMode === "all" || kindOf(e.kind) === edgeMode);
  const needle = query.trim().toLowerCase();
  const matches = (n: GNode) => !needle || `${n.label} ${n.kind} ${n.detail ?? ""} ${n.ecosystem ?? ""}`.toLowerCase().includes(needle);
  const matched = g.nodes.filter(matches);
  const observed = g.edges.filter((e) => kindOf(e.kind) === "observed").length;
  const candidate = g.edges.length - observed;
  const active = selected ? byId.get(selected) ?? null : null;
  const neighbours = new Set<string>();
  if (active) {
    neighbours.add(active.id);
    for (const e of edgesAll) {
      if (e.source === active.id) neighbours.add(e.target);
      if (e.target === active.id) neighbours.add(e.source);
    }
  }
  const dim = (id: string) => (needle && !matches(byId.get(id)!)) || (active && focusOn && !neighbours.has(id));
  const connections = active
    ? edgesAll.filter((e) => e.source === active.id || e.target === active.id).map((e) => ({ e, other: byId.get(e.source === active.id ? e.target : e.source)!, out: e.source === active.id }))
    : [];

  const centerOn = (id: string) => {
    const p = layout?.pos.get(id);
    if (!p) return;
    setView((v) => {
      const k = Math.max(v.k, 0.8);
      return { k, x: size.w / 2 - (p.x + NODE_W / 2) * k, y: size.h / 2 - (p.y + NODE_H / 2) * k, animate: true };
    });
  };
  const select = (id: string | null, center = false) => {
    setSelected(id);
    if (id && center) centerOn(id);
  };
  const focusConnections = () => {
    if (!active || !layout) {
      say("Select a node first, then focus on its connections.");
      return;
    }
    const ps = [...neighbours].map((id) => layout.pos.get(id)).filter((p): p is Placed => !!p);
    const x0 = Math.min(...ps.map((p) => p.x));
    const y0 = Math.min(...ps.map((p) => p.y));
    const x1 = Math.max(...ps.map((p) => p.x + NODE_W));
    const y1 = Math.max(...ps.map((p) => p.y + NODE_H));
    setFocusOn(true);
    fitBox(x0 - 30, y0 - 30, x1 - x0 + 60, y1 - y0 + 60, 0.6, 1.25);
    say(`Showing ${active.label} and its ${neighbours.size - 1} connected node${neighbours.size === 2 ? "" : "s"}.`);
  };
  const resetView = () => {
    setQuery("");
    setEdgeMode("all");
    setSelected(null);
    setFocusOn(true);
    setAddOpen(false);
    fitAll(true);
    say("View reset: the whole graph is fitted, and the search, filter and selection are cleared.");
  };

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest(".ig-node, .ig-controls, .ig-minimap, .ig-notice")) return;
    drag.current = { sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(true);
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.sx;
    const dy = e.clientY - d.sy;
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy, animate: false }));
  };
  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    setDragging(false);
    if (d && !d.moved) setSelected(null);                         // a click on the empty canvas clears the selection
  };
  const onKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const step = 60;
    if (e.key === "+" || e.key === "=") zoomBy(1.25);
    else if (e.key === "-") zoomBy(0.8);
    else if (e.key === "0") fitAll();
    else if (e.key === "Escape") setSelected(null);
    else if (e.key === "ArrowLeft") setView((v) => ({ ...v, x: v.x + step, animate: false }));
    else if (e.key === "ArrowRight") setView((v) => ({ ...v, x: v.x - step, animate: false }));
    else if (e.key === "ArrowUp") setView((v) => ({ ...v, y: v.y + step, animate: false }));
    else if (e.key === "ArrowDown") setView((v) => ({ ...v, y: v.y - step, animate: false }));
    else return;
    e.preventDefault();
  };

  const worldW = layout?.width ?? 0;
  const worldH = layout?.height ?? 0;
  const showMinimap = !!layout && (worldW > size.w || worldH > size.h);
  const ms = layout ? Math.min(MINIMAP_W / worldW, MINIMAP_H / worldH) : 1;
  const miniTo = (e: ReactPointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const wx = (e.clientX - r.left - (MINIMAP_W - worldW * ms) / 2) / ms;
    const wy = (e.clientY - r.top - (MINIMAP_H - worldH * ms) / 2) / ms;
    setView((v) => ({ ...v, x: size.w / 2 - wx * v.k, y: size.h / 2 - wy * v.k, animate: false }));
  };
  const vis = layout ? { x: -view.x / view.k, y: -view.y / view.k, w: size.w / view.k, h: size.h / view.k } : null;
  const lod = view.k < 0.62 ? "far" : view.k < 0.9 ? "mid" : "near";

  return (
    <div className="dependency-page ig-page">
      <div className="ig-toolbar">
        <label className="ig-search">
          <Icon name="search" size={16} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const first = matched[0];
                if (first && needle) {
                  select(first.id, true);
                  say(`${matched.length} match${matched.length === 1 ? "" : "es"}. Showing the first: ${first.label}.`);
                } else if (needle) say("No node matches this search.");
              }
            }}
            placeholder="Search repositories, packages, manifests"
            aria-label="Search the graph"
          />
          {needle && <span className="ig-count">{matched.length} of {g.nodes.length}</span>}
        </label>
        <select aria-label="Edge filter" value={edgeMode} onChange={(e) => setEdgeMode(e.target.value as EdgeMode)}>
          <option value="all">All relationships</option>
          <option value="observed">Observed only</option>
          <option value="candidate">Candidate only</option>
        </select>
        <AppAction quiet onClick={resetView}>
          Reset view
        </AppAction>
        <AppAction quiet onClick={() => setAddOpen(!addOpen)} expanded={addOpen}>
          Add relationship
        </AppAction>
      </div>
      {addOpen && (
        <div className="ig-add" role="region" aria-label="Add a relationship" data-testid="add-relationship">
          <div>
            <strong>Relationships are found from evidence, not drawn by hand.</strong>
            <p>
              A link appears here when a manifest or lockfile shows that one project consumes another. To add a connection, add the repository that holds the evidence and analyse again.
              {replay ? " This deployment shows recorded evidence only, so nothing can be added." : ""}
            </p>
          </div>
          <div className="ig-add-actions">
            <AppAction onClick={() => go("new")} disabled={replay} reason="This deployment shows recorded evidence only, so nothing can be added.">
              Add a repository
            </AppAction>
            <AppAction quiet onClick={() => go("relationships")}>
              Review relationships
            </AppAction>
            <AppAction quiet onClick={() => setAddOpen(false)}>
              Close
            </AppAction>
          </div>
        </div>
      )}
      <div className="ig-summary">
        <div><span>Visible nodes</span><strong>{matched.length}</strong></div>
        <div><span>Observed edges</span><strong>{observed}</strong></div>
        <div><span>Candidate edges</span><strong>{candidate}</strong></div>
        <div><span>Data scope</span><strong>{project.mode === "FIXTURE" ? "Fixture" : "Persisted"}</strong></div>
      </div>
      <div className="ig-layout">
        <section className="ig-stage" aria-label="Dependency graph">
          <div className="ig-stage-head">
            <h3>Dependency graph</h3>
            <span>{project.name} · persisted inventory</span>
          </div>
          <div
            className={`ig-canvas lod-${lod}${dragging ? " is-dragging" : ""}`}
            ref={canvas}
            data-testid="inventory-graph"
            tabIndex={0}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onKeyDown={onKey}
            aria-describedby="ig-hint"
          >
            {layout && (
              <div className="ig-world" style={{ width: worldW, height: worldH, transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`, transition: view.animate ? "transform .28s ease" : "none" }}>
                {layout.heads.map((h) => (
                  <span className="ig-lane" key={h.title} style={{ left: h.x, top: PAD - 4 }}>{h.title}</span>
                ))}
                <svg className="ig-edges" width={worldW} height={worldH} viewBox={`0 0 ${worldW} ${worldH}`} aria-hidden="true">
                  {edges.map((e, i) => {
                    const a = layout.pos.get(e.source);
                    const b = layout.pos.get(e.target);
                    if (!a || !b) return null;
                    const p = edgeGeometry(a, b, i);
                    const related = active && (e.source === active.id || e.target === active.id);
                    const faded = active && focusOn && !related;
                    return (
                      <g key={i} className={`ig-edge ${kindOf(e.kind)}${related ? " is-related" : ""}${faded ? " is-faded" : ""}`} data-testid={`edge-${e.kind}`}>
                        <path d={p.d} />
                        {(e.kind === "consumes" || e.kind === "suspected") && (
                          <text x={p.lx} y={p.ly}>
                            {e.level} {e.kind}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </svg>
                {g.nodes.map((n) => {
                  const p = layout.pos.get(n.id);
                  if (!p) return null;
                  return (
                    <button
                      key={n.id}
                      className={`ig-node t-${n.kind}${active?.id === n.id ? " is-selected" : ""}${dim(n.id) ? " is-dim" : ""}${active && neighbours.has(n.id) && active.id !== n.id ? " is-linked" : ""}`}
                      style={{ left: p.x, top: p.y, width: NODE_W, height: NODE_H, ...(n.status === "unsupported" ? { borderStyle: "dashed" } : {}) }}
                      onClick={() => select(n.id)}
                      onDoubleClick={() => { select(n.id); setTimeout(focusConnections, 0); }}
                      aria-pressed={active?.id === n.id}
                      data-testid={`node-${n.kind}`}
                      data-status={n.status}
                      title={`${TYPE_LABEL[n.kind] ?? n.kind}: ${n.label}${n.detail ? ` · ${n.detail}` : ""}`}
                    >
                      <strong>{n.label}</strong>
                      <span className="ig-meta">{TYPE_LABEL[n.kind] ?? n.kind}{n.ecosystem ? ` · ${n.ecosystem}` : ""}</span>
                      <small className="ig-detail">{stateText(n)}</small>
                    </button>
                  );
                })}
              </div>
            )}
            <div className="ig-controls" role="toolbar" aria-label="Graph view controls">
              <button type="button" onClick={() => zoomBy(1.25)} aria-label="Zoom in" title="Zoom in (+)" disabled={view.k >= MAX_K}>
                <Icon name="plus" size={16} />
              </button>
              <button type="button" onClick={() => zoomBy(0.8)} aria-label="Zoom out" title="Zoom out (-)" disabled={view.k <= MIN_K}>
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="M5 12h14" /></svg>
              </button>
              <button type="button" onClick={() => { fitAll(); say("The whole graph is fitted to the canvas."); }} aria-label="Fit to screen" title="Fit to screen (0)">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
              </button>
              <button type="button" onClick={focusConnections} aria-label="Focus on the selected node's connections" aria-pressed={!!active && focusOn} title={active ? "Focus on the selected node's connections" : "Select a node to focus on its connections"} className={active ? "" : "is-idle"}>
                <Icon name="graph" size={16} />
              </button>
              <output className="ig-zoom" aria-label="Zoom level">{Math.round(view.k * 100)}%</output>
            </div>
            {showMinimap && layout && vis && (
              <div className="ig-minimap" role="img" aria-label="Minimap. Drag to move the view." style={{ width: MINIMAP_W, height: MINIMAP_H }}
                onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); miniTo(e); }}
                onPointerMove={(e) => { if (e.buttons === 1) miniTo(e); }}>
                <svg width={MINIMAP_W} height={MINIMAP_H} aria-hidden="true">
                  <g transform={`translate(${(MINIMAP_W - worldW * ms) / 2} ${(MINIMAP_H - worldH * ms) / 2}) scale(${ms})`}>
                    {g.nodes.map((n) => {
                      const p = layout.pos.get(n.id);
                      return p ? <rect key={n.id} x={p.x} y={p.y} width={NODE_W} height={NODE_H} className={`mm t-${n.kind}${active?.id === n.id ? " is-selected" : ""}`} /> : null;
                    })}
                    <rect className="mm-view" x={vis.x} y={vis.y} width={vis.w} height={vis.h} />
                  </g>
                </svg>
              </div>
            )}
            <div className="ig-legend" aria-hidden="true">
              <span><i className="edge-key observed-key" />Observed</span>
              <span><i className="edge-key candidate-key" />Candidate</span>
            </div>
            {notice && <div className="ig-notice" role="status" aria-live="polite">{notice}</div>}
          </div>
          <p className="ig-hint" id="ig-hint">Drag to pan. Ctrl and wheel, or the buttons, to zoom. Select a node to highlight what it connects to. A connection is not a confirmed breakage.</p>
        </section>
        <aside className="ig-inspector" aria-label="Selected node">
          {active ? (
            <>
              <div className="ig-inspector-head">
                <span>Selected node</span>
                <button type="button" className="ig-clear" onClick={() => select(null)}>Clear</button>
              </div>
              <span className={`ig-chip t-${active.kind}`}>{TYPE_LABEL[active.kind] ?? active.kind}</span>
              <h3>{active.label}</h3>
              <code>{active.ecosystem ?? active.kind}</code>
              <span className="ig-label">Inventory state</span>
              <p>{stateText(active)}</p>
              <span className="ig-label">Connections ({connections.length})</span>
              {connections.length === 0 ? (
                <p>No relationship is recorded for this node.</p>
              ) : (
                <ul className="ig-connections">
                  {connections.map(({ e, other, out }, i) => (
                    <li key={i}>
                      <button type="button" onClick={() => select(other.id, true)} title={`Show ${other.label}`}>
                        <span className="ig-dir">{out ? "to" : "from"}</span>
                        <span className="ig-conn-label">{other.label}</span>
                        <small>{e.kind}{e.level ? ` · ${e.level}` : ""}</small>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <span className="ig-label">Interpretation</span>
              <p>This graph is read from persisted inventory and relationship records. A relationship shown here says what evidence was found; it does not say that anything is broken.</p>
              <div className="inspector-actions">
                <AppAction quiet onClick={() => go(active.kind === "repository" ? "repository" : "relationships", active.kind === "repository" ? active.id.replace(/^repo:/, "") : undefined)}>
                  Inspect related records <Icon name="arrow" size={15} />
                </AppAction>
              </div>
            </>
          ) : (
            <div className="ig-inspector-empty">
              <span className="ig-label">Selected node</span>
              <h3>Nothing selected</h3>
              <p>Select a node in the graph or a row in the table to see its state and what it is connected to.</p>
              <p>{g.nodes.length} nodes and {g.edges.length} relationships are recorded for this project.</p>
            </div>
          )}
        </aside>
      </div>
      <Panel title="Graph inventory" meta={`${g.nodes.length} nodes, including any not in view`}>
        <div className="ig-table" data-testid="inventory-legend">
          <DataTable
            columns={["Node", "Type", "State", "Detail"]}
            rows={g.nodes.map((n) => [n.label, `${TYPE_LABEL[n.kind] ?? n.kind}${n.ecosystem ? ` · ${n.ecosystem}` : ""}`, n.status, n.detail ?? ""])}
            onRow={(i) => {
              const n = g.nodes[i];
              if (n) {
                select(n.id, true);
                canvas.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
                say(`Showing ${n.label} in the graph.`);
              }
            }}
          />
        </div>
      </Panel>
    </div>
  );
}
