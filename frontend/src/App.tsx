import { useEffect, useState } from "react";
import { Workspace } from "./app/Workspace";
import { AccessPage } from "./site/Access";
import { CapabilitiesPage, CtaSection, DocsPage, Footer, Header, HomePage, HowPage, LoadingScreen, StartModal } from "./site/Site";
import { goApp, parseHash, useRoute } from "./lib/route";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  try {
    const stored = window.localStorage.getItem("faultline-theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    /* storage can be blocked */
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const route = useRoute();
  // the opening animation belongs to the product site; someone returning straight to the workspace is not made to wait for it
  const [booting, setBooting] = useState(() => parseHash(window.location.hash).page !== "app");
  const [leaving, setLeaving] = useState(false);
  const [modal, setModal] = useState(false);
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    if (!booting) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const a = window.setTimeout(() => setLeaving(true), reduced ? 60 : 550);
    const b = window.setTimeout(() => setBooting(false), reduced ? 80 : 800);
    return () => {
      window.clearTimeout(a);
      window.clearTimeout(b);
    };
  }, [booting]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem("faultline-theme", theme);
    } catch {
      /* the choice then lasts for this page load only */
    }
  }, [theme]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setModal(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggle = () => setTheme((t) => (t === "light" ? "dark" : "light"));
  const openApp = () => {
    setModal(false);
    goApp("overview");
  };
  const startNew = () => {
    setModal(false);
    goApp("new");
  };

  if (booting) return <LoadingScreen leaving={leaving} />;
  if (route.page === "app") return <Workspace route={route} theme={theme} onTheme={toggle} />;

  return (
    <div className="app">
      <Header page={route.page} onStart={() => setModal(true)} theme={theme} onTheme={toggle} />
      {route.page === "home" && <HomePage onStart={() => setModal(true)} />}
      {route.page === "how" && <HowPage onStart={() => setModal(true)} />}
      {route.page === "capabilities" && <CapabilitiesPage />}
      {route.page === "docs" && <DocsPage />}
      {route.page === "access" && <AccessPage onOpen={openApp} />}
      {(route.page === "home" || route.page === "how") && <CtaSection onStart={() => setModal(true)} />}
      <Footer />
      {modal && <StartModal onClose={() => setModal(false)} onOpen={startNew} />}
    </div>
  );
}
