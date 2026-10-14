from faultline.oracles.artifacts import content_hash, prepare_artifact
from faultline.storage.store import Store


def tree(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def test_content_hash_depends_on_bytes_and_paths_not_order_or_caches(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    tree(a, {"src/m.py": "x = 1\n", "src/n.py": "y = 2\n"})
    tree(b, {"src/n.py": "y = 2\n", "src/m.py": "x = 1\n", "src/__pycache__/m.cpython-312.pyc": "junk"})
    assert content_hash(a) == content_hash(b)
    (b / "src" / "m.py").write_text("x = 2\n", encoding="utf-8")
    assert content_hash(a) != content_hash(b)
    c = tmp_path / "c"
    tree(c, {"src/m2.py": "x = 1\n", "src/n.py": "y = 2\n"})        # renamed file
    assert content_hash(a) != content_hash(c)


def test_prepare_artifact_is_idempotent_and_content_addressed(tmp_path):
    src = tmp_path / "src"
    tree(src, {"pkg/__init__.py": "v = 1\n"})
    store = Store(tmp_path / "store")
    h1 = prepare_artifact(src, store)
    h2 = prepare_artifact(src, store)
    assert h1 == h2 and (store.artifact_dir(h1) / "pkg" / "__init__.py").read_text(encoding="utf-8") == "v = 1\n"


def test_a_refused_rename_is_retried_and_a_copy_finished_by_another_process_is_accepted(tmp_path, monkeypatch):
    """Windows can refuse to rename a new folder for a moment (a virus scanner holds it). That must not fail an analysis."""
    import time
    from pathlib import Path

    from faultline.oracles import artifacts
    from faultline.storage.store import Store
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    real = Path.rename
    calls = {"n": 0}

    def flaky(self, target):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(5, "Access is denied")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", flaky)
    store = Store(tmp_path / "store")
    h = artifacts.prepare_artifact(src, store)
    assert calls["n"] == 3 and (store.artifact_dir(h) / "pkg" / "__init__.py").read_text() == "x = 1\n"
    assert not list((tmp_path / "store" / "artifacts").glob("*.tmp"))                       # no half-copied folder is left behind

    def refuse(self, target):
        Path(target).mkdir(parents=True, exist_ok=True)                                     # someone else won the race
        raise PermissionError(5, "Access is denied")
    other = Store(tmp_path / "store2")
    monkeypatch.setattr(Path, "rename", refuse)
    h2 = artifacts.prepare_artifact(src, other)
    assert other.artifact_dir(h2).exists() and not list((tmp_path / "store2" / "artifacts").glob("*.tmp"))


def test_the_content_hash_does_not_depend_on_how_the_operating_system_orders_file_names(tmp_path):
    """Windows sorts Path objects case-insensitively, Linux case-sensitively. The hash must be the same for the same files on both."""
    import json

    from faultline.core.hashing import object_hash, sha256_hex
    from faultline.oracles import artifacts
    (tmp_path / "pkg").mkdir()
    for name, text in (("README.md", "r"), ("a.py", "a"), ("B.py", "b"), ("pkg/Zed.py", "z"), ("pkg/alpha.py", "x")):
        (tmp_path / name).write_text(text, encoding="utf-8")
    expected = sorted([n, sha256_hex(t.encode())] for n, t in (("README.md", "r"), ("a.py", "a"), ("B.py", "b"), ("pkg/Zed.py", "z"), ("pkg/alpha.py", "x")))
    assert [e[0] for e in expected] == ["B.py", "README.md", "a.py", "pkg/Zed.py", "pkg/alpha.py"]             # plain string order, upper case first
    assert artifacts.content_hash(tmp_path) == "a_" + object_hash(expected)[:40]
    assert json.dumps(expected)
