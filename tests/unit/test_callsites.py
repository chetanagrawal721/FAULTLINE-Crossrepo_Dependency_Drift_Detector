"""M4.6: the minimal call-site extractor. Golden records were reviewed by hand against tests/data/callsites_sample.py."""
from pathlib import Path

from faultline.core.hashing import content_hash
from faultline.usage.callsites import extract_callsites, extract_file, persist_callsites

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "callsites_sample.py"
D = {"urllib3", "requests", "yaml"}

# (line, col, callee, status, n_positional, keyword_names, star, dstar, literals, flags)
GOLDEN = [
    (10, 8, "urllib3.PoolManager", "RESOLVED", 1, (), False, False, {"args": [10], "kwargs": {}}, ()),                                       # attribute chain, positional
    (11, 8, "urllib3.util.retry.Retry", "RESOLVED", 0, ("total", "method_whitelist"), False, False,
     {"args": [], "kwargs": {"total": 3, "method_whitelist": ["GET"]}}, ()),                                                                  # from-import alias, keywords, all literal
    (12, 8, "urllib3.util.retry.Retry", "RESOLVED", 0, (), True, True, None, ()),                                                             # module alias, star and double star
    (13, 8, "urllib3.PoolManager", "RESOLVED", 0, ("num_pools", "headers"), False, False, None, ()),                                         # from-import, a non-literal argument
    (14, 8, "urllib3.PoolManager", "RESOLVED", 1, (), False, False, {"args": [1], "kwargs": {}}, ()),                                        # getattr with a literal name
    (15, 8, None, "DYNAMIC", 2, (), False, False, None, ("DYNAMIC_GETATTR",)),                                                              # getattr with a computed name
    (16, 8, None, "DYNAMIC", 1, (), False, False, None, ("DYNAMIC_IMPORT",)),                                                               # import_module with a computed name
    (18, 4, None, "UNRESOLVED", 1, (), False, False, {"args": ["1+1"], "kwargs": {}}, ()),                                                 # eval
    (33, 4, "requests.get", "RESOLVED", 1, ("timeout",), False, False, {"args": ["http://x"], "kwargs": {"timeout": 3}}, ("OPTIONAL_PATH",)),
    (34, 4, "yaml.safe_load", "RESOLVED", 1, (), False, False, {"args": ["a: 1"], "kwargs": {}}, ("TYPE_ONLY",)),
]


def row(s):
    return (s.line, s.col, s.callee, s.status, s.n_positional, s.keyword_names, s.has_star_args, s.has_star_kwargs, s.literals, s.flags)


def test_tc_4_6_1_records_match_the_golden_file_including_line_and_column():
    src = SAMPLE.read_bytes()
    sites = extract_file("sample.py", src, D)
    assert [row(s) for s in sites] == GOLDEN
    assert all(s.file == "sample.py" and s.file_sha256 == content_hash(src) for s in sites)       # every record names its file hash
    assert [s.site_id for s in sites][:2] == ["sample.py:10:8", "sample.py:11:8"]
    assert {s.package for s in sites if s.status == "RESOLVED"} == {"urllib3", "requests", "yaml"}


def test_only_calls_into_divergent_packages_are_recorded_as_resolved():
    sites = extract_file("sample.py", SAMPLE.read_bytes(), {"urllib3"})
    assert {s.callee for s in sites if s.status == "RESOLVED"} == {"urllib3.PoolManager", "urllib3.util.retry.Retry"}
    assert all("os.path.join" != s.callee for s in sites)                                                       # os.path.join is not divergent


def test_tc_4_6_3_dynamic_and_unresolved_forms_are_recorded_and_never_treated_as_absent():
    src = (b"import importlib, urllib3, os\n"
           b"x = getattr(urllib3, name)(1)\n"
           b"y = importlib.import_module(var)\n"
           b"z = __import__(var)\n"
           b"exec(code)\n"
           b"w = importlib.import_module('json')\n")                                                          # a literal import is not dynamic
    sites = extract_file("m.py", src, {"urllib3"})
    by = {(s.line, s.status) for s in sites}
    assert (2, "DYNAMIC") in by and (3, "DYNAMIC") in by and (4, "DYNAMIC") in by and (5, "UNRESOLVED") in by
    assert not any(s.line == 6 for s in sites)
    assert all(s.callee is None and s.reason for s in sites if s.status in ("DYNAMIC", "UNRESOLVED"))           # recorded with a reason, with no guessed target


def test_extraction_reads_source_and_never_runs_it(tmp_path):
    marker = tmp_path / "ran.txt"
    src = f"import urllib3\nopen({str(marker)!r}, 'w').write('x')\nraise SystemExit('should never run')\nurllib3.PoolManager(1)\n"
    sites = extract_file("evil.py", src, {"urllib3"})
    assert not marker.exists() and [s.callee for s in sites if s.status == "RESOLVED"] == ["urllib3.PoolManager"]


def test_a_file_that_does_not_parse_yields_no_records_and_no_error():
    assert extract_file("bad.py", b"def (:\n", D) == []


def test_a_source_tree_reads_only_python_files_in_a_stable_order():
    files = {"b.py": b"import urllib3\nurllib3.PoolManager()\n", "a.py": b"import urllib3\nurllib3.Retry()\n", "notes.txt": b"urllib3.PoolManager()"}
    sites = extract_callsites(files, {"urllib3"})
    assert [(s.file, s.callee) for s in sites] == [("a.py", "urllib3.Retry"), ("b.py", "urllib3.PoolManager")]


def test_records_are_persisted_per_file_hash_and_call_site(conn):
    src = SAMPLE.read_bytes()
    sites = extract_file("sample.py", src, D)
    assert persist_callsites(conn, sites, {"sample.py": src}) == len(sites)
    persist_callsites(conn, sites, {"sample.py": src})                                                           # idempotent
    assert conn.execute("SELECT COUNT(*) FROM usage_ref").fetchone()[0] == len(sites)
    assert conn.execute("SELECT COUNT(*) FROM usage_file").fetchone()[0] == 1
    r = conn.execute("SELECT * FROM usage_ref WHERE line=11").fetchone()
    assert r["target"] == "urllib3.util.retry.Retry" and r["root_package"] == "urllib3" and '"method_whitelist"' in r["call_shape_json"]


# ----------------------------------------------------------------------------- which call sites belong to a consumer (PC-4 applied to O-bind)

def test_module_names_follow_the_source_root():
    from faultline.analysis.bind import module_of
    assert module_of("src/acme/web.py", "src") == "acme.web" and module_of("src/acme/__init__.py", "src") == "acme"
    assert module_of("acme/web.py", ".") == "acme.web" and module_of("other/x.py", "src") is None


def test_reachable_modules_follow_the_artifacts_own_imports_and_parent_packages():
    from faultline.analysis.bind import reachable_modules
    files = {
        "src/acme/__init__.py": b"",
        "src/acme/customer.py": b"from pydantic import BaseModel\nfrom .base import Base\n",
        "src/acme/base.py": b"import acme.util\n",
        "src/acme/util.py": b"from . import helpers\n",
        "src/acme/helpers.py": b"",
        "src/acme/web.py": b"import flask\nfrom acme import customer\n",          # imports customer, but the consumer does not import web
        "src/acme/settings.py": b"",
    }
    assert reachable_modules(files, "src", {"acme.customer"}) == {"acme", "acme.customer", "acme.base", "acme.util", "acme.helpers"}
    assert reachable_modules(files, "src", {"acme.web"}) >= {"acme", "acme.web", "acme.customer", "acme.base"}          # web pulls customer in, not the reverse
    assert "acme.web" not in reachable_modules(files, "src", {"acme.customer"}) and "acme.settings" not in reachable_modules(files, "src", {"acme.customer"})


def test_sites_in_modules_the_consumer_never_loads_are_not_planned(conn, tmp_path):
    from faultline.analysis.bind import find_sites
    pkg = tmp_path / "src" / "acme"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "customer.py").write_text("import pydantic\npydantic.Field(default=1)\n")
    (pkg / "web.py").write_text("import flask\nflask.Flask('x')\n")
    both, _ = find_sites(conn, tmp_path, ["pydantic", "flask"], src_root="src", consumer_modules=None)
    only, _ = find_sites(conn, tmp_path, ["pydantic", "flask"], src_root="src", consumer_modules={"acme", "acme.customer"})
    assert {s.callee for s in both} == {"pydantic.Field", "flask.Flask"}
    assert {s.callee for s in only} == {"pydantic.Field"}                                              # flask.Flask lives in web.py, which this consumer never loads
