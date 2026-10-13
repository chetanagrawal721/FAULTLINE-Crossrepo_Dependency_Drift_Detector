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
export type FileView = components["schemas"]["FileView"];

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { Accept: "application/json" }, ...init });
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

export const api = {
  health: () => request<Health>("/api/health"),
  capabilities: () => request<Capabilities>("/api/capabilities"),
  scenarios: () => request<ScenarioInfo[]>("/api/scenarios"),
  runScenario: (id: string) => request<Job>(`/api/scenarios/${encodeURIComponent(id)}/run`, { method: "POST" }),
  job: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  findings: () => request<FindingSummary[]>("/api/findings"),
  finding: (id: string) => request<FindingDetail>(`/api/findings/${encodeURIComponent(id)}`),
  projects: () => request<ProjectView[]>("/api/projects?mode=LIVE"),
  createProject: (name: string) =>
    request<ProjectView>("/api/projects", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ name }) }),
  addRepository: (projectId: string, url: string, ref: string | null) =>
    request<RepositoryView>(`/api/projects/${encodeURIComponent(projectId)}/repositories`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ url, ref }),
    }),
  repository: (id: string) => request<RepositoryView>(`/api/repositories/${encodeURIComponent(id)}`),
  repositoryFiles: (id: string, role?: string) =>
    request<FileView[]>(`/api/repositories/${encodeURIComponent(id)}/files${role ? `?role=${encodeURIComponent(role)}` : ""}`),
  retryRepository: (id: string) => request<RepositoryView>(`/api/repositories/${encodeURIComponent(id)}/retry`, { method: "POST" }),
  analyzeRepository: (id: string) => request<Job>(`/api/repositories/${encodeURIComponent(id)}/analyze`, { method: "POST" }),
  repositoryProjects: (id: string) => request<ProjectDetail[]>(`/api/repositories/${encodeURIComponent(id)}/projects`),
  bundleUrl: (witnessId: string) => `/api/witnesses/${encodeURIComponent(witnessId)}/bundle`,
};
