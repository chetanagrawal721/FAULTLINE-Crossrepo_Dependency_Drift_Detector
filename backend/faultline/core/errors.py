"""Typed errors and the failure-code taxonomy (master section 46)."""
from enum import StrEnum


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    INVALID_ENUM = "INVALID_ENUM"
    CANONICALIZATION_ERROR = "CANONICALIZATION_ERROR"
    UNKNOWN_JOB_KIND = "UNKNOWN_JOB_KIND"
    MIGRATION_FAILED = "MIGRATION_FAILED"
    # ingestion and analysis codes used in later phases
    INVALID_REPOSITORY = "INVALID_REPOSITORY"
    REPOSITORY_NOT_FOUND = "REPOSITORY_NOT_FOUND"
    REPOSITORY_NOT_ACCESSIBLE = "REPOSITORY_NOT_ACCESSIBLE"
    REF_NOT_FOUND = "REF_NOT_FOUND"
    GITHUB_RATE_LIMITED = "GITHUB_RATE_LIMITED"
    FETCH_FAILED = "FETCH_FAILED"
    INGEST_LIMIT = "INGEST_LIMIT"
    MANIFEST_PARSE_FAILED = "MANIFEST_PARSE_FAILED"
    MANIFEST_TOO_LARGE = "MANIFEST_TOO_LARGE"
    RESOLUTION_FAILED = "RESOLUTION_FAILED"
    UNSUPPORTED_BUILD = "UNSUPPORTED_BUILD"
    NO_WHEEL = "NO_WHEEL"
    WORLD_BUILD_FAILED = "WORLD_BUILD_FAILED"
    SANDBOX_FAILED = "SANDBOX_FAILED"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    HARNESS_ERROR = "HARNESS_ERROR"
    NEEDS_EXTERNAL = "NEEDS_EXTERNAL"
    NONDETERMINISTIC = "NONDETERMINISTIC"
    ORACLE_FAILED = "ORACLE_FAILED"
    STATIC_ANALYSIS_FAILED = "STATIC_ANALYSIS_FAILED"
    API_EXTRACTION_FAILED = "API_EXTRACTION_FAILED"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"


class Cancelled(Exception):
    """Raised inside a running job when cancellation was requested or the worker lost its lease. Not a failure."""


class LeaseLost(Cancelled):
    """The worker no longer owns the job (its lease expired and another worker took it). Evidence it wrote is labelled INTERRUPTED."""


class FaultlineError(Exception):
    code: ErrorCode = ErrorCode.VALIDATION_ERROR
    http_status: int = 400

    def __init__(self, message: str, *, code: ErrorCode | None = None, details: dict | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code.value, "message": self.message, "details": self.details}}


class NotFoundError(FaultlineError):
    code = ErrorCode.NOT_FOUND
    http_status = 404


class InvalidTransitionError(FaultlineError):
    code = ErrorCode.INVALID_TRANSITION
    http_status = 409


class InvalidEnumError(FaultlineError):
    code = ErrorCode.INVALID_ENUM
    http_status = 422


class CanonicalizationError(FaultlineError):
    code = ErrorCode.CANONICALIZATION_ERROR
    http_status = 422


class UnauthorizedError(FaultlineError):
    code = ErrorCode.UNAUTHORIZED
    http_status = 401
