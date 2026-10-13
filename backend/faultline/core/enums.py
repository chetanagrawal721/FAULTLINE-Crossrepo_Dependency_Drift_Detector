"""Canonical enums. Values are the strings stored in the database and exposed by the API.

Verdict names follow the master document exactly. Never add a synonym.
"""
from enum import StrEnum


class Mode(StrEnum):
    LIVE = "LIVE"
    FIXTURE = "FIXTURE"
    REPLAY = "REPLAY"


class Ecosystem(StrEnum):
    PYPI = "pypi"
    NPM = "npm"
    MAVEN = "maven"


class Scope(StrEnum):
    RUNTIME = "runtime"
    DEV = "dev"
    TEST = "test"
    OPTIONAL = "optional"
    PROVIDED = "provided"
    PEER = "peer"


class SourceKind(StrEnum):
    REGISTRY = "registry"
    GIT = "git"
    PATH = "path"
    URL = "url"
    PRIVATE = "private"


class WorldKind(StrEnum):
    OBSERVED = "observed"
    REFERENCE = "reference"
    PROJECTED = "projected"
    FORCED = "forced"
    OVERLAY = "overlay"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_JOB_STATUSES = frozenset({JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED})

# Allowed status changes. RUNNING -> RUNNING is a lease reclaim by another worker.
JOB_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset({JobStatus.RUNNING, JobStatus.DONE, JobStatus.FAILED,
                                  JobStatus.CANCELLED, JobStatus.QUEUED}),
    JobStatus.DONE: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


class AnalysisStatus(StrEnum):
    QUEUED = "QUEUED"
    INGESTING = "INGESTING"
    RESOLVING = "RESOLVING"
    RELATING = "RELATING"
    BUILDING_CELLS = "BUILDING_CELLS"
    ANALYZING = "ANALYZING"
    VERIFYING = "VERIFYING"
    ATTRIBUTING = "ATTRIBUTING"
    DONE = "DONE"
    FAILED = "FAILED"


class Verdict(StrEnum):
    BREAK_WITNESSED = "BREAK_WITNESSED"
    SILENT_DIVERGENCE_WITNESSED = "SILENT_DIVERGENCE_WITNESSED"
    NO_DIVERGENCE_OBSERVED = "NO_DIVERGENCE_OBSERVED"
    EXPOSED = "EXPOSED"
    POTENTIAL = "POTENTIAL"
    NOT_EXPOSED = "NOT_EXPOSED"
    INCONCLUSIVE = "INCONCLUSIVE"
    HYGIENE = "HYGIENE"


class CellState(StrEnum):
    NO_DRIFT = "NO_DRIFT"
    PENDING = "PENDING"
    ANALYZED = "ANALYZED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class RelationshipLevel(StrEnum):
    L2 = "L2"
    L3 = "L3"
    L3P = "L3P"
    L4 = "L4"
    L5 = "L5"


class RelationshipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPECTED = "SUSPECTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class FailureClass(StrEnum):
    NONE = "NONE"
    ARTIFACT_FAILURE = "ARTIFACT_FAILURE"
    HARNESS_FAILURE = "HARNESS_FAILURE"
    RESOLUTION_FAILURE = "RESOLUTION_FAILURE"
    BUILD_FAILURE = "BUILD_FAILURE"
    SANDBOX_FAILURE = "SANDBOX_FAILURE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NEEDS_EXTERNAL = "NEEDS_EXTERNAL"
    UNSUPPORTED = "UNSUPPORTED"


class RunProvenance(StrEnum):
    """Only FRESH_EXECUTION runs count toward the 3 + 3 witness predicate."""
    FRESH_EXECUTION = "FRESH_EXECUTION"
    REUSED_RESULT = "REUSED_RESULT"


class WitnessClass(StrEnum):
    BREAK = "BREAK"
    SILENT_DIVERGENCE = "SILENT_DIVERGENCE"


class Sidedness(StrEnum):
    TWO_SIDED = "two_sided"
    ONE_SIDED = "one_sided"
    UNTESTABLE = "untestable"


class AttributionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BUDGET_LIMITED = "BUDGET_LIMITED"
    UNSTABLE = "UNSTABLE"
    UNAVAILABLE = "UNAVAILABLE"


class VenvStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    BUILT = "BUILT"
    FAILED = "FAILED"


class CapabilityState(StrEnum):
    ENABLED = "enabled"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class SandboxState(StrEnum):
    VERIFIED = "verified"
    STUB = "stub"
    UNAVAILABLE = "unavailable"
