import { useState } from "react";
import { token } from "../../api/client";
import { AppAction, Icon, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";

export function SettingsView({ theme, onTheme }: { theme: "light" | "dark"; onTheme: () => void }) {
  const { caps, health, apiError } = useWorkspace();
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(Boolean(token.get()));
  const required = health?.auth === "token";
  return (
    <div className="work-grid two-one">
      <div>
        <Panel title="Appearance" meta="Saved in this browser">
          <div className="setting-row">
            <div>
              <strong>Color theme</strong>
              <p>Choose a comfortable appearance for this browser.</p>
            </div>
            <button className="theme-choice" onClick={onTheme}>
              <Icon name={theme === "light" ? "moon" : "sun"} />
              {theme === "light" ? "Use dark" : "Use light"}
            </button>
          </div>
        </Panel>
        <Panel title="Access" meta={required ? "This server requires a token to start work" : "No token is required"}>
          <p className="panel-copy">
            {required
              ? "Starting an analysis, a re-run or a fix needs the admin token configured on the server. It is kept in this browser tab only (session storage) and is sent as a bearer token with those requests."
              : "This server does not require a token. If an administrator sets one, enter it here to be able to start work."}
          </p>
          <div className="app-form" data-testid="access-form">
            <label>
              <span>Admin token</span>
              <input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder={saved ? "A token is stored for this tab" : "Paste the token"} autoComplete="off" aria-label="Admin token" />
            </label>
          </div>
          <div className="app-actions">
            <AppAction
              onClick={() => {
                token.set(value.trim() || null);
                setSaved(Boolean(value.trim()));
                setValue("");
              }}
              disabled={!value.trim()}
            >
              Use this token
            </AppAction>
            <AppAction
              quiet
              onClick={() => {
                token.set(null);
                setSaved(false);
              }}
              disabled={!saved}
            >
              Forget the token
            </AppAction>
          </div>
        </Panel>
      </div>
      <Panel title="Application information" meta="From the running API">
        <dl className="key-values">
          <div>
            <dt>Mode</dt>
            <dd>{caps?.mode ?? "Unknown"}</dd>
          </div>
          <div>
            <dt>Authentication</dt>
            <dd>{health ? (required ? "Token required to start work" : "Not required") : "Unknown"}</dd>
          </div>
          <div>
            <dt>API status</dt>
            <dd>
              {apiError && !health ? <Status tone="warn">UNREACHABLE</Status> : health ? <Status tone={health.status === "ok" ? "good" : "warn"}>{health.status.toUpperCase()}</Status> : "Checking"}
            </dd>
          </div>
          <div>
            <dt>Database schema</dt>
            <dd>{health ? `v${health.schema_version} · ${health.db}` : "Unknown"}</dd>
          </div>
          <div>
            <dt>API / capability version</dt>
            <dd>{caps ? `${caps.api_version} / ${caps.capability_version}` : "Unknown"}</dd>
          </div>
          <div>
            <dt>Sandbox</dt>
            <dd>{caps ? caps.sandbox.state : "Unknown"}</dd>
          </div>
        </dl>
      </Panel>
    </div>
  );
}
