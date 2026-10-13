"""Container security profiles. Changing a flag here changes the security boundary: add a test in tests/security."""
from dataclasses import dataclass

# Hard ceilings. A job may ask for less, never more.
MAX_LIMITS = {"cpus": 2.0, "memory_mb": 2048, "pids": 512, "timeout_s": 900, "tmpfs_mb": 1024, "output_bytes": 262_144}
DEFAULT_LIMITS = {"cpus": 1.0, "memory_mb": 1024, "pids": 256, "timeout_s": 60, "tmpfs_mb": 256, "output_bytes": 65_536}

ALLOWED_ENV = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC", "PYTHONHASHSEED": "0",
               "SOURCE_DATE_EPOCH": "1700000000", "PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp"}


def clamp_limits(requested: dict | None) -> dict:
    out = dict(DEFAULT_LIMITS)
    for k, v in (requested or {}).items():
        if k not in MAX_LIMITS:
            raise ValueError(f"unknown limit {k!r}")
        if not isinstance(v, (int, float)) or v <= 0:
            raise ValueError(f"limit {k} must be a positive number")
        out[k] = min(v, MAX_LIMITS[k])
    return out


FETCH_NETWORK = "faultline-fetch"          # an internal Docker network: no route to the outside except through the egress proxy
EGRESS_HOST = "faultline-egress"
EGRESS_PORT = 3128
PROXY_ENV = {k: f"http://{EGRESS_HOST}:{EGRESS_PORT}" for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")}


@dataclass(frozen=True)
class Profile:
    name: str
    network: str                 # "none" or the internal fetch network
    extra_env: tuple = ()        # fixed (name, value) pairs; never taken from a request

    def docker_args(self, limits: dict, container_name: str, job_id: str, group: str | None = None) -> list[str]:
        mem = f"{int(limits['memory_mb'])}m"
        args = [
            "--name", container_name,
            "--label", "faultline=1", "--label", f"faultline.job={job_id}", "--label", f"faultline.zone={self.name}",
            *(["--label", f"faultline.group={group}"] if group else []),
            "--network", self.network,
            "--read-only",
            "--tmpfs", f"/tmp:rw,noexec,nosuid,mode=1777,size={int(limits['tmpfs_mb'])}m",
            "--tmpfs", f"/work:rw,noexec,nosuid,mode=1777,size={int(limits['tmpfs_mb'])}m",
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--pids-limit", str(int(limits["pids"])),
            "--memory", mem, "--memory-swap", mem,
            "--cpus", str(limits["cpus"]),
            "--ulimit", "nofile=1024:1024",
            "--ulimit", "fsize=104857600",
            "--stop-timeout", "1",
            "-i",
        ]
        for k, v in {**ALLOWED_ENV, **dict(self.extra_env)}.items():
            args += ["-e", f"{k}={v}"]
        return args


# The execution zone never has a network. The fetch zone (downloads wheels, clones repositories) can reach only the egress proxy, which allows GitHub and PyPI over HTTPS.
EXEC = Profile("exec", "none")
FETCH = Profile("fetch", FETCH_NETWORK, tuple(sorted(PROXY_ENV.items())))
PROFILES = {"exec": EXEC, "fetch": FETCH}
