import type { Capabilities } from "../api/client";

const LABEL: Record<Capabilities["mode"], string> = {
  LIVE: "LIVE",
  FIXTURE: "REPRODUCIBLE FIXTURE",
  REPLAY: "RECORDED",
};

const HINT: Record<Capabilities["mode"], string> = {
  LIVE: "Analysis runs against real repositories now.",
  FIXTURE: "Pinned fixture repositories. Results are prepared, not fresh live analysis.",
  REPLAY: "Stored evidence is displayed. Nothing is executed.",
};

/** The mode badge is always visible. Fixture and replay results must never read as live analysis. */
export function ModeBadge({ mode }: { mode: Capabilities["mode"] }) {
  return (
    <span className={`badge badge-${mode.toLowerCase()}`} title={HINT[mode]} data-testid="mode-badge">
      {LABEL[mode]}
    </span>
  );
}
