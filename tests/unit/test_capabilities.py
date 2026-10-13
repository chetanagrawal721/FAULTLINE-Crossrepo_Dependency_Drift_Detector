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


def test_without_a_verified_sandbox_nothing_that_executes_is_available():
    c = build_capabilities(Mode.FIXTURE, UNVERIFIED)
    assert not any(s.state == CapabilityState.ENABLED for s in [*c.oracles.values(), *c.features.values()])
    assert enabled_ecosystem_dimensions(c) == STATIC_ONLY                      # only what reads files: no resolving, building or running
    pypi = next(e for e in c.ecosystems if e.ecosystem.value == "pypi")
    assert pypi.resolve.state == CapabilityState.UNAVAILABLE and "sandbox not verified" in pypi.resolve.reason
    assert pypi.world.state == CapabilityState.UNAVAILABLE
    assert c.oracles["o_import"].state == CapabilityState.UNAVAILABLE and c.oracles["o_import"].reason == "sandbox not verified"
    assert c.features["witness_verification"].state == CapabilityState.UNAVAILABLE
    assert c.features["evidence_bundle"].state == CapabilityState.UNAVAILABLE
    assert c.features["repository_ingestion"].state == CapabilityState.UNAVAILABLE      # needs the sandboxed fetch zone


def test_with_a_verified_sandbox_only_fixture_scoped_partial_capabilities_appear():
    c = build_capabilities(Mode.FIXTURE, VERIFIED)
    assert c.oracles["o_import"].state == CapabilityState.PARTIAL and "FIXTURE" in c.oracles["o_import"].reason
    assert c.features["witness_verification"].state == CapabilityState.PARTIAL
    assert "replay not built" in c.features["evidence_bundle"].reason
    pypi = next(e for e in c.ecosystems if e.ecosystem.value == "pypi")
    assert pypi.runtime_witness.state == CapabilityState.PARTIAL and "FIXTURE" in pypi.runtime_witness.reason
    enabled = {n for n, s in c.features.items() if s.state == CapabilityState.ENABLED}
    assert enabled == {"repository_ingestion"}                                        # the only fully built feature so far
    assert not any(s.state == CapabilityState.ENABLED for s in c.oracles.values())
    assert enabled_ecosystem_dimensions(c) == STATIC_ONLY | {("pypi", "resolve"), ("pypi", "world")}   # runtime witnesses stay off
    for name in ("o_bind", "o_contract", "o_typecheck"):
        assert c.oracles[name].state == CapabilityState.UNAVAILABLE
    for name in ("relationship_discovery", "attribution_ddmin"):
        assert c.features[name].state == CapabilityState.UNAVAILABLE
    npm = next(e for e in c.ecosystems if e.ecosystem.value == "npm")
    assert npm.runtime_witness.state == CapabilityState.UNSUPPORTED
    maven = next(e for e in c.ecosystems if e.ecosystem.value == "maven")
    assert maven.resolve.state == CapabilityState.UNSUPPORTED and maven.world.state == CapabilityState.UNSUPPORTED
