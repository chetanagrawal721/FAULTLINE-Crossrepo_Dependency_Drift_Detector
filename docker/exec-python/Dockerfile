# Execution and fetch image (milestone M1.2). The base image is pinned by digest (checked by scripts/check_pins.py).
# Contains Python, uv and the Faultline harness only. No secrets, no repository code.
FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_NO_CACHE=1 \
    HOME=/tmp

# git is needed by the fetch zone only (hardened by flags in fetch_repo.py); the exec zone has no network and never runs it
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv==0.13.0

# Mount points for named volumes. Docker copies this ownership into a new empty volume, so the
# unprivileged user (65534) can write the world and wheelhouse volumes without any root step at run time.
RUN mkdir -p /opt/world /wheelhouse && chown 65534:65534 /opt/world /wheelhouse

COPY backend/faultline/oracles/harness/ /faultline_harness/
WORKDIR /work
# Always run as a non-root user chosen at run time (--user 65534:65534); nothing here assumes root.
