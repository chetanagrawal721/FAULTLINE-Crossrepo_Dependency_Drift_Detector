import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, api, type AnalysisView, type Capabilities, type Health, type ProjectView } from "../api/client";
import { useAsync } from "../lib/hooks";

type Workspace = {
  caps: Capabilities | null;
  health: Health | null;
  apiError: string | null;
  projects: ProjectView[];
  project: ProjectView | null;
  setProjectId: (id: string) => void;
  analysis: AnalysisView | null;
  analysisLoading: boolean;
  analysisError: string | null;
  reload: () => void;
  replay: boolean;
};

const Ctx = createContext<Workspace | null>(null);
const ACTIVE_KEY = "faultline-active-project";

export const useWorkspace = (): Workspace => {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be used inside the workspace");
  return v;
};

/** Everything the workspace views share: what the deployment can do, the projects, and the analysis of the project being looked at. */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const meta = useAsync(() => Promise.all([api.capabilities(), api.health()]), []);
  const projectsQ = useAsync(() => api.allProjects(), []);
  const projects = projectsQ.data ?? [];
  const [chosen, setChosen] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(ACTIVE_KEY);
    } catch {
      return null;
    }
  });
  const project = useMemo(() => {
    if (projects.length === 0) return null;
    // the project the person picked, else the newest one that has repositories (user-submitted projects come first in the list)
    return projects.find((p) => p.id === chosen) ?? projects.find((p) => p.mode === "LIVE" && p.repositories.length > 0) ?? projects[0];
  }, [projects, chosen]);
  const setProjectId = useCallback((id: string) => {
    setChosen(id);
    try {
      window.localStorage.setItem(ACTIVE_KEY, id);
    } catch {
      /* the choice then lasts for this page load only */
    }
  }, []);

  const analysisQ = useAsync<AnalysisView | null>(
    async () => {
      if (!project) return null;
      try {
        return await api.projectAnalysis(project.id);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    [project?.id],
  );

  useEffect(() => {
    // a project whose repositories are still being fetched is refreshed until they settle
    if (project?.repositories.some((r) => r.status === "PENDING" || r.status === "INGESTING")) {
      const t = window.setTimeout(projectsQ.reload, 2000);
      return () => window.clearTimeout(t);
    }
  }, [project, projectsQ.reload]);

  const reload = useCallback(() => {
    projectsQ.reload();
    analysisQ.reload();
  }, [projectsQ.reload, analysisQ.reload]); // eslint-disable-line react-hooks/exhaustive-deps

  const value: Workspace = {
    caps: meta.data?.[0] ?? null,
    health: meta.data?.[1] ?? null,
    apiError: meta.error ?? projectsQ.error,
    projects,
    project,
    setProjectId,
    analysis: analysisQ.data,
    analysisLoading: analysisQ.loading,
    analysisError: analysisQ.error,
    reload,
    replay: meta.data?.[0]?.mode === "REPLAY",
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
