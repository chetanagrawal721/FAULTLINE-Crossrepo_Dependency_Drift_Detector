"""Egress proxy for the fetch zone (SR-4). Runs in its own hardened container; fetch containers have no route except through it.

Only HTTPS tunnels (CONNECT host:443) to an allowlist of hostnames are permitted. Everything else is refused with 403:
plain HTTP, other ports, IP literals, unlisted names, and any name that resolves to a private, loopback, link-local (cloud
metadata), multicast or otherwise non-public address. The address that was checked is the address that is connected to, so a
DNS answer cannot change between the check and the use.

`decide` is a pure function so the policy is unit-tested without a network.
"""
import ipaddress
import json
import select
import socket
import socketserver
import sys
import threading
import time

ALLOWED_HOSTS = (
    "github.com", "api.github.com", "codeload.github.com", "objects.githubusercontent.com", "raw.githubusercontent.com",
    "pypi.org", "files.pythonhosted.org",
)
ALLOWED_PORTS = (443,)
MAX_TUNNELS = 64
IDLE_SECONDS = 120
MAX_TUNNEL_SECONDS = 900
LISTEN = ("0.0.0.0", 3128)
_slots = threading.Semaphore(MAX_TUNNELS)


def is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_global and not (ip.is_multicast or ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_unspecified)


def decide(host: str, port: int, resolve=None) -> tuple[bool, str, list[str]]:
    """(allowed, reason, addresses to connect to, all of them verified public). `resolve(host) -> list[str]` defaults to the system resolver."""
    host = host.strip().lower().rstrip(".")
    if port not in ALLOWED_PORTS:
        return False, f"port {port} is not allowed", []
    try:
        ipaddress.ip_address(host.strip("[]"))
        return False, "IP literals are not allowed", []
    except ValueError:
        pass
    if host not in ALLOWED_HOSTS:
        return False, f"{host} is not on the allowlist", []
    try:
        addresses = (resolve or _resolve)(host)
    except OSError as exc:
        return False, f"could not resolve {host}: {type(exc).__name__}", []
    if not addresses:
        return False, f"{host} did not resolve", []
    bad = [a for a in addresses if not is_public(a)]
    if bad:
        return False, f"{host} resolves to a non-public address ({bad[0]})", []
    return True, "allowed", addresses


def _resolve(host: str) -> list[str]:
    found = {info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    return sorted(found, key=lambda a: (":" in a, a))          # IPv4 first, then IPv6


def _log(event: dict) -> None:
    print(json.dumps({"t": round(time.time(), 3), **event}, sort_keys=True), file=sys.stderr, flush=True)


class Handler(socketserver.StreamRequestHandler):
    timeout = 20

    def _reply(self, code: int, text: str) -> None:
        self.wfile.write(f"HTTP/1.1 {code} {text}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n".encode("ascii", "replace"))
        self.wfile.flush()

    def handle(self) -> None:
        line = self.rfile.readline(2048).decode("latin-1").strip()
        parts = line.split()
        while True:                                                   # discard the request headers
            h = self.rfile.readline(2048)
            if h in (b"\r\n", b"\n", b""):
                break
        if len(parts) != 3 or parts[0].upper() != "CONNECT":
            _log({"decision": "deny", "reason": "only CONNECT is supported", "request": line[:80]})
            return self._reply(403, "Forbidden")
        target = parts[1]
        host, _, port_text = target.rpartition(":")
        try:
            port = int(port_text)
        except ValueError:
            _log({"decision": "deny", "reason": "bad target", "target": target[:80]})
            return self._reply(400, "Bad Request")
        allowed, reason, addresses = decide(host.strip("[]"), port)
        _log({"decision": "allow" if allowed else "deny", "host": host[:100], "port": port, "reason": reason})
        if not allowed:
            return self._reply(403, "Forbidden")
        if not _slots.acquire(blocking=False):
            return self._reply(503, "Busy")
        try:
            upstream = None
            for address in addresses:                                  # every address was verified public; use the first that answers
                try:
                    upstream = socket.create_connection((address, port), timeout=6)
                    break
                except OSError:
                    continue
            if upstream is None:
                return self._reply(502, "Bad Gateway")
            self._reply_connected()
            self._pump(self.connection, upstream)
        finally:
            _slots.release()

    def _reply_connected(self) -> None:
        self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        self.wfile.flush()

    @staticmethod
    def _pump(a: socket.socket, b: socket.socket) -> None:
        deadline = time.monotonic() + MAX_TUNNEL_SECONDS
        socks = [a, b]
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select(socks, [], [], IDLE_SECONDS)
                if not ready:
                    return                                            # idle too long
                for s in ready:
                    data = s.recv(65536)
                    if not data:
                        return
                    (b if s is a else a).sendall(data)
        except OSError:
            return
        finally:
            b.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    _log({"event": "start", "allowlist": list(ALLOWED_HOSTS), "ports": list(ALLOWED_PORTS)})
    with Server(LISTEN, Handler) as srv:
        srv.serve_forever()


if __name__ == "__main__":
    main()
