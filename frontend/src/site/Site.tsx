import { useState, type ReactNode } from "react"
import { navigate, type Page } from "../lib/route"
import { Button, Eyebrow, Icon, Logo, ThemeToggle } from "../ui/primitives"

const navItems: { label: string; page: Page }[] = [
  { label: "How It Works", page: "how" },
  { label: "Capabilities", page: "capabilities" },
  { label: "Documentation", page: "docs" },
]

export function Header({
  page,
  onStart,
  theme,
  onTheme,
}: {
  page: Page
  onStart: () => void
  theme: "light" | "dark"
  onTheme: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <header className="site-header">
      <button
        className="brand-button"
        onClick={() => navigate("home")}
        aria-label="FAULTLINE home"
      >
        <Logo />
      </button>
      <nav
        className={open ? "site-nav is-open" : "site-nav"}
        aria-label="Main navigation"
      >
        <button className="nav-link" onClick={() => navigate("home")}>
          Product
        </button>
        {navItems.map((item) => (
          <button
            key={item.page}
            className={page === item.page ? "nav-link is-active" : "nav-link"}
            onClick={() => {
              navigate(item.page)
              setOpen(false)
            }}
          >
            {item.label}
          </button>
        ))}
        <button className="nav-link" onClick={() => navigate("access")}>
          Access
        </button>
        <ThemeToggle theme={theme} onToggle={onTheme} />
        <button className="nav-cta" onClick={onStart}>
          Open the workspace
          <Icon name="arrow" size={16} />
        </button>
      </nav>
      <button
        className="menu-button"
        aria-expanded={open}
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen(!open)}
      >
        <Icon name={open ? "close" : "menu"} size={22} />
      </button>
    </header>
  )
}

export function InvestigationVisual() {
  return (
    <div className="investigation-visual" aria-label="Illustrative dependency investigation preview">
      <div className="visual-topline">
        <div className="visual-title-lockup">
          <span className="visual-live-indicator" />
          <span>Investigation preview</span>
        </div>
        <span className="mode-badge">EXAMPLE DATA</span>
      </div>

      <div className="visual-context-row">
        <span>INVESTIGATION / 041</span>
        <span>PYTHON ECOSYSTEM</span>
      </div>

      <div className="visual-relation-map">
        <div className="visual-repo producer">
          <div className="visual-repo-top"><span className="repo-glyph">P</span><span>PRODUCER</span></div>
          <strong>shared-contracts</strong>
          <code>ref · a13f9c2</code>
          <div className="repo-meta"><span className="mini-state state-pinned" /> Source pinned</div>
        </div>

        <div className="visual-edge">
          <span className="edge-line"><i /></span>
          <span className="edge-label">CONTRACT</span>
          <span className="edge-line"><i /></span>
        </div>

        <div className="visual-repo consumer">
          <div className="visual-repo-top"><span className="repo-glyph">C</span><span>CONSUMER</span></div>
          <strong>billing-api</strong>
          <code>ref · d82b641</code>
          <div className="repo-meta"><span className="mini-state state-review" /> Review required</div>
        </div>
      </div>

      <div className="visual-divider"><span>Evidence trail</span><span>03 RECORDS</span></div>
      <div className="visual-evidence-list">
        <div className="visual-evidence-row">
          <span className="evidence-index">01</span>
          <span className="evidence-symbol symbol-source">↗</span>
          <span className="evidence-copy"><strong>Source revisions pinned</strong><small>Immutable repository inputs</small></span>
          <span className="evidence-status status-complete">RECORDED</span>
        </div>
        <div className="visual-evidence-row">
          <span className="evidence-index">02</span>
          <span className="evidence-symbol symbol-delta">Δ</span>
          <span className="evidence-copy"><strong>Environment delta identified</strong><small>Candidate difference · not a witness</small></span>
          <span className="evidence-status status-candidate">CANDIDATE</span>
        </div>
        <div className="visual-evidence-row">
          <span className="evidence-index">03</span>
          <span className="evidence-symbol symbol-verdict">!</span>
          <span className="evidence-copy"><strong>Behavioral witness</strong><small>Fresh runs still required</small></span>
          <span className="evidence-status status-pending">PENDING</span>
        </div>
      </div>

      <div className="visual-footnote">
        <span>Illustrative data only</span>
        <span><span className="footnote-dot" /> No live analysis implied</span>
      </div>
    </div>
  )
}
const values = [
  [
    "Cross-repository",
    "Investigate connected producer and consumer repositories.",
  ],
  [
    "Environment-aware",
    "Compare relevant dependency and environment differences.",
  ],
  [
    "Evidence-first",
    "Separate potential causes from reproducible behavioral evidence.",
  ],
  [
    "Transparent by design",
    "See the scope, coverage, and limitations of an investigation.",
  ],
]

const workflow = [
  [
    "01",
    "Pin the inputs",
    "Start from repository references and resolve them to immutable source revisions.",
  ],
  [
    "02",
    "Map the relationship",
    "Inspect manifests, imports, package visibility, and the evidence connecting producer and consumer.",
  ],
  [
    "03",
    "Compare worlds",
    "Inspect reference and consumer dependency worlds, including relevant differences and coverage.",
  ],
  [
    "04",
    "Test the behavior",
    "Run applicable checks and preserve each outcome. Fresh runs and reused artifacts remain distinct.",
  ],
  [
    "05",
    "Read the verdict",
    "Follow the finding through the witness, dependency delta, relationship evidence, and verdict rule.",
  ],
]

const features = [
  [
    "Funnel",
    "See where an investigation stands.",
    "Follow persisted stages without fabricated percentages or decorative progress.",
  ],
  [
    "World matrix",
    "Compare the worlds cell by cell.",
    "Inspect applicable, unsupported, incomplete, and analyzed cells while preserving the coverage denominator.",
  ],
  [
    "Witness",
    "Examine all six required runs.",
    "Keep reference and consumer runs, freshness, outcome, and signature agreement individually inspectable.",
  ],
  [
    "Why-path",
    "Follow the reasoning, not just the result.",
    "Trace the supported path from pinned sources and relationship evidence through worlds, runs, witness, and verdict.",
  ],
]

const marketingCapabilities = [
  [
    "Repository provenance",
    "Keep source references and pinned revisions visible.",
  ],
  [
    "Dependency worlds",
    "Inspect resolved environments, importer visibility, and relevant deltas.",
  ],
  [
    "Repeatable witnesses",
    "Review individual runs and the normalized failure signature.",
  ],
  [
    "Attribution",
    "Trace a finding to candidate changes, counterfactual checks, and attribution limits.",
  ],
  [
    "Coverage transparency",
    "See what ran, what was skipped, what failed to initialize, and what remains unsupported.",
  ],
  [
    "Portable evidence",
    "Inspect bundle integrity and replay outcomes where those capabilities are enabled.",
  ],
]

export function HomePage({ onStart }: { onStart: () => void }) {
  const [feature, setFeature] = useState(0)
  return (
    <main>
      <section className="hero page-shell">
        <div className="hero-copy">
          <div className="hero-kicker"><span className="kicker-rule" /> ENGINEERING INTELLIGENCE <span className="kicker-index">/ 07</span></div>
          <h1>
            A dependency changed.
            <br />
            <em>Find what actually broke.</em>
          </h1>
          <p className="hero-lede">
            Dependency failures rarely explain themselves.
          </p>
          <p className="hero-description">
            FAULTLINE investigates dependency drift across producer and consumer
            repositories—connecting pinned source revisions, environment
            differences, and behavioral evidence to a conclusion you can inspect.
          </p>
          <div className="button-row">
            <Button onClick={onStart}>Start an investigation</Button>
            <Button secondary onClick={() => navigate("how")}>
              Explore the method
            </Button>
          </div>
          <div className="hero-evidence-line">
            <span className="evidence-mark"><Icon name="check" size={13} /></span>
            <span>Built around evidence, not assumptions</span>
          </div>
          <div className="hero-meta">
            <span><b>01</b> PIN THE SOURCE</span>
            <span><b>02</b> TEST THE BEHAVIOR</span>
            <span><b>03</b> SCOPE THE VERDICT</span>
          </div>
        </div>
        <div className="hero-visual-wrap">
          <div className="hero-visual-index"><span>FIG. 01</span><span>THE INVESTIGATION MODEL</span></div>
          <InvestigationVisual />
          <div className="hero-visual-caption"><span>Every conclusion has a trail.</span><span>SCROLL TO EXPLORE ↓</span></div>
        </div>
      </section>

      <section className="value-strip page-shell" aria-label="Product values">
        {values.map(([title, body]) => (
          <div key={title}>
            <strong>{title}</strong>
            <p>{body}</p>
          </div>
        ))}
      </section>

      <section className="section page-shell problem-section">
        <div className="section-intro sticky-intro">
          <Eyebrow>The problem</Eyebrow>
          <h2>
            When a dependency changes, the real question is <em>why.</em>
          </h2>
          <p>
            The version difference is easy to notice. Establishing whether it
            caused the failure is much harder.
          </p>
          <p>
            Developers may need to compare source revisions, inspect dependency
            environments, reproduce behavior, and determine whether a failure is
            related to the change—or to something else entirely.
          </p>
        </div>
        <div className="problem-list">
          {[
            [
              "Differences are easy to find.",
              "Causes are harder to establish. A changed version may be relevant, but it does not automatically explain a failure.",
            ],
            [
              "Repositories do not exist in isolation.",
              "The relationship between a producer and its consumers matters when investigating a breakage.",
            ],
            [
              "A failed run is not always a witness.",
              "Infrastructure problems, timeouts, and test harness failures can obscure the actual behavior being investigated.",
            ],
          ].map(([title, body], i) => (
            <article className="numbered-row" key={title}>
              <span>0{i + 1}</span>
              <div>
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="dark-section">
        <div className="section page-shell">
          <div className="wide-heading">
            <Eyebrow>The method</Eyebrow>
            <h2>
              Turn dependency drift into an investigation{" "}
              <em>you can follow.</em>
            </h2>
            <p>
              Instead of stopping at “something changed,” follow the evidence to
              understand what was compared, what was tested, and what the
              results actually support.
            </p>
          </div>
          <div className="workflow-grid">
            {workflow.map(([num, title, copy]) => (
              <article key={num}>
                <span className="workflow-number">{num}</span>
                <div className="workflow-rule" />
                <h3>{title}</h3>
                <p>{copy}</p>
              </article>
            ))}
          </div>
          <p className="closing-line">
            From repository snapshots to evidence-backed conclusions.
          </p>
        </div>
      </section>

      <section className="section page-shell">
        <div className="wide-heading centered">
          <Eyebrow>Evidence, not assumption</Eyebrow>
          <h2>
            A version difference is a clue.
            <br />
            <em>Not a verdict.</em>
          </h2>
          <p>
            Many dependency tools tell you that something changed. FAULTLINE
            focuses on the harder question: whether a relevant difference is
            associated with a reproducible failure.
          </p>
        </div>
        <div className="comparison">
          <article>
            <span className="status status-neutral">Candidate difference</span>
            <h3>A signal worth investigating</h3>
            <ul>
              <li>
                <Icon name="arrow" />A dependency or environment difference has
                been observed.
              </li>
              <li>
                <Icon name="arrow" />
                The difference may be relevant to the failure.
              </li>
              <li>
                <Icon name="arrow" />
                Its causal relationship remains unverified.
              </li>
            </ul>
          </article>
          <div className="comparison-divider">
            <img src="/faultline-logo.svg" alt="" />
          </div>
          <article className="finding-panel">
            <span className="status status-copper">
              Evidence-backed finding
            </span>
            <h3>A conclusion with clear boundaries</h3>
            <ul>
              <li>
                <Icon name="check" />
                Valid behavioral evidence supports the conclusion.
              </li>
              <li>
                <Icon name="check" />
                Applicable witness requirements are satisfied.
              </li>
              <li>
                <Icon name="check" />
                The conclusion is scoped to tested conditions.
              </li>
            </ul>
          </article>
        </div>
        <p className="notice">
          <strong>Important:</strong> A timeout, environment failure, test
          harness issue, or dependency-resolution problem must not automatically
          be treated as a witnessed behavioral regression.
        </p>
      </section>

      <section className="section page-shell product-section">
        <div className="section-intro">
          <Eyebrow>Inside the investigation</Eyebrow>
          <h2>
            Everything you need to <em>follow the evidence.</em>
          </h2>
          <p>
            Explore the repository relationship, compare available environments,
            examine behavioral evidence, and inspect the reasoning behind a
            conclusion.
          </p>
        </div>
        <div className="product-showcase">
          <div
            className="feature-tabs"
            role="tablist"
            aria-label="Product features"
          >
            {features.map(([label], i) => (
              <button
                className={feature === i ? "feature-tab active" : "feature-tab"}
                onClick={() => setFeature(i)}
                role="tab"
                aria-selected={feature === i}
                key={label}
              >
                <span>0{i + 1}</span>
                {label}
              </button>
            ))}
          </div>
          <div className="product-preview">
            <div className="app-bar">
              <Logo compact />
              <span>
                Analysis / <strong>Example investigation</strong>
              </span>
              <span className="mode-badge">FIXTURE</span>
            </div>
            <div className="preview-body">
              <div className="preview-heading">
                <div>
                  <span className="micro-label">Why-path</span>
                  <h3>{features[feature][1]}</h3>
                </div>
                <span className="status status-neutral">Illustrative</span>
              </div>
              <div className="evidence-chain">
                {[
                  "Relationship",
                  "Environment delta",
                  "Behavior",
                  "Evidence",
                  "Verdict",
                ].map((step, i) => (
                  <div
                    className={
                      i <= feature ? "evidence-step active" : "evidence-step"
                    }
                    key={step}
                  >
                    <span>{i + 1}</span>
                    <strong>{step}</strong>
                    <small>
                      {i < 2 ? "Observed" : i === 2 ? "Tested" : "Pending"}
                    </small>
                  </div>
                ))}
              </div>
              <div className="preview-evidence">
                <span>Selected evidence</span>
                <code>producer-service@a13f9c2 → consumer-app@d82b641</code>
                <p>{features[feature][2]}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="marketing-capabilities page-shell">
        <div className="wide-heading">
          <Eyebrow>Capability, with boundaries</Eyebrow>
          <h2>
            Everything you need to <em>follow the evidence.</em>
          </h2>
          <p>
            Each capability remains explicit about its implementation status and
            the boundary of what it can establish.
          </p>
        </div>
        <div className="marketing-capability-grid">
          {marketingCapabilities.map(([title, copy], index) => (
            <button key={title} onClick={() => navigate("capabilities")}>
              <span>0{index + 1}</span>
              <h3>{title}</h3>
              <p>{copy}</p>
              <small>
                Status to confirm <Icon name="arrow" size={14} />
              </small>
            </button>
          ))}
        </div>
      </section>

      <section className="section page-shell transparency">
        <div>
          <Eyebrow>Transparent by design</Eyebrow>
          <h2>
            Know what was tested.
            <br />
            <em>Know what remains uncertain.</em>
          </h2>
        </div>
        <div>
          <p className="large-copy">
            An investigation is only as useful as its evidence and its
            boundaries. FAULTLINE distinguishes completed checks from
            unavailable capabilities, partial coverage, and inconclusive
            outcomes.
          </p>
          {[
            [
              "Explicit scope",
              "Understand which repositories, revisions, and environments were included.",
            ],
            [
              "Honest outcomes",
              "Distinguish a verified result from a candidate, an inconclusive investigation, or an execution failure.",
            ],
            [
              "Visible limitations",
              "Understand when missing evidence or unsupported functionality limits the conclusion.",
            ],
          ].map(([title, copy]) => (
            <div className="principle" key={title}>
              <Icon name="check" />
              <div>
                <strong>{title}</strong>
                <p>{copy}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <CtaSection onStart={onStart} />
    </main>
  )
}


export function PageHero({
  eyebrow,
  title,
  copy,
  onStart,
  secondary,
}: {
  eyebrow: string
  title: ReactNode
  copy: string
  onStart?: () => void
  secondary?: ReactNode
}) {
  return (
    <section className="subpage-hero page-shell">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h1>{title}</h1>
      <p>{copy}</p>
      <div className="button-row">
        {onStart && <Button onClick={onStart}>Start an investigation</Button>}
        {secondary}
      </div>
    </section>
  )
}

const howSteps = [
  [
    "01",
    "Source revisions",
    "Start with a known state.",
    "Pin the producer and consumer source revisions so the examined repositories are identifiable and the investigation scope is explicit.",
    [
      "Which repository snapshots are being examined.",
      "Which revisions define the scope.",
      "Which inputs the investigation used.",
    ],
  ],
  [
    "02",
    "Relationship evidence",
    "Understand how the repositories are connected.",
    "FAULTLINE records or inspects available relationship evidence so developers can understand why the repositories are being compared.",
    [
      "The producer and consumer under investigation.",
      "Available evidence for their relationship.",
      "Missing, conflicting, or incomplete information.",
    ],
  ],
  [
    "03",
    "Environment delta",
    "Find the relevant differences.",
    "Compare available reference and consumer environments to identify differences that may matter. A difference is a candidate, not an established cause.",
    [
      "Which environment information is available.",
      "Which values differ.",
      "Where coverage is partial.",
    ],
  ],
  [
    "04",
    "Behavioral evidence",
    "Test the hypothesis, not just the environment.",
    "Use supported methods to examine whether the suspected issue corresponds to observable behavior. Infrastructure or harness failure is not automatically a valid witness.",
    [
      "Which checks were actually run.",
      "Which outcomes were observed.",
      "Whether applicable witness requirements were met.",
    ],
  ],
  [
    "05",
    "Scoped verdict",
    "Know what the evidence supports.",
    "Review the conclusion alongside tested revisions, relationship evidence, environment differences, behavioral results, and scope limitations.",
    [
      "The outcome and its scope.",
      "The evidence that supports it.",
      "Coverage, limitations, and available artifacts.",
    ],
  ],
]

export function HowPage({ onStart }: { onStart: () => void }) {
  const [openFaq, setOpenFaq] = useState(0)
  const faqs = [
    [
      "Does every dependency difference mean something is broken?",
      "No. A dependency or environment difference is a candidate for investigation. It does not establish that the difference caused a behavioral failure.",
    ],
    [
      "Does every failed test count as a witness?",
      "No. Infrastructure failures, harness failures, timeouts, resource failures, and dependency-resolution problems must not automatically be treated as valid behavioral witnesses.",
    ],
    [
      "What if the evidence is incomplete?",
      "The interface shows partial coverage, unsupported conditions, or an inconclusive result where appropriate. It does not imply a stronger conclusion than the evidence supports.",
    ],
    [
      "Does FAULTLINE support every ecosystem?",
      "Universal support is not promised. Refer to the Capabilities page for implementation-backed ecosystem and oracle status.",
    ],
    [
      "Can every investigation be replayed?",
      "Only when replay is supported for the particular investigation and its available artifacts. Universal replay is not implied.",
    ],
  ]
  return (
    <main>
      <PageHero
        eyebrow="The investigation workflow"
        title={
          <>
            From a dependency change to an{" "}
            <em>evidence-backed investigation.</em>
          </>
        }
        copy="FAULTLINE organizes cross-repository dependency investigation into a traceable workflow, helping developers move from relevant differences to behavioral evidence and a conclusion whose scope is clear."
        onStart={onStart}
        secondary={
          <Button secondary onClick={() => navigate("capabilities")}>
            Explore capabilities
          </Button>
        }
      />
      <section className="process-overview page-shell">
        {howSteps.map(([n, label]) => (
          <div key={String(n)}>
            <span>{n}</span>
            <strong>{label}</strong>
          </div>
        ))}
      </section>
      <section className="steps-section page-shell">
        {howSteps.map(([n, label, title, copy, bullets]) => (
          <article className="detail-step" key={String(n)}>
            <div className="step-meta">
              <span>{n}</span>
              <small>{label}</small>
            </div>
            <div className="step-copy">
              <h2>{title}</h2>
              <p>{copy}</p>
            </div>
            <div className="establishes">
              <span className="micro-label">What this establishes</span>
              <ul>
                {(bullets as string[]).map((b) => (
                  <li key={b}>
                    <Icon name="check" />
                    {b}
                  </li>
                ))}
              </ul>
            </div>
          </article>
        ))}
      </section>
      <section className="section page-shell faq-section">
        <div>
          <Eyebrow>Common questions</Eyebrow>
          <h2>
            Every investigation should make its <em>reasoning visible.</em>
          </h2>
        </div>
        <div className="faq-list">
          {faqs.map(([q, a], i) => (
            <div className="faq" key={q}>
              <button
                onClick={() => setOpenFaq(openFaq === i ? -1 : i)}
                aria-expanded={openFaq === i}
              >
                <span>{q}</span>
                <Icon name="chevron" />
              </button>
              {openFaq === i && <p>{a}</p>}
            </div>
          ))}
        </div>
      </section>
      <CtaSection onStart={onStart} />
    </main>
  )
}

const capabilities = [
  [
    "Repository revision pinning",
    "Identifies source revisions used to define an investigation's scope.",
    "Do not imply every remote source or revision format is supported.",
  ],
  [
    "Repository relationship evidence",
    "Records or inspects evidence connecting a producer and consumer repository.",
    "A suspected relationship requires supporting evidence.",
  ],
  [
    "Dependency inventory",
    "Displays dependency information available for an inspected repository or environment.",
    "Status must be confirmed separately for each ecosystem.",
  ],
  [
    "World comparison",
    "Compares available environment information between reference and consumer sides.",
    "Missing or unresolved values remain explicit.",
  ],
  [
    "Dependency delta analysis",
    "Highlights differences that may be relevant to an investigation.",
    "A delta is a candidate, not a witnessed regression.",
  ],
  [
    "Supported testing oracles",
    "Uses available behavioral-checking methods to observe relevant behavior.",
    "Test types and frameworks must be implementation-backed.",
  ],
  [
    "Behavioral witness validation",
    "Evaluates whether observed runs satisfy the applicable validation protocol.",
    "Infrastructure and harness failures are not witnesses.",
  ],
  [
    "Scoped verdicts",
    "Presents conclusions bounded by the evidence and conditions examined.",
    "An inconclusive result remains inconclusive.",
  ],
  [
    "Evidence export",
    "Makes supported investigation artifacts available for inspection or export.",
    "Bundle contents and replay outcomes are listed with each witness.",
  ],
  [
    "Replay support",
    "Replays an investigation when implementation and available artifacts support it.",
    "Universal replay is not implied.",
  ],
]

export function CapabilitiesPage() {
  return (
    <main>
      <PageHero
        eyebrow="Capabilities & limitations"
        title={
          <>
            Built for careful <em>dependency investigations.</em>
          </>
        }
        copy="Explore the capabilities available in FAULTLINE, the evidence each capability provides, and the boundaries that determine what an investigation can conclude."
        secondary={
          <Button onClick={() => navigate("how")}>Explore the workflow</Button>
        }
      />
      <section className="capability-section page-shell">
        <div className="table-header">
          <span>Capability</span>
          <span>What it does</span>
          <span>Current status</span>
          <span>Limitations</span>
        </div>
        {capabilities.map(([name, description, limitation]) => (
          <article className="capability-row" key={name}>
            <strong>{name}</strong>
            <p>{description}</p>
            <span>
              <b className="status status-neutral">Status to confirm</b>
            </span>
            <small>{limitation}</small>
          </article>
        ))}
      </section>
      <section className="dark-section">
        <div className="section page-shell boundaries">
          <div>
            <Eyebrow>Truthful by default</Eyebrow>
            <h2>
              Capability boundaries are <em>part of the result.</em>
            </h2>
          </div>
          <div className="state-grid">
            {[
              ["Completed", "Comparison finished within stated scope."],
              [
                "Partial coverage",
                "Only part of the intended scope was inspected.",
              ],
              ["Unsupported", "The requested scenario is not available."],
              [
                "Inconclusive",
                "Evidence does not justify a stronger conclusion.",
              ],
            ].map(([s, c]) => (
              <article key={s}>
                <span className="state-dot" />
                <strong>{s}</strong>
                <p>{c}</p>
                <small>Illustrative state</small>
              </article>
            ))}
          </div>
        </div>
      </section>
      <section className="simple-cta page-shell">
        <h2>Know what you can investigate—and what the evidence can establish.</h2>
        <p>
          Explore the workflow to understand how repository context, environment
          differences, and behavioral evidence fit together.
        </p>
        <Button onClick={() => navigate("how")}>See how it works</Button>
      </section>
    </main>
  )
}

const docGroups = [
  [
    "01",
    "Getting started",
    "Start with the investigation scope.",
    "Begin by understanding which repositories and revisions are being examined, what relationship connects them, and which analysis capabilities are available.",
    [
      "Repository setup",
      "Source revisions",
      "Relationship evidence",
      "Preflight and capability status",
    ],
  ],
  [
    "02",
    "The workflow",
    "Follow the stages of an investigation.",
    "An investigation may move through repository validation, relationship inspection, environment comparison, behavioral checks, witness evaluation, and a scoped conclusion.",
    [
      "Investigation workflow",
      "Reference and consumer worlds",
      "Dependency deltas",
      "Analysis status",
    ],
  ],
  [
    "03",
    "Understanding findings",
    "Interpret the result correctly.",
    "A candidate difference, a verified finding, an inconclusive result, and an execution failure represent different kinds of evidence.",
    [
      "Candidate versus verified",
      "Finding status",
      "Why-Path",
      "Coverage limitations",
    ],
  ],
  [
    "04",
    "Witness & verdict semantics",
    "Know what counts as evidence.",
    "A failed run is not automatically a valid witness. Review validation requirements, run outcomes, failure signatures, and reasons a result may remain incomplete.",
    [
      "Witness validation",
      "Normalized failure signatures",
      "Scoped verdicts",
      "Infrastructure and harness failures",
    ],
  ],
  [
    "05",
    "Evidence & export",
    "Inspect the record behind the conclusion.",
    "Review source revisions, relationship evidence, environment comparison, behavioral results, provenance, and available artifacts.",
    [
      "Evidence manifest",
      "Export behavior",
      "Replay support",
      "Provenance and integrity",
    ],
  ],
  [
    "06",
    "Troubleshooting",
    "When an investigation cannot reach a conclusion.",
    "Unsupported ecosystems, unavailable revisions, failed resolution, incomplete inventories, and insufficient evidence can all limit an investigation.",
    [
      "Unsupported scenarios",
      "Inconclusive investigations",
      "Partial coverage",
      "Execution failures",
    ],
  ],
]

export function DocsPage() {
  const [query, setQuery] = useState("")
  const visible = docGroups.filter((g) =>
    g.join(" ").toLowerCase().includes(query.toLowerCase()),
  )
  return (
    <main>
      <section className="docs-hero">
        <div className="page-shell">
          <Eyebrow>FAULTLINE documentation</Eyebrow>
          <h1>
            Understand the investigation.
            <br />
            <em>Inspect the evidence.</em>
          </h1>
          <p>
            Learn how FAULTLINE structures cross-repository investigations,
            represents environment differences, evaluates behavioral evidence,
            and communicates the limits of a result.
          </p>
          <label className="search-box">
            <Icon name="search" size={21} />
            <span className="sr-only">Search documentation</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search documentation"
            />
            <kbd>⌘ K</kbd>
          </label>
        </div>
      </section>
      <section className="docs-grid page-shell">
        {visible.map(([n, group, title, copy, links]) => (
          <article className="doc-card" key={String(n)}>
            <div className="doc-number">{n}</div>
            <span className="micro-label">{group}</span>
            <h2>{title}</h2>
            <p>{copy}</p>
            <div className="doc-links">
              {(links as string[]).map((link) => (
                <button key={link}>
                  {link}
                  <Icon name="arrow" size={16} />
                </button>
              ))}
            </div>
          </article>
        ))}
        {visible.length === 0 && (
          <div className="no-results">
            <h2>No matching documentation</h2>
            <p>
              Try a broader term. Documentation links are
              information-architecture placeholders until implementation details
              are confirmed.
            </p>
          </div>
        )}
      </section>
      <div className="documentation-note page-shell">
        <strong>Documentation reflects implementation.</strong>
        <p>
          Planned features and future capabilities must be identified as
          planned, not presented as available. CLI commands, API endpoints, and
          framework support remain unspecified until confirmed.
        </p>
      </div>
    </main>
  )
}

export function CtaSection({ onStart }: { onStart: () => void }) {
  return (
    <section className="final-cta">
      <div className="page-shell">
        <img src="/faultline-logo.svg" alt="" />
        <div>
          <Eyebrow>Begin with the evidence</Eyebrow>
          <h2>
            Stop guessing at dependency failures.
            <br />
            <em>Start investigating the evidence.</em>
          </h2>
        </div>
        <div>
          <p>
            Bring the producer and consumer repositories into view. Compare
            relevant environments, investigate observed behavior, and see what
            the evidence supports.
          </p>
          <div className="button-row">
            <Button onClick={onStart}>Start an investigation</Button>
            <Button secondary onClick={() => navigate("how")}>
              Explore the workflow
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}

export function Footer() {
  return (
    <footer className="site-footer page-shell">
      <div className="footer-brand">
        <Logo />
        <p>
          Cross-repository dependency investigation, grounded in reproducible
          evidence.
        </p>
      </div>
      <div className="footer-columns">
        <div>
          <strong>Product</strong>
          <button onClick={() => navigate("home")}>Overview</button>
          <button onClick={() => navigate("how")}>How it works</button>
          <button onClick={() => navigate("capabilities")}>Capabilities</button>
        </div>
        <div>
          <strong>Resources</strong>
          <button onClick={() => navigate("docs")}>Documentation</button>
          <button onClick={() => navigate("docs")}>Evidence model</button>
          <button onClick={() => navigate("capabilities")}>
            Coverage & limitations
          </button>
        </div>
        <div>
          <strong>Project</strong>
          <span>Hacktopia 2026</span>
          <span>PS07</span>
        </div>
      </div>
      <p className="footer-statement">WITNESSES, NOT WARNINGS.</p>
      <p className="footer-note">
        FAULTLINE · Witnesses, not warnings. Every result states what was and was not checked.
      </p>
    </footer>
  )
}

export function StartModal({
  onClose,
  onOpen,
}: {
  onClose: () => void
  onOpen: () => void
}) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <button className="modal-close" onClick={onClose} aria-label="Close">
          <Icon name="close" />
        </button>
        <span className="status status-copper">Start an analysis</span>
        <h2 id="modal-title">Start with two public repositories.</h2>
        <p>
          Give FAULTLINE two or more public GitHub repositories. It pins each to one commit, fetches it inside a sandbox, relates the
          repositories by evidence, and reports only what it could reproduce. Nothing in a repository is installed or run outside the sandbox.
        </p>
        <div className="modal-note">
          <Icon name="check" />
          <span>
            <strong>Scoped by design.</strong> Python is verified end to end. npm and Maven are read as inventory only. Every result lists what was not checked.
          </span>
        </div>
        <Button onClick={onOpen}>Open the workspace</Button>
      </div>
    </div>
  )
}

export function LoadingScreen({ leaving }: { leaving: boolean }) {
  return (
    <div className={`faultline-loader${leaving ? " is-leaving" : ""}`} role="status" aria-live="polite" aria-label="Loading FAULTLINE">
      <div className="loader-content">
        <img src="/faultline-logo.svg" alt="" width="34" height="34" />
        <span className="loader-name">FAULTLINE</span>
        <div className="loader-progress-track" aria-hidden="true"><span /></div>
      </div>
    </div>
  )
}
