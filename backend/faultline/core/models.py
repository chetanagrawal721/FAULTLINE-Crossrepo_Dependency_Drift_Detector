"""Canonical models. Every phase uses these shapes; no phase defines a parallel version.

These follow master section 63.2. Changing a field here changes the API schema, the persisted evidence
schema and the generated TypeScript types, so changes need review by two members.
"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .enums import (
    AttributionStatus,
    CapabilityState,
    CellState,
    Ecosystem,
    FailureClass,
    JobStatus,
    Mode,
    RunProvenance,
    SandboxState,
    Scope,
    Sidedness,
    SourceKind,
    Verdict,
    WitnessClass,
    WorldKind,
)

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=False)


# ----------------------------------------------------------------------------- worlds

class Runtime(Frozen):
    name: Literal["cpython", "node", "jdk"]
    version: str            # "3.12.15" or "20.11" ... exact string as pinned


class EnvProfile(Frozen):
    """Environment dimensions held constant during execution (master section 10.3)."""
    image_ref: str          # must contain @sha256:<digest> once images exist
    os: str = "linux"
    arch: str = "amd64"
    locale: str = "C.UTF-8"
    tz: str = "UTC"
    env: dict[str, str] = Field(default_factory=dict)   # allow-listed environment variables
    seed: int = 17


class WorldEntry(Frozen):
    locator: str            # python: normalized name; npm: node_modules path; maven: g:a:classifier:type
    name: str
    version: str
    scope: Scope = Scope.RUNTIME
    source_kind: SourceKind = SourceKind.REGISTRY
    source_ref: str | None = None
    artifact_sha256: Sha256 | None = None
    parents: tuple[str, ...] = ()       # reason edges; NOT part of world identity


class ResolvedWorld(Frozen):
    world_hash: str
    ecosystem: Ecosystem
    kind: WorldKind
    runtime: Runtime
    env_profile_id: str
    entries: tuple[WorldEntry, ...]


class DeltaEntry(Frozen):
    name: str               # package name, "<runtime>" or "<artifact>"
    v_ref: str | None
    v_test: str | None


class Cell(Frozen):
    cell_id: str
    artifact_project_id: str
    ref_world_hash: str
    test_world_hash: str
    state: CellState
    delta: tuple[DeltaEntry, ...] = ()
    consumers: tuple[str, ...] = ()     # consumer project ids
    forced_overlay: bool = False


# ----------------------------------------------------------------------------- oracles

class OracleJob(Frozen):
    job_id: str
    oracle: Literal["o_import", "o_tests", "o_bind", "o_contract_producer", "o_contract_consumer",
                    "o_typecheck", "o_protobuf", "world_build", "resolve", "clone"]
    oracle_version: str
    image: str              # immutable: "sha256:<id>" or "name@sha256:<digest>"
    world_hash: str | None = None
    artifact_content_hash: str | None = None
    args: dict = Field(default_factory=dict)
    limits: dict = Field(default_factory=dict)
    env_profile_id: str
    run_index: int = 1
    zone: Literal["exec", "fetch"] = "exec"

    @field_validator("image")
    @classmethod
    def _immutable_image(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"(sha256:[0-9a-f]{64}|[\w./:-]+@sha256:[0-9a-f]{64})", v):
            raise ValueError("image must be referenced by an immutable sha256 id or digest, not a tag")
        return v


class EntryOutcome(Frozen):
    entry: str              # module, test id, call-site id or input id
    passed: bool
    exc_type: str | None = None
    message: str | None = None
    frames: tuple[dict, ...] = ()
    output_canonical: str | None = None
    warnings: tuple[str, ...] = ()
    failure_class: FailureClass = FailureClass.NONE   # per entry: ARTIFACT_FAILURE, HARNESS_FAILURE, NEEDS_EXTERNAL, ...
    not_applicable: bool = False                      # e.g. the module needs a package this world does not contain
    skipped: bool = False                             # a test that did not run (counts as neither pass nor failure)


class OracleRunResult(Frozen):
    job_id: str
    run_id: str
    provenance: RunProvenance
    exit_code: int | None
    duration_ms: int
    failure_class: FailureClass
    entries: tuple[EntryOutcome, ...] = ()
    stdout_tail: str = ""
    stderr_tail: str = ""
    data: dict | None = None            # the harness result frame, when one was produced
    truncated: bool = False             # output hit the size cap


# ----------------------------------------------------------------------------- evidence

class FailureSignature(Frozen):
    exc_type: str
    message_norm: str
    origin_module: str | None = None
    origin_package: str | None = None
    entry_point: str


class Witness(Frozen):
    witness_id: str
    witness_class: WitnessClass
    cell_id: str
    oracle: str
    oracle_version: str
    entry_point: str
    witness_key: str
    signature: FailureSignature
    ref_run_ids: tuple[str, ...]        # exactly three FRESH_EXECUTION passes
    test_run_ids: tuple[str, ...]       # exactly three FRESH_EXECUTION failures
    input_tier: Literal["T1", "T2", "T3", "T4"] | None = None


class AttributionAttempt(Frozen):
    subset: tuple[str, ...]
    direction: Literal["apply_to_reference", "revert_in_consumer"]
    reproduced: bool


class Attribution(Frozen):
    attribution_id: str
    witness_id: str
    status: AttributionStatus
    minimal_set: tuple[str, ...]
    sidedness: Sidedness
    forced_worlds_used: bool
    attempts: tuple[AttributionAttempt, ...] = ()
    notes: tuple[str, ...] = ()


class Finding(Frozen):
    finding_id: str
    analysis_id: str
    cell_id: str | None
    verdict: Verdict
    headline: str
    policy_version: str
    mode: Mode
    coverage: float | None = None
    scope_exercised: tuple[str, ...] = ()
    scope_not_checked: tuple[str, ...] = ()


# ----------------------------------------------------------------------------- capabilities / jobs

class CapabilityStatus(Frozen):
    state: CapabilityState
    reason: str | None = None


class EcosystemCapability(Frozen):
    ecosystem: Ecosystem
    inventory: CapabilityStatus
    resolve: CapabilityStatus
    world: CapabilityStatus
    runtime_witness: CapabilityStatus


class SandboxStatus(Frozen):
    state: SandboxState
    verified: bool
    reason: str


class Capabilities(Frozen):
    capability_version: str
    api_version: str
    mode: Mode
    sandbox: SandboxStatus
    ecosystems: tuple[EcosystemCapability, ...]
    oracles: dict[str, CapabilityStatus]
    features: dict[str, CapabilityStatus]


class Health(Frozen):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "error"]
    schema_version: int
    mode: Mode
    auth: Literal["token", "disabled"]
    time: datetime


class JobCreate(Frozen):
    kind: str
    payload: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)


class Job(Frozen):
    job_id: str
    kind: str
    status: JobStatus
    idempotency_key: str | None
    attempts: int
    max_attempts: int
    progress: float
    message: str | None
    cancel_requested: bool
    result: dict | None
    error: dict | None
    created_at: datetime
    updated_at: datetime
    duration_ms: int | None = None      # time actually spent running (all attempts); for a running job, so far
    queue_wait_ms: int | None = None    # created until the first attempt started
    failure_class: str | None = None    # error code of a failed job, CANCELLED, or None
    retried_after: str | None = None    # how an earlier attempt ended (LEASE_LOST, RETRY, ...) when a later attempt was needed
