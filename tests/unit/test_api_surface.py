"""M6.2: static API surface and ApiDelta. Packages are parsed, never imported."""
import json

from faultline.diff.delta import REMOVED, SIGNATURE_BREAKING, SIGNATURE_CHANGED, compute_delta
from faultline.diff.surface import cached_surface, extract, read_tree, resolve

# A small package pair that models the urllib3 1.26 -> 2.x change behind scenario C: Retry loses `method_whitelist`.
RETRY_V1 = '''
class Retry:
    def __init__(self, total=10, connect=None, method_whitelist=None, allowed_methods=None, backoff_factor=0):
        pass

    def sleep(self, response=None):
        pass


def make_pool(host, port=80):
    pass


OLD_CONSTANT = 1
'''
RETRY_V2 = '''
class Retry:
    def __init__(self, total=10, connect=None, allowed_methods=None, backoff_factor=0, backoff_max=120):
        pass

    def sleep(self, response):
        pass


def make_pool(host, port=80, *, timeout=None):
    pass
'''


def pkg(**modules):
    return {f"acme_http/{name}.py" if name != "__init__" else "acme_http/__init__.py": src.encode() for name, src in modules.items()}


V1 = pkg(__init__="from .retry import Retry, make_pool\nfrom .retry import *\n", retry=RETRY_V1)
V2 = pkg(__init__="from .retry import Retry, make_pool\n", retry=RETRY_V2)


def test_tc_6_2_1_a_known_removal_is_reported_with_kind_and_old_and_new_description():
    d = compute_delta(extract(V1, "acme_http"), extract(V2, "acme_http"))
    e = d.changed("acme_http.retry.Retry")
    assert e.change == SIGNATURE_BREAKING and e.breaking and e.kind == "class"
    assert "parameter `method_whitelist` was removed" in e.details
    assert "method_whitelist=..." in e.old and "method_whitelist" not in e.new                      # old and new description
    assert "an optional parameter `backoff_max` was added" in e.details
    assert d.changed("acme_http.Retry").change == SIGNATURE_BREAKING                                # the re-export reports the same change
    gone = d.changed("acme_http.retry.OLD_CONSTANT")
    assert gone.change == REMOVED and gone.kind == "constant" and gone.breaking and gone.new is None
    assert d.breaking and d.explanatory_only and d.to_json()["explanatory_only"] is True


def test_signature_rules_separate_breaking_from_other_changes():
    d = compute_delta(extract(V1, "acme_http"), extract(V2, "acme_http"))
    sleep = d.changed("acme_http.retry.Retry.sleep")
    assert sleep.breaking and "parameter `response` became required" in sleep.details
    pool = d.changed("acme_http.retry.make_pool")
    assert pool.change == SIGNATURE_CHANGED and not pool.breaking                                    # an optional keyword-only parameter was added

    def delta(old_sig, new_sig):
        a = extract({"p/__init__.py": f"def f({old_sig}): pass\n".encode()}, "p")
        b = extract({"p/__init__.py": f"def f({new_sig}): pass\n".encode()}, "p")
        e = compute_delta(a, b).changed("p.f")
        return e and e.breaking
    assert delta("a, b=1", "a, *, b=1") is True                                                       # positional call would stop binding
    assert delta("a, b=1", "a, b") is True                                                            # optional became required
    assert delta("a", "a, b") is True                                                                 # a required parameter was added
    assert delta("a, b", "b, a") is True                                                              # order changed
    assert delta("a, b=1", "a, **kw") is True                                                         # removed, and a **kwargs would ignore it
    assert delta("a", "a, b=1") is False                                                              # an optional parameter was added
    assert delta("a, /", "a") is None                                                                 # positional-only relaxed: nothing that bound stops binding
    assert delta("a", "a") is None                                                                    # nothing changed


def test_tc_6_2_2_extraction_never_imports_the_target_code(tmp_path):
    canary = tmp_path / "canary.txt"
    root = tmp_path / "src" / "evil_pkg"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text(f"open({str(canary)!r}, 'w').write('ran')\ndef f(a): pass\n", encoding="utf-8")
    surface, _ = cached_surface(read_tree(tmp_path / "src"), "evil_pkg", tmp_path / "cache")
    assert not canary.exists()                                                                        # the module body was parsed, not executed
    assert "evil_pkg.f" in surface.symbols


def test_tc_6_2_3_limits_are_flagged_not_hidden():
    files = {"cext/__init__.py": b"__all__ = ['a']\ndef a(): pass\ndef __getattr__(name):\n    return 1\n",
             "cext/_speedups.cpython-312-x86_64-linux-gnu.so": b"\x7fELF",
             "cext/broken.py": b"def (:\n",
             "cext/dyn.py": b"from . import other\n__all__ = other.__all__ + ['z']\n"}
    s = extract(files, "cext")
    assert s.opaque_modules == ["cext._speedups"] and "cext" in s.dynamic_exports and "cext.dyn" in s.dynamic_exports
    assert s.unparsed_files == ["cext/broken.py"] and not s.complete
    d = compute_delta(s, extract({"cext/__init__.py": b"def a(): pass\n"}, "cext"))
    assert d.incomplete and d.opaque_modules and d.dynamic_exports                                    # the delta carries the limits of both surfaces


def test_reexports_wildcards_and_all_are_followed():
    files = {"w/__init__.py": b"from .core import *\nfrom ._hidden import secret as shown\n",
             "w/core.py": b"__all__ = ['visible']\ndef visible(a): pass\ndef also_public(): pass\n",
             "w/_hidden.py": b"def secret(): pass\n"}
    s = extract(files, "w")
    assert resolve(s, "w.visible").qualname == "w.core.visible" and "w.also_public" not in s.symbols  # __all__ limits what a wildcard exports
    assert resolve(s, "w.shown").qualname == "w._hidden.secret"                                       # a public re-export of a private definition resolves
    assert "w._hidden.secret" not in s.public_names() and "w.shown" in s.public_names()               # but the private module itself is not public surface


def test_surface_is_cached_by_package_hash_and_extractor_version(tmp_path):
    cache = tmp_path / "c"
    s1, hit1 = cached_surface(V1, "acme_http", cache)
    s2, hit2 = cached_surface(V1, "acme_http", cache)
    assert (hit1, hit2) == (False, True) and s1.to_json() == s2.to_json()
    _, hit3 = cached_surface({**V1, "acme_http/retry.py": RETRY_V2.encode()}, "acme_http", cache)
    assert hit3 is False                                                                              # a changed file is a different package hash
    assert json.loads(next(cache.glob("*.json")).read_text())["extractor_version"] == "surface/1"
