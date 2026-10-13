import type { components } from "./schema";

export type Capabilities = components["schemas"]["Capabilities"];
export type Health = components["schemas"]["Health"];
export type CapabilityStatus = components["schemas"]["CapabilityStatus"];
export type EcosystemCapability = components["schemas"]["EcosystemCapability"];
export type Job = components["schemas"]["Job"];
export type ScenarioInfo = components["schemas"]["ScenarioInfo"];
export type FindingSummary = components["schemas"]["FindingSummary"];
export type FindingDetail = components["schemas"]["FindingDetail"];
export type RunView = components["schemas"]["RunView"];
export type WitnessView = components["schemas"]["WitnessView"];
export type ProjectView = components["schemas"]["ProjectView"];
export type RepositoryView = components["schemas"]["RepositoryView"];
export type ProjectDetail = components["schemas"]["ProjectDetail"];
export type WorldDetail = components["schemas"]["WorldDetail"];
export type InventoryDep = components["schemas"]["InventoryDep"];
export type PackageView = components["schemas"]["PackageView"];
export type AnalysisView = components["schemas"]["AnalysisView"];
export type CellView = components["schemas"]["CellView"];
export type RelationshipView = components["schemas"]["RelationshipView"];
export type InventoryGraph = components["schemas"]["InventoryGraph"];
export type WhyPath = components["schemas"]["WhyPath"];
export type FileView = components["schemas"]["FileView"];

/** What the bundle endpoint reports for a witness: the manifest, every file with its SHA-256, and the verifier's result. */
export type BundleManifest = {
  witness_id: string;
  verified: boolean;
  errors: string[];
  schema_version: string | null;
  bundle_id: string | null;
  created_at: string | null;
  mode: string | null;
  oracle: { name: string; version: string; entry_point: string } | null;
  worlds: { reference: string; consumer: string; env_profile: string } | null;
  artifact: { content_hash: string; source_dir: string } | null;
  run_summary: { reference_passes: number; consumer_failures: number; all_fresh: boolean; signature: { exc_type: string; message_norm: string } } | null;
  claim: { statement: string; not_claimed: string[] } | null;
  files: { path: string; sha256: string; size: number }[];
};

/** An API failure that keeps the machine-readable code, so the UI can show distinct states. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string | null,
    readonly retryable: boolean,
    readonly status: number,
  ) {
    super(message);
  }
}

const JSON_HEADERS = { Accept: "application/json", "Content-Type": "application/json" };
const TOKEN_KEY = "faultline-admin-token";

/** The admin token (when the server requires one) lives in this browser tab only and is sent as a bearer token on requests that start work. */
export const token = {
  get(): string | null {
    try {
      return window.sessionStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(value: string | null) {
    try {
      if (value) window.sessionStorage.setItem(TOKEN_KEY, value);
      else window.sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* storage can be blocked; the token then lasts only until the page reloads */
    }
  },
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const t = token.get();
  const headers: Record<string, string> = { Accept: "application/json", ...((init?.headers as Record<string, string>) ?? {}) };
  if (t && init?.method && init.method !== "GET") headers.Authorization = `Bearer ${t}`;
  const r = await fetch(path, { ...init, headers });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    let code: string | null = null;
    let retryable = false;
    try {
      const body = await r.json();
      msg = body?.error?.message ?? msg;
      code = body?.error?.code ?? null;
      retryable = Boolean(body?.error?.details?.retryable);
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(msg, code, retryable, r.status);
  }
  return (await r.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<Health>("/api/health"),
  capabilities: () => request<Capabilities>("/api/capabilities"),
  scenarios: () => request<ScenarioInfo[]>("/api/scenarios"),
  runScenario: (id: string) => request<Job>(`/api/scenarios/${enc(id)}/run`, { method: "POST" }),
  job: (id: string) => request<Job>(`/api/jobs/${enc(id)}`),
  jobs: (limit = 50) => request<Job[]>(`/api/jobs?limit=${limit}`),
  cancelJob: (id: string) => request<Job>(`/api/jobs/${enc(id)}/cancel`, { method: "POST" }),
  findings: (verdict?: string) => request<FindingSummary[]>(`/api/findings${verdict ? `?verdict=${enc(verdict)}` : ""}`),
  inventory: (id: string) => request<InventoryGraph>(`/api/projects/${enc(id)}/inventory`),
  whyPath: (id: string) => request<WhyPath>(`/api/findings/${enc(id)}/why-path`),
  finding: (id: string) => request<FindingDetail>(`/api/findings/${enc(id)}`),
  /** User-submitted (LIVE) projects, newest first. */
  projects: () => request<ProjectView[]>("/api/projects?mode=LIVE"),
  /** Every project, LIVE and the committed FIXTURE scenarios, newest first. */
  allProjects: () => request<ProjectView[]>("/api/projects"),
  project: (id: string) => request<ProjectView>(`/api/projects/${enc(id)}`),
  createProject: (name: string) => request<ProjectView>("/api/projects", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ name }) }),
  addRepository: (projectId: string, url: string, ref: string | null) =>
    request<RepositoryView>(`/api/projects/${enc(projectId)}/repositories`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ url, ref }) }),
  repository: (id: string) => request<RepositoryView>(`/api/repositories/${enc(id)}`),
  repositoryFiles: (id: string, role?: string) => request<FileView[]>(`/api/repositories/${enc(id)}/files${role ? `?role=${enc(role)}` : ""}`),
  retryRepository: (id: string) => request<RepositoryView>(`/api/repositories/${enc(id)}/retry`, { method: "POST" }),
  analyzeRepository: (id: string) => request<Job>(`/api/repositories/${enc(id)}/analyze`, { method: "POST" }),
  repositoryProjects: (id: string) => request<ProjectDetail[]>(`/api/repositories/${enc(id)}/projects`),
  analyzeProject: (id: string) => request<Job>(`/api/projects/${enc(id)}/analyze`, { method: "POST" }),
  projectAnalysis: (id: string) => request<AnalysisView>(`/api/projects/${enc(id)}/analysis`),
  analysis: (id: string) => request<AnalysisView>(`/api/analyses/${enc(id)}`),
  rerunWitness: (id: string) => request<Job>(`/api/witnesses/${enc(id)}/rerun`, { method: "POST" }),
  remediateFinding: (id: string) => request<Job>(`/api/findings/${enc(id)}/remediate`, { method: "POST" }),
  bundleUrl: (witnessId: string) => `/api/witnesses/${enc(witnessId)}/bundle`,
  bundleManifest: (witnessId: string) => request<BundleManifest>(`/api/witnesses/${enc(witnessId)}/bundle/manifest`),
};
