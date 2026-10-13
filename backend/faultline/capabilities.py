"""Builds the capability report. Every capability that is not implemented says so, with a reason.

Update the table below when a milestone enables something, and only then.
"""
from .core.config import API_VERSION, CAPABILITY_VERSION
from .core.enums import CapabilityState, Ecosystem, Mode
from .core.models import Capabilities, CapabilityStatus, EcosystemCapability, SandboxStatus


def _off(reason: str, state: CapabilityState = CapabilityState.UNAVAILABLE) -> CapabilityStatus:
    return CapabilityStatus(state=state, reason=reason)


def build_capabilities(mode: Mode, sandbox: SandboxStatus) -> Capabilities:
    not_built = "not implemented yet"
    # A verified boundary only lifts the sandbox reason; each oracle stays unavailable until its milestone lands.
    needs_sandbox = f"{not_built} (oracles arrive in M1.4+)" if sandbox.verified else "sandbox not verified"

    def on(reason: str) -> CapabilityStatus:
        return CapabilityStatus(state=CapabilityState.ENABLED, reason=reason)

    def eco(e: Ecosystem, phase: str) -> EcosystemCapability:
        if e == Ecosystem.PYPI:
            runtime = (on("O-import witnesses in the sandbox (live repositories and fixtures)")
                       if sandbox.verified else _off(needs_sandbox))
            needs = None if sandbox.verified else "sandbox not verified: resolving and building use the sandbox"
            return EcosystemCapability(
                ecosystem=e,
                inventory=on("requirements, pyproject (PEP 621, PEP 735, Poetry), uv.lock, poetry.lock; nothing is executed"),
                resolve=on("committed lockfile, else the pinned uv at a recorded cutoff; wheels only") if not needs else _off(needs),
                world=on("hash-pinned wheels installed offline in the sandbox") if not needs else _off(needs),
                runtime_witness=runtime)
        unsupported = "deferred: expansion capability"
        if e == Ecosystem.NPM:
            return EcosystemCapability(
                ecosystem=e,
                inventory=on("package.json and package-lock.json v2/v3; nested instances kept; lifecycle scripts never run"),
                resolve=on("committed lockfile only: npm install is never run"),
                world=on("inventory world with per-importer visibility; no runtime claim"),
                runtime_witness=_off(unsupported, CapabilityState.UNSUPPORTED))
        return EcosystemCapability(
            ecosystem=e,
            inventory=on("POM coordinates, properties, in-repository parents and declared dependencies; Maven is never run"),
            resolve=_off("Maven resolution is not performed", CapabilityState.UNSUPPORTED),
            world=_off("no resolved Maven world: declared-dependency inventory only", CapabilityState.UNSUPPORTED),
            runtime_witness=_off(unsupported, CapabilityState.UNSUPPORTED))

    oracles = {name: _off(needs_sandbox) for name in
               ("o_import", "o_tests", "o_bind", "o_contract", "o_typecheck")}
    features = {
        "repository_ingestion": _off("sandbox not verified: repositories are fetched inside the sandbox"),
        "relationship_discovery": on("evidence-based L2 (published name, git dependency) for Python projects; look-alikes go to the suspected tray"),
        "witness_verification": _off("sandbox not verified"),
        "attribution_ddmin": _off("sandbox not verified"),
        "remediation_minimal": _off("sandbox not verified"),
        "evidence_bundle": on("verified evidence bundles with provenance; replaying one needs the sandbox. Replay on a different computer is not yet confirmed"),
        "llm_assistance": _off("off by design: the LLM is never in the decision path"),
    }
    if sandbox.verified:
        oracles["o_import"] = on("3 + 3 fresh runs of the modules the consumer imports, in the sandbox")
        oracles["o_tests"] = _off("implemented (M1.5) but not part of the live pipeline: reported NOT_PLANNED per cell", CapabilityState.PARTIAL)
        for name, phase in (("o_bind", "M4.6 call-site binding"), ("o_contract", "M7.1 contract replay"), ("o_typecheck", "M7.2 type checking")):
            oracles[name] = _off(f"not built ({phase})")
        features["repository_ingestion"] = on("public GitHub repositories at a pinned commit, fetched in the sandbox into immutable hashed snapshots")
        features["witness_verification"] = on("O-import witnesses under the 3 + 3 rule; O-bind and O-tests are not in the live pipeline yet")
        features["attribution_ddmin"] = on("two-sided ddmin over the world delta; forced worlds are labelled experiments")
        features["remediation_minimal"] = on("constraint diff, native re-resolution and a 3 + 3 re-run; the result is a diff and nothing is pushed")
    return Capabilities(
        capability_version=CAPABILITY_VERSION,
        api_version=API_VERSION,
        mode=mode,
        sandbox=sandbox,
        ecosystems=(eco(Ecosystem.PYPI, "phase 3"), eco(Ecosystem.NPM, "phase 3.6"), eco(Ecosystem.MAVEN, "phase 3.7")),
        oracles=oracles,
        features=features,
    )
