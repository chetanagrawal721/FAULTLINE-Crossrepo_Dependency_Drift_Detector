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
