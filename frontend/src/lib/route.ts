import { useEffect, useState } from "react";

export type Page = "home" | "how" | "capabilities" | "docs" | "access" | "app";
export type AppView =
  | "overview"
  | "new"
  | "run"
  | "findings"
  | "finding"
  | "worlds"
  | "witness"
  | "relationships"
  | "inventory"
  | "evidence"
  | "jobs"
  | "repository"
  | "coverage"
  | "settings";

export type Route = { page: Page; view: AppView; id: string | null };

const PAGES: Page[] = ["home", "how", "capabilities", "docs", "access", "app"];
const VIEWS: AppView[] = ["overview", "new", "run", "findings", "finding", "worlds", "witness", "relationships", "inventory", "evidence", "jobs", "repository", "coverage", "settings"];
/** Routes used before the redesign keep working (bookmarks, links in the evidence documents). */
const LEGACY: Record<string, AppView> = { repo: "repository" };

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const first = parts[0] ?? "home";
  if (first === "app") {
    const view = (VIEWS as string[]).includes(parts[1] ?? "") ? (parts[1] as AppView) : "overview";
    return { page: "app", view, id: parts[2] ?? null };
  }
  if ((PAGES as string[]).includes(first)) return { page: first as Page, view: "overview", id: null };
  const legacy = LEGACY[first] ?? ((VIEWS as string[]).includes(first) ? (first as AppView) : null);
  if (legacy) return { page: "app", view: legacy, id: parts[1] ?? null };
  return { page: "home", view: "overview", id: null };
}

export const appHref = (view: AppView, id?: string | null) => `#/app${view === "overview" && !id ? "" : `/${view}`}${id ? `/${encodeURIComponent(id)}` : ""}`;

export function navigate(page: Page) {
  window.location.hash = page === "home" ? "#/" : page === "app" ? "#/app" : `#/${page}`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

export function goApp(view: AppView, id?: string | null) {
  window.location.hash = appHref(view, id);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
