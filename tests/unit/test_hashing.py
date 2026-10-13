"""TC-0.3.1, TC-0.3.2, TC-0.3.3 and the single-hash-owner policy."""
import random
import re
from pathlib import Path

import pytest

from faultline.core.errors import CanonicalizationError
from faultline.core.hashing import canonical_json, env_profile_id, object_hash, world_hash
from faultline.core.models import EnvProfile, ResolvedWorld, Runtime, WorldEntry

ENV = EnvProfile(image_ref="local@sha256:" + "a" * 64)
RT = Runtime(name="cpython", version="3.12.15")


def make_world(entries, runtime=RT, env=ENV, **extra):
    return ResolvedWorld(world_hash="x", ecosystem="pypi", kind="reference", runtime=runtime,
                         env_profile_id=env_profile_id(env), entries=tuple(entries), **extra)


def entry(name="pydantic", version="1.10.13", **kw):
    return WorldEntry(locator=name, name=name, version=version, **kw)


BASE = [entry("pydantic", "1.10.13"), entry("flask", "2.2.2"), entry("werkzeug", "2.2.3")]


def test_tc_0_3_1_order_independence():
    hashes = set()
    for seed in range(100):
        rnd = random.Random(seed)
        shuffled = BASE[:]
        rnd.shuffle(shuffled)
        hashes.add(world_hash(make_world(shuffled)))
    assert len(hashes) == 1


def test_canonical_json_key_order_independent():
    assert canonical_json({"b": 1, "a": [2, 1]}) == canonical_json({"a": [2, 1], "b": 1})


@pytest.mark.parametrize("mutate", [
    lambda: make_world([entry("pydantic", "1.10.14")] + BASE[1:]),                                   # version
    lambda: make_world(BASE, runtime=Runtime(name="cpython", version="3.11.9")),                      # runtime minor
    lambda: make_world(BASE, env=EnvProfile(image_ref=ENV.image_ref, arch="arm64")),                  # platform
    lambda: make_world([entry("pydantic", "1.10.13", artifact_sha256="b" * 64)] + BASE[1:]),          # artifact hash
])
def test_tc_0_3_2_semantic_changes_change_hash(mutate):
    assert world_hash(mutate()) != world_hash(make_world(BASE))


def test_tc_0_3_2_non_semantic_data_is_ignored():
    base = world_hash(make_world(BASE))
    with_parents = [WorldEntry(locator=e.locator, name=e.name, version=e.version, parents=("<root>", "x"))
                    for e in BASE]
    assert world_hash(make_world(with_parents)) == base
    # extra non-semantic keys in a dict form (timestamps, local paths, provenance) do not matter
    d = {"ecosystem": "pypi", "runtime": RT.model_dump(), "env_profile_id": env_profile_id(ENV),
         "entries": [e.model_dump() for e in BASE],
         "provenance": {"resolved_at": "2026-10-13T00:00:00Z"}, "venv_path": "C:/Users/x/venv"}
    assert world_hash(d) == base


def test_nested_instances_stay_distinct():
    a = make_world([WorldEntry(locator="node_modules/a/node_modules/x", name="x", version="1.0.0"),
                    WorldEntry(locator="node_modules/x", name="x", version="2.0.0")])
    b = make_world([WorldEntry(locator="node_modules/x", name="x", version="2.0.0"),
                    WorldEntry(locator="node_modules/b/node_modules/x", name="x", version="1.0.0")])
    assert world_hash(a) != world_hash(b)


def test_tc_0_3_3_nan_and_infinity_rejected():
    for bad in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(CanonicalizationError):
            canonical_json({"v": bad})


def test_tc_0_3_3_float_edge_cases_are_deterministic():
    assert canonical_json({"v": -0.0}) == canonical_json({"v": -0.0}) == b'{"v":-0.0}'
    big = 1.7976931348623157e308
    assert canonical_json({"v": big}) == canonical_json({"v": big})
    assert canonical_json({"v": 3}) == b'{"v":3}'          # ints stay ints


def test_unsupported_types_rejected():
    with pytest.raises(CanonicalizationError):
        canonical_json({"v": {1, 2}})
    with pytest.raises(CanonicalizationError):
        canonical_json({1: "int key"})


def test_object_hash_is_stable():
    assert object_hash({"a": 1}) == object_hash({"a": 1})


def test_hash_policy_only_core_hashing_and_migration_checksums_use_hashlib():
    """Only core/hashing.py computes identity hashes. migrate.py checksums migration files (not identities)."""
    root = Path(__file__).resolve().parents[2] / "backend" / "faultline"
    allowed = {root / "core" / "hashing.py", root / "storage" / "migrate.py"}
    harness = root / "oracles" / "harness"      # runs inside the container, stdlib only, hashes downloaded wheel files
    offenders = [str(p.relative_to(root)) for p in root.rglob("*.py")
                 if p not in allowed and harness not in p.parents and re.search(r"\bhashlib\b|\bsha256\(", p.read_text(encoding="utf-8"))]
    assert offenders == []
