"""A wheel already in the wheelhouse with a hash the lock lists is used without asking the package index."""
import hashlib
import importlib.util
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[2] / "backend" / "faultline" / "oracles" / "harness"
sys.path.insert(0, str(HARNESS))
spec = importlib.util.spec_from_file_location("fetch_wheels_h", HARNESS / "fetch_wheels.py")
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)

SHA = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731

LOCK = """# Resolved by uv
click==8.1.7 \\
    --hash=sha256:{a} \\
    --hash=sha256:{b}
markupsafe==3.0.2 \\
    --hash=sha256:{c}
typing-extensions==4.12.2 \\
    --hash=sha256:{d}
"""


def test_the_lock_is_parsed_into_requirements_with_their_hashes():
    a, b, c, d = (SHA(x) for x in (b"a", b"b", b"c", b"d"))
    reqs = fw.parse_lock(LOCK.format(a=a, b=b, c=c, d=d))
    assert [(r["name"], r["version"], len(r["hashes"])) for r in reqs] == [("click", "8.1.7", 2), ("markupsafe", "3.0.2", 1), ("typing-extensions", "4.12.2", 1)]
    assert "--hash=sha256:" + a in "\n".join(reqs[0]["block"])                              # the block can be written back as a lock


def test_only_wheels_present_with_a_listed_hash_are_skipped(tmp_path):
    click_whl, ms_whl = b"click wheel bytes", b"markupsafe wheel bytes"
    (tmp_path / "click-8.1.7-py3-none-any.whl").write_bytes(click_whl)
    (tmp_path / "MarkupSafe-3.0.2-cp312-cp312-manylinux_2_17_x86_64.whl").write_bytes(b"different bytes than the lock lists")
    reqs = fw.parse_lock(LOCK.format(a=SHA(click_whl), b=SHA(b"other"), c=SHA(ms_whl), d=SHA(b"d")))
    present = {r["name"]: fw.in_wheelhouse(r, str(tmp_path)) for r in reqs}
    assert present == {"click": True, "markupsafe": False, "typing-extensions": False}     # a file with the right name but the wrong bytes is not trusted
    (tmp_path / "typing_extensions-4.12.2-py3-none-any.whl").write_bytes(b"d")
    assert fw.in_wheelhouse(reqs[2], str(tmp_path)) is True                                  # names are matched the way wheel file names spell them


def test_a_missing_wheelhouse_or_an_unhashed_requirement_is_never_treated_as_present(tmp_path):
    req = {"name": "click", "version": "8.1.7", "hashes": [SHA(b"x")], "block": []}
    assert fw.in_wheelhouse(req, str(tmp_path / "nope")) is False
    assert fw.in_wheelhouse({**req, "hashes": []}, str(tmp_path)) is False


def test_a_one_line_lock_as_written_by_render_lock_is_understood(tmp_path):
    """The dependency-edge step sends `name==version --hash=... --hash=...` on one line; it must also be served from the wheelhouse."""
    from faultline.resolvers.pinned import PinnedRequirement, render_lock
    wheel = b"markupsafe wheel"
    (tmp_path / "markupsafe-3.0.2-cp312-cp312-manylinux_2_17_x86_64.whl").write_bytes(wheel)
    text = render_lock([PinnedRequirement("markupsafe", "MarkupSafe", "3.0.2", (SHA(wheel), SHA(b"other")))])
    reqs = fw.parse_lock(text)
    assert [(r["name"], r["version"], len(r["hashes"])) for r in reqs] == [("MarkupSafe", "3.0.2", 2)]
    assert fw.in_wheelhouse(reqs[0], str(tmp_path)) is True
