import pytest

from faultline.core.errors import FaultlineError
from faultline.resolvers.pinned import canonical_name, diff_locks, parse_pinned_lock

H = "a" * 64
G = "b" * 64
BS = "\\"          # a literal backslash (line continuation in lock files)


def test_parses_hash_pinned_lines_with_continuations():
    text = (f"# header\nFlask==2.2.2 {BS}\n    --hash=sha256:{H} {BS}\n    --hash=sha256:{G}\n"
            f"click==8.1.7 --hash=sha256:{H}\n")
    reqs = parse_pinned_lock(text)
    assert [(r.name, r.version, len(r.hashes)) for r in reqs] == [("click", "8.1.7", 1), ("flask", "2.2.2", 2)]
    assert reqs[1].display_name == "Flask"


@pytest.mark.parametrize("bad", ["", "# only a comment\n", "flask>=2\n", "-e .\n", "pkg @ git+https://x/y\n",
                                 f"flask==2.2.2 {BS}\n", "flask==1\nflask==2\n", "flask==1 ; python_version<'3.9'\n"])
def test_unparseable_locks_raise_instead_of_producing_an_empty_world(bad):
    with pytest.raises(FaultlineError) as ei:
        parse_pinned_lock(bad)
    assert ei.value.code.value == "MANIFEST_PARSE_FAILED"


def test_canonical_names():
    assert canonical_name("Foo_Bar.baz") == "foo-bar-baz" == canonical_name("FOO-bar_Baz")


def test_diff_locks_reports_changed_added_and_removed():
    a = parse_pinned_lock(f"a==1 --hash=sha256:{H}\nb==1 --hash=sha256:{H}\nc==1 --hash=sha256:{H}\n")
    b = parse_pinned_lock(f"a==1 --hash=sha256:{H}\nb==2 --hash=sha256:{H}\nd==1 --hash=sha256:{H}\n")
    assert diff_locks(a, b) == {"b": ("1", "2"), "c": ("1", None), "d": (None, "1")}
