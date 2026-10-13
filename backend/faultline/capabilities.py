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
            runtime = (CapabilityStatus(state=CapabilityState.PARTIAL, reason="FIXTURE scenarios only")
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
    fixture_only = "FIXTURE scenarios only: committed fixture repositories, not live ingestion"
    features = {
        "repository_ingestion": _off(f"{not_built} (phase 2)"),
        "relationship_discovery": _off(f"{not_built} (phase 4)"),
        "witness_verification": _off("sandbox not verified" if not sandbox.verified else f"{not_built}"),
        "attribution_ddmin": _off(f"{not_built} (phase 5)"),
        "evidence_bundle": _off(f"{not_built}"),
        "llm_assistance": _off("off by design: the LLM is never in the decision path"),
    }
    if sandbox.verified:
        # what is genuinely built and tested at this point (milestones M1.4 to M1.7), and only what is
        oracles["o_import"] = CapabilityStatus(state=CapabilityState.PARTIAL, reason=fixture_only)
        oracles["o_tests"] = _off("implemented (M1.5) but not part of the scenario pipeline yet", CapabilityState.PARTIAL)
        features["repository_ingestion"] = CapabilityStatus(
            state=CapabilityState.ENABLED, reason="public GitHub repositories at a pinned commit; snapshot and inventory only")
        features["witness_verification"] = CapabilityStatus(state=CapabilityState.PARTIAL, reason=fixture_only)
        features["evidence_bundle"] = CapabilityStatus(state=CapabilityState.PARTIAL, reason=fixture_only + "; replay not built (M5.2)")
    return Capabilities(
        capability_version=CAPABILITY_VERSION,
        api_version=API_VERSION,
        mode=mode,
        sandbox=sandbox,
        ecosystems=(eco(Ecosystem.PYPI, "phase 3"), eco(Ecosystem.NPM, "phase 3.6"), eco(Ecosystem.MAVEN, "phase 3.7")),
        oracles=oracles,
        features=features,
    )
