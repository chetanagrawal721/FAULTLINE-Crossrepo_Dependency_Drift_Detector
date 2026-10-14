"""Capabilities must never claim more than is built: partial and FIXTURE-qualified at most, and only with a verified sandbox."""
from faultline.capabilities import build_capabilities
from faultline.core.enums import CapabilityState, Mode, SandboxState
from faultline.core.models import SandboxStatus

VERIFIED = SandboxStatus(state=SandboxState.VERIFIED, verified=True, reason="checks passed")
UNVERIFIED = SandboxStatus(state=SandboxState.UNAVAILABLE, verified=False, reason="sandbox not verified: down")


def all_statuses(c):
    yield from c.oracles.values()
    yield from c.features.values()
    for e in c.ecosystems:
        yield from (e.inventory, e.resolve, e.world, e.runtime_witness)


STATIC_ONLY = {("pypi", "inventory"), ("npm", "inventory"), ("npm", "resolve"), ("npm", "world"), ("maven", "inventory")}


def enabled_ecosystem_dimensions(c):
    return {(e.ecosystem.value, d) for e in c.ecosystems for d in ("inventory", "resolve", "world", "runtime_witness")
            if getattr(e, d).state == CapabilityState.ENABLED}


STATIC_FEATURES = {"relationship_discovery", "evidence_bundle"}              # read files and records; no execution


def test_without_a_verified_sandbox_nothing_that_executes_is_available():
    c = build_capabilities(Mode.FIXTURE, UNVERIFIED)
    assert not any(s.state == CapabilityState.ENABLED for s in c.oracles.values())
    assert {n for n, s in c.features.items() if s.state == CapabilityState.ENABLED} == STATIC_FEATURES
    assert enabled_ecosystem_dimensions(c) == STATIC_ONLY                      # only what reads files: no resolving, building or running
    pypi = next(e for e in c.ecosystems if e.ecosystem.value == "pypi")
    assert pypi.resolve.state == CapabilityState.UNAVAILABLE and "sandbox not verified" in pypi.resolve.reason
    assert pypi.world.state == CapabilityState.UNAVAILABLE and pypi.runtime_witness.state == CapabilityState.UNAVAILABLE
    assert c.oracles["o_import"].state == CapabilityState.UNAVAILABLE and c.oracles["o_import"].reason == "sandbox not verified"
    for name in ("witness_verification", "attribution_ddmin", "remediation_minimal", "repository_ingestion"):
        assert c.features[name].state == CapabilityState.UNAVAILABLE, name     # all need the sandbox


def test_with_a_verified_sandbox_exactly_what_is_built_is_enabled_and_the_rest_says_so():
    c = build_capabilities(Mode.FIXTURE, VERIFIED)
    assert {n for n, s in c.oracles.items() if s.state == CapabilityState.ENABLED} == {"o_import", "o_tests", "o_bind", "o_contract"}
    assert c.oracles["o_tests"].state == CapabilityState.ENABLED and "NOT PLANNED" in c.oracles["o_tests"].reason     # built, with its condition stated
    enabled = {n for n, s in c.features.items() if s.state == CapabilityState.ENABLED}
    assert enabled == {"repository_ingestion", "relationship_discovery", "witness_verification", "attribution_ddmin", "remediation_minimal", "evidence_bundle"}
    assert c.features["llm_assistance"].state == CapabilityState.UNAVAILABLE
    assert "Replay on a different computer is not yet confirmed" in c.features["evidence_bundle"].reason      # an unfinished claim is stated
    assert "O-tests" in c.features["witness_verification"].reason
    pypi = next(e for e in c.ecosystems if e.ecosystem.value == "pypi")
    assert pypi.runtime_witness.state == CapabilityState.ENABLED
    assert enabled_ecosystem_dimensions(c) == STATIC_ONLY | {("pypi", "resolve"), ("pypi", "world"), ("pypi", "runtime_witness")}
    assert c.oracles["o_bind"].state == CapabilityState.ENABLED and "not executed" in c.oracles["o_bind"].reason           # built, with its limits stated
    assert c.oracles["o_contract"].state == CapabilityState.ENABLED and "assumed" in c.oracles["o_contract"].reason          # built, with its limits stated
    assert c.oracles["o_typecheck"].state == CapabilityState.UNAVAILABLE and "not built" in c.oracles["o_typecheck"].reason   # unfinished items are visible, not hidden
    npm = next(e for e in c.ecosystems if e.ecosystem.value == "npm")
    assert npm.runtime_witness.state == CapabilityState.UNSUPPORTED
    maven = next(e for e in c.ecosystems if e.ecosystem.value == "maven")
    assert maven.resolve.state == CapabilityState.UNSUPPORTED and maven.world.state == CapabilityState.UNSUPPORTED
