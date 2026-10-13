"""The frozen contract: models reject unknown fields and enums match the master vocabulary."""
import pytest
from pydantic import ValidationError

from faultline.core.enums import Verdict
from faultline.core.models import EnvProfile, Runtime, WorldEntry

MASTER_VERDICTS = {"BREAK_WITNESSED", "SILENT_DIVERGENCE_WITNESSED", "NO_DIVERGENCE_OBSERVED", "EXPOSED",
                   "POTENTIAL", "NOT_EXPOSED", "INCONCLUSIVE", "HYGIENE"}


def test_verdict_vocabulary_matches_master_exactly():
    assert {v.value for v in Verdict} == MASTER_VERDICTS


def test_models_forbid_extra_fields_and_are_frozen():
    with pytest.raises(ValidationError):
        Runtime(name="cpython", version="3.12", extra_field=1)
    r = Runtime(name="cpython", version="3.12")
    with pytest.raises(ValidationError):
        r.version = "3.13"


def test_invalid_values_rejected():
    with pytest.raises(ValidationError):
        Runtime(name="ruby", version="3")
    with pytest.raises(ValidationError):
        WorldEntry(locator="x", name="x", version="1", artifact_sha256="not-a-hash")
    assert EnvProfile(image_ref="x").tz == "UTC"
