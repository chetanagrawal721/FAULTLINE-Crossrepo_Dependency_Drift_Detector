import { useState } from "react";

/** Small, dependency-free charts. Each is drawn only from the numbers it is given, has a text summary for assistive technology, and prints
 *  its values in a legend, so nothing depends on colour alone. */

export type Tone = "break" | "silent" | "ok" | "warn" | "run" | "neutral";
export type Slice = { key: string; label: string; value: number; tone: Tone; note?: string };

export const TONE_VAR: Record<Tone, string> = {
  break: "var(--c-break)",
  silent: "var(--c-silent)",
  ok: "var(--c-ok)",
  warn: "var(--c-warn)",
  run: "var(--c-run)",
  neutral: "var(--c-neutral)",
};

function summary(slices: Slice[], total: number) {
  return slices.filter((s) => s.value > 0).map((s) => `${s.label}: ${s.value} of ${total}`).join("; ") || "no data";
}

/** Part to whole for a few mutually exclusive categories. The total is the sum of the slices and is printed in the centre. */
export function Donut({ slices, centerLabel, onSlice, testid }: { slices: Slice[]; centerLabel: string; onSlice?: (key: string) => void; testid?: string }) {
  const total = slices.reduce((a, s) => a + s.value, 0);
  const [hover, setHover] = useState<string | null>(null);
  const R = 50;
  const C = 2 * Math.PI * R;
  let offset = 0;
  const active = slices.find((s) => s.key === hover);
  return (
    <figure className="chart donut" data-testid={testid}>
      <svg viewBox="0 0 140 140" role="img" aria-label={`${centerLabel}. ${summary(slices, total)}`}>
        <circle cx="70" cy="70" r={R} fill="none" stroke="var(--ui-surface-2)" strokeWidth="14" />
        {total > 0 &&
          slices
            .filter((s) => s.value > 0)
            .map((s) => {
              const len = (s.value / total) * C;
              const gap = slices.filter((x) => x.value > 0).length > 1 ? 1.5 : 0;
              const dash = `${Math.max(len - gap, 0.5)} ${C - Math.max(len - gap, 0.5)}`;
              const el = (
                <circle
                  key={s.key}
                  cx="70"
                  cy="70"
                  r={R}
                  fill="none"
                  stroke={TONE_VAR[s.tone]}
                  strokeWidth={hover === s.key ? 17 : 14}
                  strokeDasharray={dash}
                  strokeDashoffset={-offset}
                  transform="rotate(-90 70 70)"
                  onMouseEnter={() => setHover(s.key)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => onSlice?.(s.key)}
                  style={{ cursor: onSlice ? "pointer" : "default", transition: "stroke-width .15s ease" }}
                >
                  <title>{`${s.label}: ${s.value} of ${total}`}</title>
                </circle>
              );
              offset += len;
              return el;
            })}
        <text x="70" y="68" textAnchor="middle" className="donut-total">{active ? active.value : total}</text>
        <text x="70" y="85" textAnchor="middle" className="donut-label">{active ? active.label : centerLabel}</text>
      </svg>
      <ul className="chart-legend">
        {slices.map((s) => (
          <li key={s.key} onMouseEnter={() => setHover(s.key)} onMouseLeave={() => setHover(null)}>
            <button type="button" disabled={!onSlice || s.value === 0} onClick={() => onSlice?.(s.key)} title={s.note}>
              <i className={`swatch tone-${s.tone}`} aria-hidden="true" />
              <span>{s.label}</span>
              <b>{s.value}</b>
              <small>{total ? `${Math.round((s.value / total) * 100)}%` : ""}</small>
            </button>
          </li>
        ))}
      </ul>
    </figure>
  );
}

/** Horizontal bars on one shared scale that starts at zero, for comparing counts across categories. */
export function Bars({ slices, onBar, testid }: { slices: Slice[]; onBar?: (key: string) => void; testid?: string }) {
  const max = Math.max(1, ...slices.map((s) => s.value));
  const total = slices.reduce((a, s) => a + s.value, 0);
  return (
    <figure className="chart bars" data-testid={testid} role="img" aria-label={summary(slices, total)}>
      {slices.map((s) => (
        <button type="button" key={s.key} className="bar-row" disabled={!onBar || s.value === 0} onClick={() => onBar?.(s.key)} title={s.note ?? `${s.label}: ${s.value}`}>
          <span className="bar-label">{s.label}</span>
          <span className="bar-track">
            <i className={`tone-${s.tone}`} style={{ width: `${(s.value / max) * 100}%` }} />
          </span>
          <b>{s.value}</b>
        </button>
      ))}
    </figure>
  );
}
