import { type ReactNode } from "react"

export function Icon({
  name,
  size = 18,
}: {
  name: "arrow" | "check" | "menu" | "close" | "search" | "chevron" | "sun" | "moon" | "grid"
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
}: {
  children: ReactNode
  onClick?: () => void
  quiet?: boolean
  disabled?: boolean
}) {
  return (
    <button
      className={quiet ? "app-action quiet" : "app-action"}
      onClick={onClick}
      disabled={disabled}
      title={disabled ? "Unavailable" : undefined}
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
