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

# The runtime status endpoint, served by the gateway beside /health.
RUNTIME_STATUS_PATH = "/runtime/status"

# Environment seam: absolute path of the nexus.toml the runtime was started
# from. The supervisor sets it on every spawned service so the gateway's
# /runtime/status reports the profile/ports of the config that actually
# launched it (test harnesses point this at temp configs).
RUNTIME_CONFIG_ENV = "NEXUS_RUNTIME_CONFIG"
