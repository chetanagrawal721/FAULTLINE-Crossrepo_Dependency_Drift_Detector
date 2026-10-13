"""Code that runs INSIDE the sandbox container. Keep it dependency-free (standard library only).

Protocol: the control plane writes one JSON document to stdin. The harness prints exactly one result frame to
stdout, delimited by marker lines, so any other output (library noise, tracebacks) cannot be mistaken for a result.
"""
import json
import os
import sys

BEGIN = "@@FAULTLINE_RESULT_BEGIN@@"
END = "@@FAULTLINE_RESULT_END@@"


def read_spec() -> dict:
    return json.loads(sys.stdin.read() or "{}")


PROXY_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")


def proxy_env() -> dict:
    """The egress proxy variables the sandbox profile set for this container (fetch zone), to pass on to a subprocess that builds its own environment."""
    return {k: os.environ[k] for k in PROXY_VARS if os.environ.get(k)}


def emit(result: dict) -> None:
    sys.stdout.write(f"\n{BEGIN}\n{json.dumps(result, sort_keys=True)}\n{END}\n")
    sys.stdout.flush()
