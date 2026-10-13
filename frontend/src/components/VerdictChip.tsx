/** Verdict words are the master document's, shown with spaces. Never invent a softer word such as "compatible". */
const LABEL: Record<string, string> = {
  BREAK_WITNESSED: "BREAK WITNESSED",
  SILENT_DIVERGENCE_WITNESSED: "SILENT DIVERGENCE WITNESSED",
  NO_DIVERGENCE_OBSERVED: "NO DIVERGENCE OBSERVED",
  EXPOSED: "EXPOSED",
  POTENTIAL: "POTENTIAL",
  NOT_EXPOSED: "NOT EXPOSED",
  INCONCLUSIVE: "INCONCLUSIVE",
  HYGIENE: "HYGIENE",
};

const TONE: Record<string, string> = {
  BREAK_WITNESSED: "bad",
  SILENT_DIVERGENCE_WITNESSED: "bad",
  NO_DIVERGENCE_OBSERVED: "good",
  EXPOSED: "warn",
  POTENTIAL: "warn",
  NOT_EXPOSED: "off",
  INCONCLUSIVE: "off",
  HYGIENE: "off",
};

export function VerdictChip({ verdict }: { verdict: string }) {
  return (
    <span className={`verdict verdict-${TONE[verdict] ?? "off"}`} data-testid="verdict">
      {LABEL[verdict] ?? verdict}
    </span>
  );
}
