"""sandboxd: the only process that talks to Docker.

    python -m faultline.sandbox.sandboxd [--host 127.0.0.1] [--port 8787]

Transport: newline-delimited JSON over loopback TCP (Unix sockets are not available on Windows). Every request
carries a shared token kept in var/sandboxd.token (or FAULTLINE_SANDBOX_TOKEN). The server only listens on loopback.
Requests: ping, status, run, sweep. `run` accepts structured jobs only; see runner.run_job.
"""
import argparse
import hmac
import json
import logging
import os
import re
import secrets
import socketserver
import threading
import time
from pathlib import Path

from ..core.config import Settings, repo_root
from ..core.logging import configure as configure_logging
from ..storage.store import Store
from . import egress, images, profiles, runner

log = logging.getLogger("faultline.sandboxd")
MAX_CONCURRENT = int(os.environ.get("FAULTLINE_SANDBOX_CONCURRENCY", "4"))
MAX_REQUEST_BYTES = 1_000_000
WHEELHOUSE_VOLUME = "fl-wheelhouse"


def world_volume(world_hash: str) -> str:
    if not re.fullmatch(r"w_[0-9a-f]{20,64}", world_hash):
        raise ValueError(f"invalid world hash {world_hash!r}")
    return f"fl-world-{world_hash}"


def token_path() -> Path:
    return repo_root() / "var" / "sandboxd.token"


def load_token(create: bool = False) -> str | None:
    env = os.environ.get("FAULTLINE_SANDBOX_TOKEN")
    if env:
        return env
    p = token_path()
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    if create:
        p.parent.mkdir(parents=True, exist_ok=True)
        t = secrets.token_hex(24)
        p.write_text(t, encoding="utf-8")
        return t
    return None


class Daemon:
    def __init__(self, token: str, docker_host: str | None = None, store: Store | None = None,
                 lock_path: Path | None = None):
        self.token, self.docker_host, self.lock_path = token, docker_host, lock_path
        self.store = store or Store(Settings.from_env().store_path)
        self.slots = threading.Semaphore(MAX_CONCURRENT)
        self.boundary: dict = {"verified": False, "reason": "not checked yet", "checks": [], "at": None}
        self.lock = threading.Lock()

    # -- mounts come from a fixed table keyed by hash, never from request paths.
    # Worlds and the wheelhouse live in named Docker volumes (bind mounts from Windows cannot hold symlinks).
    # A volume is mounted read-write only for the one job kind that must write it.
    def mounts(self, spec: dict, job: dict) -> list[dict]:
        out: list[dict] = []
        script, zone = job.get("script", "probe.py"), job.get("zone", "exec")
        for target, ref in (spec or {}).items():
            if target == "/opt/world":
                rw = bool(ref.get("rw"))
                if rw and script != "build_world.py":
                    raise ValueError("/opt/world is writable only for world builds")
                out.append({"type": "volume", "source": world_volume(ref["world"]), "target": target, "readonly": not rw})
            elif target == "/wheelhouse":
                rw = bool(ref.get("rw"))
                if rw and not (zone == "fetch" and script == "fetch_wheels.py"):
                    raise ValueError("/wheelhouse is writable only for wheel downloads in the fetch zone")
                out.append({"type": "volume", "source": WHEELHOUSE_VOLUME, "target": target, "readonly": not rw})
            elif target == "/snapshot":
                if not (zone == "fetch" and script == "fetch_repo.py"):
                    raise ValueError("/snapshot is writable only for repository fetches in the fetch zone")
                dest = self.store.snapshot_dir(ref["snapshot"])
                dest.mkdir(parents=True, exist_ok=True)
                try:
                    os.chmod(dest, 0o777)              # the container runs as an unprivileged user and must be able to write here (Linux hosts enforce modes)
                except OSError:
                    pass
                out.append({"type": "bind", "source": dest, "target": target, "readonly": False})
            elif target == "/source":
                if not (zone == "fetch" and script in ("fetch_repo.py", "resolve_uv.py")):
                    raise ValueError("/source is for repository fetches and local test indexes only")
                src = self.store.remote_dir(ref["remote"])
                if not src.exists():
                    raise ValueError("local remote does not exist")
                out.append({"type": "bind", "source": src, "target": target, "readonly": True})
            elif target == "/artifact":
                src = self.store.artifact_dir(ref["artifact"])
                if not src.exists():
                    raise ValueError("artifact is not in the store")
                out.append({"type": "bind", "source": src, "target": target, "readonly": True})
            else:
                raise ValueError(f"mount target {target!r} is not allowed")
        return out

    def run(self, job: dict) -> dict:
        try:
            mounts = self.mounts(job.get("mounts", {}), job)
        except (ValueError, KeyError) as exc:
            return {"failure_class": "SANDBOX_FAILURE", "error": f"rejected: {exc}", "data": None}
        if job.get("zone") == "fetch":                                    # fail closed: no fetch without the egress allowlist in place
            try:
                allowed = images.require_allowed(job["image"], self.lock_path)
            except (KeyError, ValueError) as exc:
                return {"failure_class": "SANDBOX_FAILURE", "error": f"rejected: {exc}", "data": None}
            ok, reason = egress.ensure(allowed, self.docker_host)
            if not ok:
                return {"failure_class": "SANDBOX_FAILURE", "error": f"fetch zone disabled: {reason}", "data": None}
        with self.slots:
            return runner.run_job(job, mounts=mounts, docker_host=self.docker_host, lock_path=self.lock_path)

    def volume_exists(self, name: str) -> bool:
        return runner.volume_exists(name, self.docker_host)

    def verify_boundary(self) -> dict:
        """Run fixed probes against the real container profile and record what the boundary actually enforces."""
        checks: list[dict] = []
        try:
            image = images.default_image(path=self.lock_path)
        except ValueError as exc:
            res = {"verified": False, "reason": str(exc), "checks": [], "at": time.time()}
            with self.lock:
                self.boundary = res
            return res

        def probe(name: str, args: dict | None = None) -> dict | None:
            r = self.run({"image": image, "probe": name, "args": args or {}, "limits": {"timeout_s": 30}})
            return (r.get("data") or {}).get("data")

        def check(name: str, ok: bool, detail) -> None:
            checks.append({"check": name, "ok": bool(ok), "detail": detail})

        ident = probe("identity") or {}
        check("non-root user", ident.get("uid") not in (None, 0) and ident.get("euid") not in (None, 0), ident.get("uid"))
        check("no capabilities", ident.get("cap_eff") == "0000000000000000", ident.get("cap_eff"))
        check("no-new-privileges", ident.get("no_new_privs") == "1", ident.get("no_new_privs"))
        check("seccomp filter active", ident.get("seccomp") == "2", ident.get("seccomp"))
        check("root filesystem read-only", ident.get("root_read_only") is True, ident.get("root_read_only"))
        check("docker socket absent", ident.get("docker_sock_exists") is False, ident.get("docker_sock_exists"))
        net = probe("network") or {}
        check("no network", net.get("connected") is False and net.get("dns") is False, net)
        w = probe("write", {"path": "/etc/faultline_probe"}) or {}
        check("cannot write to /etc", w.get("written") is False, w)
        # the fetch zone: reachable only through the allowlisting proxy (SR-4)
        ok_net, why = egress.ensure(image, self.docker_host)
        check("egress proxy running", ok_net, why)
        check("fetch network is internal", egress.network_internal(self.docker_host) is True, profiles.FETCH_NETWORK)
        eg = {}
        if ok_net:
            r = self.run({"image": image, "zone": "fetch", "probe": "egress", "limits": {"timeout_s": 60},
                          "args": {"targets": ["169.254.169.254:80", "169.254.169.254:443", "127.0.0.1:443", "10.0.0.1:443", "example.com:443",
                                               "github.com:22", "github.com:443"],
                                   "direct": [["1.1.1.1", 443], ["169.254.169.254", 80], ["8.8.8.8", 53]]}})
            eg = (r.get("data") or {}).get("data") or {}
        conn = eg.get("connect", {})
        check("direct egress from the fetch zone is blocked", bool(eg) and not any((eg.get("direct") or {"x": True}).values()), eg.get("direct"))
        check("proxy refuses cloud metadata, loopback and private targets",
              all(conn.get(t) == "403" for t in ("169.254.169.254:80", "169.254.169.254:443", "127.0.0.1:443", "10.0.0.1:443")), conn)
        check("proxy refuses hosts that are not allowlisted and other ports", conn.get("example.com:443") == "403" and conn.get("github.com:22") == "403", conn)
        ok = all(c["ok"] for c in checks) and len(checks) >= 8
        res = {"verified": ok, "reason": "all boundary checks passed" if ok else
               "failed: " + ", ".join(c["check"] for c in checks if not c["ok"]) or "no result", "checks": checks,
               "at": time.time(), "image": image}
        with self.lock:
            self.boundary = res
        return res

    def status(self) -> dict:
        up = runner.docker_ok(self.docker_host)
        with self.lock:
            b = dict(self.boundary)
        return {"docker": up, "boundary": b, "concurrency": MAX_CONCURRENT}


class Handler(socketserver.StreamRequestHandler):
    server: "Server"

    def handle(self) -> None:
        line = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if not line or len(line) > MAX_REQUEST_BYTES:
            return
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            return self._send({"error": "bad json"})
        if not hmac.compare_digest(str(req.get("token", "")), self.server.daemon.token):
            return self._send({"error": "unauthorized"})
        cmd, d = req.get("cmd"), self.server.daemon
        try:
            if cmd == "ping":
                self._send({"ok": True})
            elif cmd == "status":
                self._send(d.status())
            elif cmd == "run":
                self._send(d.run(req["job"]))
            elif cmd == "verify":
                self._send(d.verify_boundary())
            elif cmd == "volume_exists":
                self._send({"exists": d.volume_exists(world_volume(req["world"]) if "world" in req else WHEELHOUSE_VOLUME)})
            elif cmd == "volume_rm":
                self._send({"removed": runner.volume_rm(world_volume(req["world"]), d.docker_host)})
            elif cmd == "cancel":
                self._send({"killed": runner.kill_group(str(req["group"]), d.docker_host)})
            elif cmd == "groups":
                self._send({"groups": runner.running_groups(d.docker_host)})
            elif cmd == "sweep":
                self._send({"removed": runner.sweep_orphans(d.docker_host)})
            else:
                self._send({"error": f"unknown command {cmd!r}"})
        except Exception as exc:  # noqa: BLE001
            log.exception("request failed")
            self._send({"error": f"{type(exc).__name__}: {exc}"})

    def _send(self, obj: dict) -> None:
        self.wfile.write((json.dumps(obj) + "\n").encode())


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, daemon: Daemon):
        super().__init__(addr, Handler)
        self.daemon = daemon


def serve(host: str, port: int, daemon: Daemon) -> Server:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("sandboxd only listens on loopback")
    return Server((host, port), daemon)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("FAULTLINE_SANDBOX_PORT", "8787")))
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()
    configure_logging()
    daemon = Daemon(load_token(create=True) or "", docker_host=os.environ.get("FAULTLINE_DOCKER_HOST"))
    if runner.docker_ok(daemon.docker_host):
        removed = runner.sweep_orphans(daemon.docker_host)
        if removed:
            log.info("removed %d orphaned containers from a previous run", len(removed))
        if not a.no_verify:
            res = daemon.verify_boundary()
            log.info("boundary verification: verified=%s (%s)", res["verified"], res["reason"])
    else:
        log.warning("docker is not reachable: execution is disabled until it is")
    srv = serve(a.host, a.port, daemon)
    log.info("sandboxd listening on %s:%d", a.host, a.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
