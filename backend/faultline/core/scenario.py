"""Fixture scenario specification: executable expected outcomes (fixtures/scenarios/<ID>.yaml).

Expected values are written before detection code exists. Tests assert Faultline's output equals them.
"""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import Verdict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactSpec(Strict):
    repo: str
    path: str                       # relative to repository root
    import_package: str
    src: str = "src"
    tests: str = "tests"
    runtime_lock: str = "requirements.lock.txt"
    test_lock: str = "requirements.test.lock.txt"


class ConsumerSpec(Strict):
    repo: str
    path: str
    lock: str = "requirements.lock.txt"
    imports: list[str]              # artifact modules the consumer imports (PC-4)


class Control(Strict):
    kind: Literal["no_drift", "harmless_drift", "unrelated_drift", "lookalike"]
    reason: str


class Signature(Strict):
    exc_type: str
    message_contains: str


class Attribution(Strict):
    minimal_set: list[str]
    sidedness: Literal["two_sided", "one_sided", "untestable"]


class CellExpectation(Strict):
    consumer: str
    delta: list[str] = Field(default_factory=list)   # names that differ between the two locks (added/removed/changed)
    state: Literal["NO_DRIFT", "ANALYZED", "NOT_APPLICABLE", "INCONCLUSIVE"]
    verdict: Verdict | None = None
    oracle: str | None = None
    entry_point: str | None = None
    signature: Signature | None = None
    attribution: Attribution | None = None
    witness: bool = False                            # is a witness expected?
    control: Control | None = None                   # set on negative controls

    @model_validator(mode="after")
    def _consistent(self):
        if self.witness and self.signature is None:
            raise ValueError("a cell expecting a witness must give the expected signature")
        if self.state == "NO_DRIFT" and self.delta:
            raise ValueError("NO_DRIFT cell cannot list a delta")
        if self.state == "NO_DRIFT" and self.witness:
            raise ValueError("NO_DRIFT cell cannot expect a witness")
        return self


class RelationshipExpectation(Strict):
    producer: str
    consumer: str
    level: Literal["L2", "L3", "L4"]


class SuspectedExpectation(Strict):
    producer: str
    consumer: str
    kind: str = "SUSPECTED_TWIN"


class TimeMachine(Strict):
    reference_cutoff: str           # RFC 3339: the world is resolved as of this time (before the dependency's release)
    consumer_cutoff: str            # RFC 3339: and as of this time (after it)


class RealSource(Strict):
    url: str
    ref: str


class Bystander(Strict):
    """A repository that must NOT be related to the artifact (hygiene control or look-alike)."""
    repo: str
    path: str
    kind: Literal["unrelated", "lookalike"]


class Expect(Strict):
    relationships: list[RelationshipExpectation]
    cells: list[CellExpectation]
    suspected: list[SuspectedExpectation] = Field(default_factory=list)
    unrelated: list[str] = Field(default_factory=list)         # repos that must have no relationship with the artifact at all


class Scenario(Strict):
    id: str
    title: str
    kind: Literal["fixture", "real_world"] = "fixture"
    verified_by: str | None = None
    runtime: str = "3.12"
    artifact: ArtifactSpec
    consumers: list[ConsumerSpec]
    bystanders: list[Bystander] = Field(default_factory=list)
    truth: Literal["break", "silent_divergence", "no_break", "not_a_finding"] | None = None   # the committed ground-truth label
    real_source: RealSource | None = None                       # real_world scenarios: the public repository and the tag it is pinned at
    time_machine: TimeMachine | None = None
    public_evidence: list[str] = Field(default_factory=list)    # public issue or changelog links that describe the break
    evaluated: bool = True                                    # False: registered with its label, but the MVP cannot observe it
    not_evaluated_reason: str | None = None
    expect: Expect

    @model_validator(mode="after")
    def _consumers_match(self):
        if self.kind == "real_world":
            return self
        names = {c.repo for c in self.consumers}
        for cell in self.expect.cells:
            if cell.consumer not in names:
                raise ValueError(f"expectation names unknown consumer {cell.consumer}")
        return self

    @property
    def breaks(self) -> bool:
        return any(c.witness for c in self.expect.cells)


def load_scenario(path: Path) -> Scenario:
    return Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
