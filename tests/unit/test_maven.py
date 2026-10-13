"""M3.7: Maven POM inventory. Properties, in-repository parents, unsupported external parents and hostile XML."""
import re
import socket
import subprocess
import threading
from pathlib import Path

import pytest

from faultline.parsers.common import SnapshotFS
from faultline.parsers.maven.pom import discover_maven, load_pom_tree, read_pom
from tests.snapshots import make_snapshot

NS = 'xmlns="http://maven.apache.org/POM/4.0.0"'

ROOT = f"""<?xml version="1.0"?>
<project {NS}>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId><artifactId>acme-parent</artifactId><version>1.0.0</version><packaging>pom</packaging>
  <modules><module>core</module><module>api</module></modules>
  <properties><jackson.version>2.17.0</jackson.version><junit.version>4.13.2</junit.version></properties>
  <dependencyManagement><dependencies>
    <dependency><groupId>com.fasterxml.jackson.core</groupId><artifactId>jackson-databind</artifactId><version>${{jackson.version}}</version></dependency>
  </dependencies></dependencyManagement>
</project>"""

CORE = f"""<project {NS}>
  <parent><groupId>com.acme</groupId><artifactId>acme-parent</artifactId><version>1.0.0</version></parent>
  <artifactId>acme-core</artifactId>
  <dependencies>
    <dependency><groupId>com.fasterxml.jackson.core</groupId><artifactId>jackson-databind</artifactId></dependency>
    <dependency><groupId>junit</groupId><artifactId>junit</artifactId><version>${{junit.version}}</version><scope>test</scope></dependency>
    <dependency><groupId>org.slf4j</groupId><artifactId>slf4j-api</artifactId><version>2.0.13</version><optional>true</optional></dependency>
  </dependencies>
</project>"""

API = f"""<project {NS}>
  <parent><groupId>com.acme</groupId><artifactId>acme-parent</artifactId><version>1.0.0</version></parent>
  <artifactId>acme-api</artifactId>
  <dependencies>
    <dependency><groupId>com.acme</groupId><artifactId>acme-core</artifactId><version>${{project.version}}</version></dependency>
    <dependency><groupId>org.unknown</groupId><artifactId>no-version</artifactId></dependency>
  </dependencies>
</project>"""


def projects(tmp_path, files):
    root, inv = make_snapshot(tmp_path, files)
    return {p.rel_path: p for p in discover_maven(root, inv)}


def test_tc_3_7_1_properties_and_in_repository_parent(tmp_path):
    ps = projects(tmp_path, {"pom.xml": ROOT, "core/pom.xml": CORE, "api/pom.xml": API})
    assert set(ps) == {".", "core", "api"}
    core, api = ps["core"].pom, ps["api"].pom
    assert (core.group_id, core.artifact_id, core.version) == ("com.acme", "acme-core", "1.0.0")      # inherited from the in-repo parent
    assert core.parent["found_in_repository"] and core.parent["path"] == "pom.xml"
    deps = {d.artifact_id: d for d in core.dependencies}
    assert (deps["jackson-databind"].version, deps["jackson-databind"].version_source) == ("2.17.0", "managed")   # parent property inside parent management
    assert (deps["junit"].version, deps["junit"].version_source, deps["junit"].scope) == ("4.13.2", "property", "test")
    assert deps["slf4j-api"].optional and deps["slf4j-api"].version == "2.0.13"
    adeps = {d.artifact_id: d for d in api.dependencies}
    assert adeps["acme-core"].version == "1.0.0"                                                       # ${project.version}
    assert adeps["no-version"].version is None and adeps["no-version"].version_source == "unresolved"  # not guessed
    assert ps["core"].module_of == "." and ps["api"].module_of == "." and ps["."].module_of is None   # module boundaries preserved
    assert ps["."].pom.modules == ["core", "api"] and ps["."].pom.packaging == "pom"


def test_tc_3_7_2_external_parent_and_bom_are_unsupported_and_unresolved(tmp_path):
    pom = f"""<project {NS}>
      <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.2.5</version></parent>
      <groupId>com.acme</groupId><artifactId>svc</artifactId><version>1</version>
      <dependencyManagement><dependencies>
        <dependency><groupId>com.example</groupId><artifactId>acme-bom</artifactId><version>9</version><type>pom</type><scope>import</scope></dependency>
      </dependencies></dependencyManagement>
      <dependencies>
        <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
        <dependency><groupId>com.example</groupId><artifactId>from-bom</artifactId></dependency>
        <dependency><groupId>x</groupId><artifactId>y</artifactId><version>${{env.SECRET}}</version></dependency>
      </dependencies></project>"""
    root, _ = make_snapshot(tmp_path, {"pom.xml": pom})
    model, _, _ = load_pom_tree(SnapshotFS(root), "pom.xml")
    codes = {d["code"] for d in model.diagnostics}
    assert {"EXTERNAL_PARENT", "EXTERNAL_BOM", "UNSUPPORTED_INTERPOLATION"} <= codes and model.status == "PARTIAL"
    for d in model.dependencies:
        assert d.version is None and d.version_source == "unresolved", d                             # versions are left unresolved, not guessed
    assert any("external parent may manage it" in (d.note or "") for d in model.dependencies)


def test_in_repo_parent_that_is_not_the_declared_parent_is_not_trusted(tmp_path):
    other = ROOT.replace("acme-parent", "something-else")
    root, _ = make_snapshot(tmp_path, {"pom.xml": other, "core/pom.xml": CORE})
    model, _, _ = load_pom_tree(SnapshotFS(root), "core/pom.xml")
    assert any(d["code"] == "PARENT_MISMATCH" for d in model.diagnostics) and not model.parent["found_in_repository"]
    assert model.dependencies[0].version is None


def test_parent_path_escape_and_property_cycles_do_not_loop_or_escape(tmp_path):
    esc = f'<project {NS}><parent><groupId>g</groupId><artifactId>a</artifactId><version>1</version><relativePath>../../etc/pom.xml</relativePath></parent><artifactId>x</artifactId></project>'
    cyc = f'<project {NS}><groupId>g</groupId><artifactId>c</artifactId><version>1</version><properties><a>${{b}}</a><b>${{a}}</b></properties><dependencies><dependency><groupId>g</groupId><artifactId>d</artifactId><version>${{a}}</version></dependency></dependencies></project>'
    root, _ = make_snapshot(tmp_path, {"sub/pom.xml": esc, "cyc/pom.xml": cyc})
    fs = SnapshotFS(root)
    m, _, _ = load_pom_tree(fs, "sub/pom.xml")
    assert any(d["code"] == "PATH_ESCAPE" for d in m.diagnostics)
    c, _, _ = load_pom_tree(fs, "cyc/pom.xml")
    assert c.dependencies[0].version is None and any(d["code"] in ("INTERPOLATION_TOO_DEEP", "UNRESOLVED_PROPERTY") for d in c.diagnostics)


# ----------------------------------------------------------------------------- hostile XML

def listener():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    hits = []

    def accept():
        srv.settimeout(3)
        try:
            while True:
                c, _ = srv.accept()
                hits.append(1)
                c.close()
        except (TimeoutError, OSError):
            pass

    t = threading.Thread(target=accept, daemon=True)
    t.start()
    return srv, hits, t


def test_tc_3_7_3_hostile_xml_is_rejected_without_reading_files_or_touching_the_network(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CANARY-VALUE")
    srv, hits, t = listener()
    port = srv.getsockname()[1]
    bomb = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
            '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]><project><artifactId>&lol3;</artifactId></project>')
    xxe_file = f'<?xml version="1.0"?><!DOCTYPE p [<!ENTITY xxe SYSTEM "{secret.as_uri()}">]><project><artifactId>&xxe;</artifactId></project>'
    xxe_net = f'<?xml version="1.0"?><!DOCTYPE p [<!ENTITY xxe SYSTEM "http://127.0.0.1:{port}/x">]><project><artifactId>&xxe;</artifactId></project>'
    ext_dtd = f'<?xml version="1.0"?><!DOCTYPE project SYSTEM "http://127.0.0.1:{port}/evil.dtd"><project><artifactId>a</artifactId></project>'
    param = '<?xml version="1.0"?><!DOCTYPE p [<!ENTITY % e SYSTEM "http://127.0.0.1:1/x"> %e;]><project/>'
    root, _ = make_snapshot(tmp_path / "s", {"bomb.xml": bomb, "xxe_file.xml": xxe_file, "xxe_net.xml": xxe_net, "ext_dtd.xml": ext_dtd,
                                             "param.xml": param, "notpom.xml": "<html/>", "broken.xml": "<project><a></project>"})
    fs = SnapshotFS(root)
    for name in ("bomb", "xxe_file", "xxe_net", "ext_dtd", "param"):
        model, parsed = read_pom(fs, f"{name}.xml")
        assert parsed is None and model.status == "FAILED" and "refused" in model.error, name
        assert "TOP-SECRET-CANARY-VALUE" not in repr(model)
    for name in ("notpom", "broken"):
        assert read_pom(fs, f"{name}.xml")[0].status == "FAILED"
    t.join(timeout=5)
    srv.close()
    assert hits == []                                                                              # no connection was ever made


def test_deeply_nested_and_oversized_poms_are_rejected_not_crashed(tmp_path):
    deep = f'<project {NS}>' + "<a>" * 6000 + "</a>" * 6000 + "</project>"
    root, _ = make_snapshot(tmp_path, {"deep.xml": deep, "big.xml": f"<project {NS}>" + "<x>1</x>" * 3_000_000 + "</project>"})
    fs = SnapshotFS(root)
    for name in ("deep.xml", "big.xml"):
        m, parsed = read_pom(fs, name)
        assert parsed is None and m.status in ("FAILED", "TOO_LARGE")


def test_tc_3_7_4_no_maven_or_any_process_is_started(tmp_path, monkeypatch):
    started = []

    def forbid(*a, **k):
        started.append(a)
        raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "Popen", forbid)
    monkeypatch.setattr("os.system", forbid)
    ps = projects(tmp_path, {"pom.xml": ROOT, "core/pom.xml": CORE, "api/pom.xml": API, ".mvn/wrapper/maven-wrapper.properties": "x=1"})
    assert len(ps) == 3 and started == []
    src = "\n".join(p.read_text(encoding="utf-8") for p in Path(__file__).resolve().parents[2].joinpath("backend/faultline/parsers/maven").glob("*.py"))
    assert not re.search(r"\bsubprocess\b|os\.system|os\.popen|\bmvn\b|\bmvnw\b", src.replace("Maven is never run", ""))   # no code path can start Maven


@pytest.mark.parametrize("bad", ["", "   ", "\x00", "<project"])
def test_odd_poms_do_not_crash(tmp_path, bad):
    root, _ = make_snapshot(tmp_path, {"pom.xml": bad})
    m, parsed = read_pom(SnapshotFS(root), "pom.xml")
    assert parsed is None and m.status == "FAILED"
