"""Runtime contract constants shared by the gateway, supervisor, and clients.

These values are part of the client/runtime boundary documented in
docs/runtime.md. Clients (PWA, CLI, future desktop shells or hosted clients)
should import or mirror these rather than hardcoding strings.
"""

from __future__ import annotations

# Reserved auth header for every client -> runtime request. Semantics:
# an opaque bearer credential issued by the runtime operator. The local
# profile ignores it entirely (no-op), but clients must send it from day one
# so that pointing the same client at a remote runtime is a base-URL change,
# not a code change. Hosted runtimes reject requests without it.
NEXUS_AUTH_HEADER = "X-Nexus-Auth"

# Cloudflare Access service-token headers. These are edge credentials, not
# application authentication: clients add them only for a configured remote
# origin, and the gateway remains unaware of their values.
CF_ACCESS_CLIENT_ID_HEADER = "CF-Access-Client-Id"
CF_ACCESS_CLIENT_SECRET_HEADER = "CF-Access-Client-Secret"

# The runtime status endpoint, served by the gateway beside /health.
RUNTIME_STATUS_PATH = "/runtime/status"

# Environment seam: absolute path of the nexus.toml the runtime was started
# from. The supervisor sets it on every spawned service so the gateway's
# /runtime/status reports the profile/ports of the config that actually
# launched it (test harnesses point this at temp configs).
RUNTIME_CONFIG_ENV = "NEXUS_RUNTIME_CONFIG"

# Environment seam: run the gateway on an alternate port with isolated
# runtime state (pidfiles/logs under a per-port subdirectory). This is the
# designated lane for agent and test sessions, so a live-testing gateway can
# never squat the desktop app's configured port — the collision that
# motivated it was an orphaned test gateway from a dead session holding
# :8002. The desktop shell never sets this; interactive test shells export
# it before `nexus up`.
GATEWAY_PORT_ENV = "NEXUS_GATEWAY_PORT"


def gateway_port_override() -> "int | None":
    """Parse the gateway port override from the environment.

    Returns None when unset; raises ValueError loudly on garbage so a typo
    can never silently fall back to the configured port.
    """
    import os

    raw = os.environ.get(GATEWAY_PORT_ENV)
    if raw is None or raw.strip() == "":
        return None
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{GATEWAY_PORT_ENV} must be an integer port, got {raw!r}"
        ) from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{GATEWAY_PORT_ENV} must be 1-65535, got {port}")
    return port
