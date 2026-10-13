import { useState } from "react";
import { ApiError, api, type Capabilities, type Job, type RepositoryView } from "../../api/client";
import { useAsync, short } from "../../lib/hooks";
import type { AppView } from "../../lib/route";
import { AppAction, DataTable, Panel, Status } from "../../ui/primitives";
import { useWorkspace } from "../context";
import { Loading, StateBlock } from "../shared";

type Go = (view: AppView, id?: string | null) => void;
type Slot = { url: string; ref: string };
const MAX_SLOTS = 6;

/** What went wrong, in words a person can act on. Distinct states for distinct causes. */
function describe(e: unknown): { title: string; body: string; retryable: boolean } {
  const err = e instanceof ApiError ? e : null;
  const body = err?.message ?? (e instanceof Error ? e.message : "Unknown error");
  switch (err?.code) {
    case "REPOSITORY_NOT_FOUND":
      return { title: "Repository not found", body: "It does not exist, or it was deleted. Check the owner and name.", retryable: false };
    case "REPOSITORY_NOT_ACCESSIBLE":
      return { title: "Repository not accessible", body: "It is private or access-restricted. Only public repositories are supported.", retryable: false };
    case "GITHUB_RATE_LIMITED":
      return { title: "GitHub rate limit reached", body: "This is temporary. Wait a minute and submit again. Setting GITHUB_TOKEN on the server raises the limit.", retryable: true };
    case "REF_NOT_FOUND":
      return { title: "Branch, tag or commit not found", body, retryable: false };
    case "INVALID_REPOSITORY":
      return { title: "Not a GitHub repository URL", body, retryable: false };
    case "FETCH_FAILED":
      return { title: "Could not reach GitHub", body, retryable: true };
    case "UNAUTHORIZED":
      return { title: "An access token is required", body: "This server requires an admin token to start work. Add it in Settings, then try again.", retryable: false };
    default:
      return { title: "Request failed", body, retryable: Boolean(err?.retryable) };
  }
}

const tone = (s: string) => (s === "enabled" ? "good" : s === "partial" ? "warn" : "neutral");

function CapabilityPreview({ caps }: { caps: Capabilities | null }) {
  if (!caps) return <Loading what="what this deployment supports" />;
  const cell = (c: { state: string; reason?: string | null }) => (
    <span title={c.reason ?? undefined}>
      <Status tone={tone(c.state)}>{c.state.toUpperCase()}</Status>
    </span>
  );
  return (
    <>
      <DataTable
        columns={["Ecosystem", "Inventory", "Resolution", "World construction", "Runtime witness"]}
        rows={caps.ecosystems.map((e) => [<strong>{e.ecosystem}</strong>, cell(e.inventory), cell(e.resolve), cell(e.world), cell(e.runtime_witness)])}
      />
      <p className="panel-note">Inventory support does not imply runtime execution support. Hover a status for the reason.</p>
    </>
  );
}

function Scenarios({ go }: { go: Go }) {
  const { replay, reload } = useWorkspace();
  const list = useAsync(() => api.scenarios(), []);
  const [running, setRunning] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  const poll = (id: string) =>
    api
      .job(id)
      .then((j) => {
        setJob(j);
        if (j.status === "QUEUED" || j.status === "RUNNING") window.setTimeout(() => poll(id), 1500);
        else {
          setRunning(null);
          if (j.status === "DONE") reload();
        }
      })
      .catch((e: Error) => {
        setError(e.message);
        setRunning(null);
      });
  const run = (id: string) => {
    setError(null);
    setRunning(id);
    api
      .runScenario(id)
      .then((j) => {
        setJob(j);
        poll(j.job_id);
      })
      .catch((e: unknown) => {
        setError(describe(e).body);
        setRunning(null);
      });
  };
  return (
    <Panel title="Fixture scenarios" meta="Committed repositories · real pipeline">
      <p className="panel-copy" data-testid="scenario-panel">
        Each scenario runs the real pipeline on committed fixture repositories: worlds are built offline, the oracles run in the sandbox three times per side, and the result is recorded. The mode stays FIXTURE; this is not analysis of a live repository.
      </p>
      {error && <p className="panel-note" role="alert">{error}</p>}
      {list.loading && !list.data ? (
        <Loading what="scenarios" />
      ) : (
        <DataTable
          columns={["Scenario", "Expected by its label", ""]}
          rows={(list.data ?? []).map((s) => [
            <span><strong>{s.id}</strong> · {s.title}</span>,
            s.consumers.length
              ? s.consumers.map((c) => `${c.repo}: ${c.expected_state === "NO_DRIFT" ? "no drift" : (c.expected_verdict ?? c.expected_state).toLowerCase().replaceAll("_", " ")}`).join(" · ")
              : "Not evaluated by the current oracles",
            <AppAction onClick={() => run(s.id)} disabled={replay || running !== null || s.consumers.length === 0} >
              {running === s.id ? "Running…" : "Run"}
            </AppAction>,
          ])}
        />
      )}
      {job && (
        <p className="panel-note" data-testid="job-status">
          Job <code>{job.job_id.slice(-8)}</code>: <strong>{job.status}</strong>
          {job.status === "RUNNING" ? ` · ${Math.round(job.progress * 100)}%` : ""}
          {job.message ? ` · ${job.message}` : ""}
          {job.status === "DONE" && (
            <>
              {" "}
              · <button className="back-link" onClick={() => go("findings")}>Open findings</button>
            </>
          )}
        </p>
      )}
    </Panel>
  );
}

export function NewAnalysisView({ go }: { go: Go }) {
  const { caps, health, replay, setProjectId, reload } = useWorkspace();
  const [step, setStep] = useState(1);
  const [slots, setSlots] = useState<Slot[]>([{ url: "", ref: "" }, { url: "", ref: "" }]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ReturnType<typeof describe> | null>(null);
  const [projectId, setPid] = useState<string | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [job, setJob] = useState<Job | null>(null);

  const project = useAsync(() => (projectId ? api.project(projectId) : Promise.resolve(null)), [projectId], {
    pollMs: 2000,
    keepPolling: (p) => Boolean(p?.repositories.some((r) => r.status === "PENDING" || r.status === "INGESTING")),
  });
  const repos: RepositoryView[] = project.data?.repositories ?? [];
  const ingested = repos.filter((r) => r.status === "INGESTED").length;
  const filled = slots.filter((s) => s.url.trim());

  const setSlot = (i: number, patch: Partial<Slot>) => setSlots((all) => all.map((s, k) => (k === i ? { ...s, ...patch } : s)));

  const pin = async () => {
    setProblem(null);
    setBusy(true);
    try {
      const name = filled.map((s) => s.url.trim().replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "")).join(" + ").slice(0, 78) || "analysis";
      const p = await api.createProject(name);
      for (const s of filled) await api.addRepository(p.id, s.url.trim(), s.ref.trim() || null);
      setPid(p.id);
      setProjectId(p.id);
      reload();
      setStep(2);
    } catch (e) {
      setProblem(describe(e));
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (!projectId) return;
    setProblem(null);
    setBusy(true);
    try {
      const j = await api.analyzeProject(projectId);
      setJob(j);
      setStep(3);
    } catch (e) {
      setProblem(describe(e));
    } finally {
      setBusy(false);
    }
  };

  const retry = (id: string) =>
    api
      .retryRepository(id)
      .then(() => project.reload())
      .catch((e: unknown) => setProblem(describe(e)));

  const startOver = () => {
    setStep(1);
    setPid(null);
    setJob(null);
    setUnderstood(false);
    setSlots([{ url: "", ref: "" }, { url: "", ref: "" }]);
  };

  return (
    <>
      <div className="stepper">
        {["Repositories", "Review pinned inputs", "Submit"].map((label, index) => (
          <button className={step >= index + 1 ? "active" : ""} onClick={() => (index + 1 <= step ? setStep(index + 1) : undefined)} key={label} disabled={index + 1 > step}>
            <span>{index + 1}</span>
            {label}
          </button>
        ))}
      </div>

      {problem && (
        <div className="state-panel compact" role="alert" data-testid="repo-problem">
          <Status tone="warn">{problem.title.toUpperCase()}</Status>
          <h2>{problem.title}</h2>
          <p>
            {problem.body} {problem.retryable ? "This may work if you try again." : "Retrying will not help until the input changes."}
          </p>
        </div>
      )}

      {step === 1 && (
        <>
          <div className="work-grid equal" data-testid="repositories-panel">
            {slots.slice(0, 2).map((s, index) => (
              <Panel title={index ? "Consumer repository" : "Producer repository"} meta={index ? "Downstream input" : "Reference input"} key={index}>
                <div className="app-form">
                  <label>
                    <span>Repository URL</span>
                    <input value={s.url} onChange={(e) => setSlot(index, { url: e.target.value })} placeholder="https://github.com/owner/repo" aria-label={index ? "Consumer repository URL" : "Producer repository URL"} />
                  </label>
                  <label>
                    <span>Branch, tag or commit (optional)</span>
                    <input value={s.ref} onChange={(e) => setSlot(index, { ref: e.target.value })} placeholder="default branch" aria-label={index ? "Consumer ref" : "Producer ref"} />
                  </label>
                  <p>Public GitHub repositories only. The ref is resolved to one immutable commit before anything else happens.</p>
                </div>
              </Panel>
            ))}
          </div>
          {slots.length > 2 && (
            <div className="work-grid equal">
              {slots.slice(2).map((s, k) => (
                <Panel title={`Additional repository ${k + 1}`} meta="Optional" key={k}>
                  <div className="app-form">
                    <label>
                      <span>Repository URL</span>
                      <input value={s.url} onChange={(e) => setSlot(k + 2, { url: e.target.value })} placeholder="https://github.com/owner/repo" aria-label={`Additional repository ${k + 1} URL`} />
                    </label>
                    <label>
                      <span>Branch, tag or commit (optional)</span>
                      <input value={s.ref} onChange={(e) => setSlot(k + 2, { ref: e.target.value })} aria-label={`Additional repository ${k + 1} ref`} />
                    </label>
                  </div>
                </Panel>
              ))}
            </div>
          )}
          <p className="panel-note">Faultline infers which repository shares code with which from evidence in the files. The producer and consumer labels are a hint for you, not an input to the result.</p>
          <div className="app-actions">
            {slots.length < MAX_SLOTS && (
              <AppAction quiet onClick={() => setSlots([...slots, { url: "", ref: "" }])}>
                Add another repository
              </AppAction>
            )}
            <AppAction onClick={pin} disabled={replay || busy || filled.length < 2}>
              {busy ? "Resolving…" : "Pin repositories"}
            </AppAction>
          </div>
          {replay && <p className="panel-note">This deployment shows recorded evidence only; nothing can be started.</p>}
          <Panel title="Capability preview" meta="Reported by this deployment">
            <CapabilityPreview caps={caps} />
          </Panel>
          <Scenarios go={go} />
        </>
      )}

      {step === 2 && (
        <Panel title="Review pinned inputs" meta="Nothing has run yet">
          {project.loading && !project.data ? (
            <Loading what="the pinned repositories" />
          ) : (
            <div className="review-inputs" data-testid="review-inputs">
              {repos.map((r) => (
                <div key={r.id} data-testid="repo-card">
                  <span>
                    {r.status === "INGESTED" ? "Pinned and fetched" : r.status === "FAILED" ? "Fetch failed" : "Fetching in the sandbox…"}
                    {r.snapshot?.status === "PARTIAL" ? " · partial snapshot" : ""}
                  </span>
                  <strong>
                    {r.owner}/{r.name}
                  </strong>
                  <code>
                    Requested: {r.requested_ref ?? "default branch"} · Pinned <span data-testid="pinned-sha" title={r.pinned_sha ?? ""}>{short(r.pinned_sha)}</span>
                  </code>
                  {r.snapshot && (
                    <code>
                      {r.snapshot.file_count} entries · {r.snapshot.manifests} manifest or lockfile{r.snapshot.manifests === 1 ? "" : "s"}
                    </code>
                  )}
                  {r.status === "INGESTED" && (
                    <button className="back-link" data-testid="inspect-link" onClick={() => go("repository", r.id)}>
                      Inspect dependency worlds →
                    </button>
                  )}
                  {r.status === "FAILED" && r.error && (
                    <>
                      <code>
                        {String(r.error.code)}: {String(r.error.message)}
                      </code>
                      {r.error.retryable ? (
                        <button className="back-link" onClick={() => retry(r.id)}>Retry the same commit</button>
                      ) : (
                        <code>Not retryable.</code>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
          <label className="confirm-check">
            <input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />I understand that a dependency difference is a candidate cause, and that only a witnessed failure counts as evidence of a break.
          </label>
          {health?.auth === "token" && <p className="panel-note">This server requires an access token to start an analysis. Add it in Settings if the request is refused.</p>}
          <div className="app-actions">
            <AppAction quiet onClick={startOver}>
              Start over
            </AppAction>
            <AppAction onClick={submit} disabled={replay || busy || !understood || ingested < 2}>
              {busy ? "Submitting…" : "Run analysis"}
            </AppAction>
          </div>
          {ingested < 2 && repos.length > 0 && <p className="panel-note">The analysis needs at least two repositories fetched ({ingested} so far).</p>}
        </Panel>
      )}

      {step === 3 && job && (
        <StateBlock tone="copper" label={`JOB ${job.status}`} title="The analysis was queued." testid="submitted">
          Job <code>{job.job_id}</code> was accepted and persisted. Its stages appear in the run view as they complete.
          <br />
          <AppAction onClick={() => go("run", job.job_id)}>Open the analysis run</AppAction>
        </StateBlock>
      )}
    </>
  );
}
