import { useState } from "react";
import { api, token } from "../api/client";
import { useAsync } from "../lib/hooks";
import { navigate } from "../lib/route";
import { Button, Logo, Status } from "../ui/primitives";

/** What this deployment requires before work can be started, and where the token goes. There are no accounts. */
export function AccessPage({ onOpen }: { onOpen: () => void }) {
  const health = useAsync(() => api.health(), []);
  const caps = useAsync(() => api.capabilities(), []);
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(Boolean(token.get()));
  const required = health.data?.auth === "token";
  return (
    <main className="access-page">
      <div className="access-graphic">
        <Logo />
        <div className="access-contract">
          <span />
          <img src="/faultline-logo.svg" alt="" />
          <span />
        </div>
        <p>WITNESSES, NOT WARNINGS.</p>
      </div>
      <section className="access-card">
        <Status tone="copper">{health.error ? "API not reached" : required ? "Token required to start work" : "No token required"}</Status>
        <h1>Open the FAULTLINE workspace</h1>
        <p>
          FAULTLINE has no user accounts. Reading results is open; starting an analysis, a re-run or a fix needs an admin token only when the server is configured with one.
        </p>
        <div className="access-facts">
          <div>
            <span>Mode</span>
            <strong>{caps.data?.mode ?? "Checking"}</strong>
          </div>
          <div>
            <span>Starting work</span>
            <strong>{health.data ? (required ? "Token required" : "Open") : "Checking"}</strong>
          </div>
          <div>
            <span>API</span>
            <strong>{health.error ? "Unreachable" : health.data ? health.data.status : "Checking"}</strong>
          </div>
        </div>
        {required && (
          <div className="app-form" data-testid="access-form">
            <label>
              <span>Admin token (kept in this tab only)</span>
              <input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder={saved ? "A token is stored for this tab" : "Paste the token"} autoComplete="off" aria-label="Admin token" />
            </label>
            <button
              className="back-link"
              onClick={() => {
                if (value.trim()) {
                  token.set(value.trim());
                  setSaved(true);
                  setValue("");
                }
              }}
            >
              Use this token
            </button>
          </div>
        )}
        <Button onClick={onOpen}>Open the workspace</Button>
        <button className="back-link" onClick={() => navigate("home")}>
          Return to the product site
        </button>
      </section>
    </main>
  );
}
