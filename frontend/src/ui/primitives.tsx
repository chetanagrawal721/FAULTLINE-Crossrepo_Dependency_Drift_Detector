import { type ReactNode } from "react"

export type IconName =
  | "arrow" | "check" | "menu" | "close" | "search" | "chevron" | "sun" | "moon" | "grid"
  | "overview" | "plus" | "findings" | "matrix" | "link" | "graph" | "evidence" | "jobs" | "repo" | "sliders" | "gear" | "panel" | "exit"

export function Icon({
  name,
  size = 18,
}: {
  name: IconName
  size?: number
}) {
  const paths = {
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    check: <path d="m5 12 4 4L19 7" />,
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    chevron: <path d="m8 10 4 4 4-4" />,
    sun: (
      <>
        <circle cx="12" cy="12" r="3.5" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </>
    ),
    moon: <path d="M20 15.1A8 8 0 0 1 8.9 4a8.1 8.1 0 1 0 11.1 11.1Z" />,
    overview: (
      <>
        <rect x="3.5" y="3.5" width="7" height="9" rx="1" />
        <rect x="13.5" y="3.5" width="7" height="5" rx="1" />
        <rect x="13.5" y="11.5" width="7" height="9" rx="1" />
        <rect x="3.5" y="15.5" width="7" height="5" rx="1" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    findings: (
      <>
        <path d="M12 3.5 4.5 6.5v5.2c0 4.3 3 7.4 7.5 8.8 4.5-1.4 7.5-4.5 7.5-8.8V6.5L12 3.5Z" />
        <path d="M12 8.5v4M12 15.6v.1" />
      </>
    ),
    matrix: (
      <>
        <rect x="4" y="4" width="16" height="16" rx="1" />
        <path d="M4 9.3h16M4 14.7h16M9.3 4v16M14.7 4v16" />
      </>
    ),
    link: <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />,
    graph: (
      <>
        <circle cx="6" cy="6.5" r="2.2" />
        <circle cx="18" cy="8" r="2.2" />
        <circle cx="10.5" cy="17.5" r="2.2" />
        <path d="m7.9 7 8 .8M7.3 8.5l2.2 7M16.7 9.9l-4.8 6" />
      </>
    ),
    evidence: (
      <>
        <path d="M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5h-10A.5.5 0 0 1 7 20V3.5Z" />
        <path d="M14 3.5v4h4M9.5 12h5M9.5 15.5h5" />
      </>
    ),
    jobs: <path d="M8.5 6.5H20M8.5 12H20M8.5 17.5H20M4 6.5h.01M4 12h.01M4 17.5h.01" />,
    repo: (
      <>
        <circle cx="7" cy="6" r="2" />
        <circle cx="7" cy="18" r="2" />
        <circle cx="17" cy="8.5" r="2" />
        <path d="M7 8v8M17 10.5c0 3-3 3-8.5 5.5" />
      </>
    ),
    sliders: <path d="M5 8h9M18 8h1M5 16h1M10 16h9M14 5.5v5M6 13.5v5" />,
    gear: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6 6l1.5 1.5M16.5 16.5 18 18M18 6l-1.5 1.5M7.5 16.5 6 18" />
      </>
    ),
    panel: (
      <>
        <rect x="3.5" y="4.5" width="17" height="15" rx="1.5" />
        <path d="M9.5 4.5v15" />
      </>
    ),
    exit: <path d="M14 4.5h4.5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H14M10 8l-4 4 4 4M6 12h10" />,
    grid: (
      <>
        <rect x="4" y="4" width="6" height="6" />
        <rect x="14" y="4" width="6" height="6" />
        <rect x="4" y="14" width="6" height="6" />
        <rect x="14" y="14" width="6" height="6" />
      </>
    ),
  }
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
    >
      {paths[name]}
    </svg>
  )
}

export function LogoMark({ className = "" }: { className?: string }) {
  return <span className={`logo-mark-pair ${className}`}><img src="/faultline-logo.svg" alt="" /><img src="/faultline-logo-dark.svg" alt="" /></span>
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="logo-lockup">
      <LogoMark className="logo-mark" />
      {!compact && <span className="logo-type">FAULTLINE</span>}
    </span>
  )
}

export function Button({
  children,
  secondary = false,
  onClick,
}: {
  children: ReactNode
  secondary?: boolean
  onClick?: () => void
}) {
  return (
    <button
      className={secondary ? "button button-secondary" : "button"}
      onClick={onClick}
    >
      <span>{children}</span>
      <Icon name="arrow" />
    </button>
  )
}

export function ThemeToggle({
  theme,
  onToggle,
}: {
  theme: "light" | "dark"
  onToggle: () => void
}) {
  return (
    <button
      className="theme-toggle"
      onClick={onToggle}
      aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
      title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
    >
      <Icon name={theme === "light" ? "moon" : "sun"} size={17} />
    </button>
  )
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="eyebrow">
      <span />
      {children}
    </p>
  )
}

export function Status({
  children,
  tone = "neutral",
}: {
  children: ReactNode
  tone?: "neutral" | "copper" | "warn" | "good"
}) {
  return <span className={`app-status ${tone}`}>{children}</span>
}

export function AppAction({
  children,
  onClick,
  quiet = false,
  disabled = false,
  expanded,
  reason,
}: {
  children: ReactNode
  onClick?: () => void
  quiet?: boolean
  disabled?: boolean
  expanded?: boolean
  /** Why the action is unavailable, shown as the tooltip while it is disabled. */
  reason?: string
}) {
  return (
    <button
      className={quiet ? "app-action quiet" : "app-action"}
      onClick={onClick}
      disabled={disabled}
      aria-expanded={expanded}
      title={disabled ? reason ?? "Unavailable" : undefined}
    >
      {children}
    </button>
  )
}

export function Panel({
  title,
  meta,
  children,
  className = "",
}: {
  title: string
  meta?: string
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`work-panel ${className}`}>
      <div className="panel-heading">
        <div>
          {meta && <span>{meta}</span>}
          <h3>{title}</h3>
        </div>
      </div>
      {children}
    </section>
  )
}

export function DataTable({
  columns,
  rows,
  onRow,
  testid,
  rowAttrs,
}: {
  columns: string[]
  rows: ReactNode[][]
  onRow?: (index: number) => void
  testid?: string
  rowAttrs?: (index: number) => Record<string, string>
}) {
  return (
    <div className="data-table-wrap" data-testid={testid}>
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column, i) => (
              <th key={`${column}-${i}`}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={index}
              onClick={() => onRow?.(index)}
              className={onRow ? "clickable" : ""}
              tabIndex={onRow ? 0 : undefined}
              onKeyDown={(event) => event.key === "Enter" && onRow?.(index)}
              {...(rowAttrs?.(index) ?? {})}
            >
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
