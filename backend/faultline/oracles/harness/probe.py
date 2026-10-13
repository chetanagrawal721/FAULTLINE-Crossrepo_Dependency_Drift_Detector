"""Sandbox probes: fixed, structured experiments that show what the container boundary really allows.

Only the probes listed in PROBES exist; the spec cannot ask for arbitrary code. Every probe reports data and
never decides pass or fail: the control plane (and the tests) judge the result.
"""
import os
import socket
import sys
import time

from common import emit, read_spec


def _status_field(name: str) -> str | None:
    try:
        for line in open("/proc/self/status", encoding="utf-8"):
            if line.startswith(name + ":"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def probe_identity(_: dict) -> dict:
    mounts = {}
    try:
        for line in open("/proc/mounts", encoding="utf-8"):
            dev, target, fstype, opts = line.split()[:4]
            mounts[target] = {"fstype": fstype, "read_only": "ro" in opts.split(","), "noexec": "noexec" in opts.split(",")}
    except OSError:
        pass
    return {
        "uid": os.getuid(), "gid": os.getgid(), "euid": os.geteuid(), "cwd": os.getcwd(),
        "env_names": sorted(os.environ), "cap_eff": _status_field("CapEff"), "no_new_privs": _status_field("NoNewPrivs"),
        "seccomp": _status_field("Seccomp"), "root_read_only": mounts.get("/", {}).get("read_only"),
        "mounts": {k: v for k, v in mounts.items() if k in ("/", "/tmp", "/work", "/opt/world", "/artifact", "/wheelhouse")},
        "docker_sock_exists": os.path.exists("/var/run/docker.sock") or os.path.exists("/run/docker.sock"),
        "python": sys.version.split()[0],
    }


def probe_network(a: dict) -> dict:
    host, port = a.get("host", "1.1.1.1"), int(a.get("port", 443))
    out = {"host": host, "port": port}
    try:
        socket.create_connection((host, port), timeout=float(a.get("timeout", 2))).close()
        out["connected"] = True
    except OSError as exc:
        out["connected"] = False
        out["error"] = type(exc).__name__
    try:
        socket.getaddrinfo(a.get("dns", "pypi.org"), 443)
        out["dns"] = True
    except OSError as exc:
        out["dns"] = False
        out["dns_error"] = type(exc).__name__
    return out


def probe_egress(a: dict) -> dict:
    """From a fetch-zone container: what the egress proxy allows and what a direct connection can reach. Reports data only."""
    proxy = (a.get("proxy_host", "faultline-egress"), int(a.get("proxy_port", 3128)))
    out: dict = {"proxy": f"{proxy[0]}:{proxy[1]}", "env_proxy": os.environ.get("HTTPS_PROXY"), "connect": {}}
    for target in a.get("targets", []):
        try:
            with socket.create_connection(proxy, timeout=10) as s:
                s.settimeout(15)
                s.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode("ascii"))
                head = s.recv(256).split(b"\r\n", 1)[0].decode("latin-1")
                out["connect"][target] = head.split(" ", 2)[1] if head.startswith("HTTP/") and len(head.split(" ", 2)) > 1 else head
        except OSError as exc:
            out["connect"][target] = f"error:{type(exc).__name__}"
    direct = {}
    for host, port in a.get("direct", []):
        try:
            socket.create_connection((host, int(port)), timeout=3).close()
            direct[f"{host}:{port}"] = True
        except OSError:
            direct[f"{host}:{port}"] = False
    out["direct"] = direct
    return out


def probe_write(a: dict) -> dict:
    path = a["path"]
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("x")
        os.unlink(path)
        return {"path": path, "written": True}
    except OSError as exc:
        return {"path": path, "written": False, "error": type(exc).__name__}


def probe_read(a: dict) -> dict:
    path = a["path"]
    try:
        with open(path, "rb") as f:
            return {"path": path, "readable": True, "bytes": len(f.read(4096))}
    except OSError as exc:
        return {"path": path, "readable": False, "error": type(exc).__name__}


def probe_fork_bomb(a: dict) -> dict:
    limit = int(a.get("max", 5000))
    children: list[int] = []
    error = None
    try:
        for _ in range(limit):
            pid = os.fork()
            if pid == 0:
                time.sleep(30)
                os._exit(0)
            children.append(pid)
    except OSError as exc:
        error = type(exc).__name__
    count = len(children)
    for pid in children:
        try:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        except OSError:
            pass
    return {"forked": count, "stopped_by": error, "reached_limit": count >= limit}


def probe_memory(a: dict) -> dict:
    target_mb, chunks = int(a.get("mb", 4096)), []
    try:
        for _ in range(target_mb // 50):
            chunks.append(bytearray(b"\xff") * (50 * 1024 * 1024))     # non-zero fill so pages are really used
        return {"allocated_mb": len(chunks) * 50, "completed": True}
    except MemoryError:
        return {"allocated_mb": len(chunks) * 50, "completed": False, "error": "MemoryError"}


def probe_disk(a: dict) -> dict:
    written, block = 0, b"\0" * (1024 * 1024)
    try:
        with open(a.get("path", "/tmp/fill"), "wb") as f:
            for _ in range(int(a.get("mb", 2048))):
                f.write(block)
                f.flush()
                written += 1
        return {"written_mb": written, "completed": True}
    except OSError as exc:
        return {"written_mb": written, "completed": False, "error": type(exc).__name__}


def probe_print_flood(a: dict) -> dict:
    line = "x" * 1023 + "\n"
    for _ in range(int(a.get("mb", 200)) * 1024):
        sys.stdout.write(line)
    return {"printed_mb": int(a.get("mb", 200))}


def probe_sleep(a: dict) -> dict:
    time.sleep(float(a.get("seconds", 1)))
    return {"slept": float(a.get("seconds", 1))}


def probe_busy(a: dict) -> dict:
    end = time.monotonic() + float(a.get("seconds", 5))
    n = 0
    while time.monotonic() < end:
        n += 1
    return {"iterations": n}


def probe_echo(a: dict) -> dict:
    return {"echo": a}


PROBES = {
    "identity": probe_identity, "network": probe_network, "write": probe_write, "read": probe_read,
    "fork_bomb": probe_fork_bomb, "memory": probe_memory, "disk": probe_disk, "print_flood": probe_print_flood,
    "sleep": probe_sleep, "busy": probe_busy, "echo": probe_echo, "egress": probe_egress,
}


def main() -> None:
    spec = read_spec()
    name = spec.get("probe")
    if name not in PROBES:
        emit({"error": f"unknown probe {name!r}", "known": sorted(PROBES)})
        sys.exit(2)
    emit({"probe": name, "data": PROBES[name](spec.get("args", {}))})


if __name__ == "__main__":
    main()
