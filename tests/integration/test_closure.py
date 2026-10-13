"""The artifact's runtime closure from real wheel metadata, and what it does to projections."""
import pytest

from faultline.core.scenario import load_scenario
from faultline.resolvers.pinned import parse_pinned_lock
from faultline.worlds.closure import closure, reach, requires_of
from faultline.worlds.projection import project
from faultline.worlds.reference import ReferenceWorld
from tests.livefix import FIXTURES, lock_text

ROOT = FIXTURES.parents[1]
ROOTS = [("pydantic", frozenset()), ("flask", frozenset())]        # acme-models[web]: pydantic plus the web extra


def test_requires_of_follows_markers_and_extras():
    raw = ["jinja2>=3.0", 'importlib-metadata>=3.6; python_version < "3.10"', 'asgiref>=3.2; extra == "async"', 'colorama; platform_system == "Windows"']
    assert requires_of(raw, frozenset()) == [("jinja2", frozenset())]                                  # py3.12 linux, no extras
    assert ("asgiref", frozenset()) in requires_of(raw, frozenset({"async"}))


def test_unrelated_packages_are_outside_the_closure():
    edges = {"flask": ["werkzeug>=2.2"], "werkzeug": ["markupsafe"], "requests": ["urllib3", "idna"], "pydantic": []}
    present = {"flask", "werkzeug", "markupsafe", "requests", "urllib3", "idna", "pydantic"}
    got = reach(ROOTS, present, edges)
    assert got == {"flask", "werkzeug", "markupsafe", "pydantic"} and "requests" not in got
    assert reach(ROOTS, {"pydantic"}, edges) == {"pydantic"}                                           # an absent extra is simply not reached


@pytest.mark.docker
def test_real_wheel_metadata_gives_the_closure_and_the_scenario_deltas(sbx, image):
    from faultline.worlds.builder import WorldBuilder
    b = WorldBuilder(sbx, image)
    ref_p = parse_pinned_lock(lock_text("acme-models"))
    ref = ReferenceWorld("p", "w_ref", tuple(ref_p), "lockfile")
    ref_edges = b.edges(ref_p)
    assert {"werkzeug", "jinja2", "itsdangerous", "click"} <= {n for n, _ in requires_of(ref_edges["flask"], frozenset())}
    assert closure(ref_p, ROOTS, ref_edges) == {p.name for p in ref_p}                                  # every reference package is in the closure

    h = parse_pinned_lock(lock_text("billing-svc/H"))
    h_closure = closure(h, ROOTS, b.edges(h))
    assert h_closure == {"pydantic", "pydantic-core", "annotated-types", "typing-extensions"}
    sc = load_scenario(ROOT / "fixtures" / "scenarios" / "H.yaml")
    proj = project(ref, h, ref_names=closure(ref_p, ROOTS, ref_edges), consumer_names=h_closure)
    expected = next(c for c in sc.expect.cells if c.consumer == "billing-svc").delta
    assert sorted(d.name for d in proj.delta) == sorted(expected)                                       # still equals the YAML exactly
