"""API response models for scenarios, findings and witnesses. They are read models: built from persisted rows only."""
from pydantic import BaseModel, ConfigDict

from .models import FailureSignature


class View(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioConsumer(View):
    repo: str
    expected_state: str
    expected_verdict: str | None
    expects_witness: bool


class ScenarioInfo(View):
    id: str
    title: str
    kind: str
    artifact: str
    consumers: list[ScenarioConsumer]


class DeltaItem(View):
    name: str
    reference: str | None
    consumer: str | None


class EntryView(View):
    entry: str
    passed: bool
    skipped: bool
    not_applicable: bool
    failure_class: str
    exc_type: str | None
    message: str | None
    origin_module: str | None


class RunView(View):
    run_id: str
    side: str
    run_index: int
    provenance: str
    failure_class: str
    duration_ms: int
    entries: list[EntryView]
    stdout_tail: str
    stderr_tail: str


class WorldView(View):
    world_hash: str
    kind: str
    runtime: str
    env_profile_id: str
    package_count: int


class WitnessView(View):
    witness_id: str
    witness_class: str
    oracle: str
    oracle_version: str
    entry_point: str
    divergence: str
    ref_pass: int
    test_fail: int
    signature: FailureSignature
    ref_run_ids: list[str]
    test_run_ids: list[str]
    reverifications: int


class Scope(View):
    exercised: list[str]
    not_applicable: list[str]
    not_checked: list[str]
    reasons: list[str]
    policy: str


class FindingSummary(View):
    finding_id: str
    analysis_id: str
    cell_id: str
    mode: str
    verdict: str
    headline: str
    artifact: str
    consumer: str
    created_at: str
    witness_ids: list[str]


class FindingDetail(FindingSummary):
    reference: WorldView
    consumer_world: WorldView
    delta: list[DeltaItem]
    runs: list[RunView]
    witnesses: list[WitnessView]
    scope: Scope
    fresh_runs: int
    reused_runs: int
    bundle_url: str | None


# ---- ingestion (Phase 2) -----------------------------------------------------------------------------------

class SnapshotSummary(View):
    id: str
    sha: str
    status: str                       # OK | PARTIAL
    truncated: bool
    warnings: list[str]
    file_count: int
    stored_files: int
    manifests: int


class RepositoryView(View):
    id: str
    project_id: str
    owner: str
    name: str
    url: str
    requested_ref: str | None
    default_branch: str | None
    pinned_sha: str | None
    committed_at: str | None
    is_fork: bool
    is_archived: bool
    status: str                       # PENDING | INGESTING | INGESTED | FAILED
    error: dict | None                # {code, message, retryable}
    snapshot: SnapshotSummary | None
    job_id: str | None = None


class ProjectView(View):
    id: str
    name: str
    mode: str
    created_at: str
    repositories: list[RepositoryView]


class FileView(View):
    path: str
    kind: str                         # file | symlink | submodule | lfs_pointer | too_large | unsupported_path
    size: int | None
    role: str | None
    tags: list[str]
    reason: str | None
    sha256: str | None


class ProjectCreate(View):
    name: str


class RepositoryCreate(View):
    url: str
    ref: str | None = None


# ---- world inspector (Phase 3) -----------------------------------------------------------------------------

class DeclaredView(View):
    spec: str                         # the range as written ("" when unconstrained)
    group: str
    marker: str | None
    origin: str                       # manifest path
    kind: str                         # registry | vcs | url | path


class PackageView(View):
    name: str
    declared: list[DeclaredView]      # empty means a transitive dependency nobody declared directly
    resolved: str | None              # the version the resolver or lockfile chose
    visible: str | None               # what an importer can actually see; null until observed in a built world
    visible_source: str | None
    scope: str | None
    source_kind: str | None
    artifact_sha256: str | None
    locator: str | None = None        # npm: the node_modules path of this exact instance
    visible_to: list[str] = []        # npm: importers that resolve to THIS instance ('' is the project root)


class ManifestView(View):
    path: str
    kind: str
    parse_status: str
    parse_error: str | None


class WorldDetail(View):
    status: str                       # OK | OK_PARTIAL | FAILED
    source: str                       # lockfile | resolver
    world_hash: str | None
    resolver: str | None
    cutoff: str
    failure: dict | None
    warnings: list[str]
    private: list[str]
    reproducibility: dict
    packages: list[PackageView]


class InventoryDep(View):
    name: str                         # Maven: groupId:artifactId
    version: str | None               # None when it cannot be established from the repository
    scope: str
    version_source: str               # declared | property | managed | unresolved
    note: str | None


class ProjectDetail(View):
    project_id: str
    rel_path: str
    ecosystem: str
    name: str | None
    origin: str | None
    notes: list[str]
    manifests: list[ManifestView]
    world: WorldDetail | None
    inventory: list[InventoryDep] = []        # declared dependencies, for ecosystems where no world is built (Maven)


# ---- live analysis (Phase 4) -------------------------------------------------------------------------------

class EvidenceLine(View):
    signal: str
    repository: str                   # owner/name
    commit: str                       # the pinned SHA the line was read at
    file_path: str
    line: int | None
    excerpt: str | None


class RelationshipView(View):
    id: str
    producer: str                     # owner/name[:path]
    consumer: str
    level: str
    kind: str
    confidence: str
    actionable: bool
    status: str                       # ACTIVE | SUSPECTED
    notes: list[str]
    evidence: list[EvidenceLine]


class DeltaLine(View):
    name: str
    reference: str | None
    consumer: str | None
    kind: str


class AttemptView(View):
    direction: str                    # search | sufficiency | necessity
    subset: list[str]
    outcome: str                      # FAIL | PASS | UNRESOLVED
    note: str | None
    label: str                        # always the forced-world label: these are experiments, never observations


class AttributionView(View):
    status: str                       # COMPLETE | PARTIAL | BUDGET_LIMITED | UNSTABLE | UNAVAILABLE
    sidedness: str
    minimal: list[str]
    minimal_claim: str | None         # only set when COMPLETE and two-sided
    notes: list[str]
    attempts: list[AttemptView]


class OraclePlanStep(View):
    oracle: str
    status: str          # RAN | PLANNED | BLOCKED | NOT_PLANNED
    reason: str = ""
    entries: list[str] = []


class CellView(View):
    id: str
    state: str
    ref_world_hash: str
    test_world_hash: str
    consumers: list[str]
    imported_modules: list[str]
    delta: list[DeltaLine]
    finding_id: str | None
    verdict: str | None
    headline: str | None
    attribution: AttributionView | None = None
    oracle_plan: list[OraclePlanStep] = []      # what was planned and run for this cell, from the stored finding
    runtime: str = "cpython 3.12.15"
    platform: str = "linux/amd64 (x86_64-unknown-linux-gnu)"
    visibility: str = "flat site-packages: the importer sees the resolved version"


class FailedConsumer(View):
    consumer: str
    producer: str
    side: str
    reason: str
    text: str


class AnalysisView(View):
    id: str
    project_id: str
    status: str
    outcome: str | None = None          # for an analysis that did not finish: CANCELLED, INTERRUPTED or ERROR (partial evidence is kept)
    partial_note: str | None = None
    mode: str
    started_at: str | None
    finished_at: str | None
    funnel: dict
    failed: list[FailedConsumer]
    relationships: list[RelationshipView]
    cells: list[CellView]


# ---- why-path and inventory graph (M5.6) ------------------------------------------------------------------

class WhyStep(View):
    kind: str                         # relationship | delta | oracle | verdict | attribution
    status: str                       # analysed | not_analysed
    title: str
    detail: str
    items: list[str] = []


class WhyPath(View):
    finding_id: str
    verdict: str
    steps: list[WhyStep]


class GraphNode(View):
    id: str
    kind: str                         # repository | project | manifest | package
    label: str
    ecosystem: str | None = None
    status: str = "ok"                # ok | unsupported | failed
    detail: str | None = None


class GraphEdge(View):
    source: str
    target: str
    kind: str                         # contains | declares | consumes | suspected
    label: str | None = None
    level: str | None = None          # relationship evidence level for consumes edges


class InventoryGraph(View):
    project_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
