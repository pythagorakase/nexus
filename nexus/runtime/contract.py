"""Runtime contract constants shared by the gateway, supervisor, and clients.

These values are part of the client/runtime boundary documented in
docs/runtime.md. Clients (PWA, CLI, future desktop shells or hosted clients)
should import or mirror these rather than hardcoding strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nexus.config.settings_models import RuntimeSettings

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

# Environment seam: absolute path of the runtime home (issue #820). When set,
# $NEXUS_HOME/nexus.toml is the active configuration and relative runtime
# directories resolve under it; NEXUS_RUNTIME_CONFIG, when also set, must name
# that same file. Unset, the checkout is the home. nexus/runtime/home.py owns
# the rule.
HOME_ENV = "NEXUS_HOME"

# Per-user failure-receipt root (issue #806, decision 806-Q12), resolved under
# Path.home(). A receipt goes here when no runtime home can be located (a
# RuntimeHomeError), because its home receipt directory is then unknown.
FALLBACK_RECEIPTS_DIR = PurePath(".nexus", "receipts")

# Test seam for failure receipts (issue #806). tests/conftest.py sets it for
# the whole session, and child processes inherit it. When set and non-empty,
# home receipts go to $NEXUS_TEST_RECEIPTS_DIR/home and fallback receipts to
# $NEXUS_TEST_RECEIPTS_DIR/fallback; the runtime-home locator still runs, so
# routing is unchanged. It must be an absolute path. It is not an owner
# setting.
TEST_RECEIPTS_ENV = "NEXUS_TEST_RECEIPTS_DIR"

# The gateway serves two listeners from one process (issue #824): the player
# projection on [runtime.services.gateway].port, the address the Cloudflare
# tunnel reaches, and the operator projection (the whole runtime) on
# [runtime.gateway].operator_port. The operator plane never binds a
# non-loopback interface, so its host is this constant, not a tunable.
OPERATOR_HOST = "127.0.0.1"

# Environment seam: run the gateway's operator listener on an alternate port
# with isolated runtime state (pidfiles/logs under a per-port subdirectory).
# This is the designated lane for agent and test sessions, so a live-testing
# gateway can never squat the desktop app's configured ports — the collision
# that motivated it was an orphaned test gateway from a dead session holding
# :8002. A lane that sets only this variable gets one listener serving the
# whole runtime and never binds the player port; NEXUS_PLAYER_PORT adds the
# lane's player listener. The desktop shell never sets either; interactive
# test shells export them before `nexus up`.
GATEWAY_PORT_ENV = "NEXUS_GATEWAY_PORT"
PLAYER_PORT_ENV = "NEXUS_PLAYER_PORT"


def _port_from_environment(name: str) -> "int | None":
    import os

    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer port, got {raw!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{name} must be 1-65535, got {port}")
    return port


def gateway_port_override() -> "int | None":
    """Parse the operator-listener port override from the environment.

    Returns None when unset; raises ValueError loudly on garbage so a typo
    can never silently fall back to the configured port.
    """
    return _port_from_environment(GATEWAY_PORT_ENV)


def player_port_override() -> "int | None":
    """Parse the player-listener port override from the environment.

    Returns None when unset; raises ValueError loudly on garbage, as
    :func:`gateway_port_override` does.
    """
    return _port_from_environment(PLAYER_PORT_ENV)


@dataclass(frozen=True)
class GatewayPorts:
    """The gateway's listener ports: ``player`` is None in an operator-only lane."""

    player: Optional[int]
    operator: int


def gateway_listener_ports(runtime: "RuntimeSettings") -> GatewayPorts:
    """Resolve the gateway's listener ports from the config and the lane overrides.

    ``operator`` is ``NEXUS_GATEWAY_PORT`` or ``[runtime.gateway].operator_port``.
    With ``NEXUS_GATEWAY_PORT`` set, ``player`` is ``NEXUS_PLAYER_PORT`` or None
    (an operator-only lane that never binds the configured player port);
    without it, ``player`` is ``[runtime.services.gateway].port``.

    Raises:
        ValueError: An override is malformed, ``NEXUS_PLAYER_PORT`` is set
            without ``NEXUS_GATEWAY_PORT``, a lane port equals
            ``[runtime.services.gateway].port`` or
            ``[runtime.gateway].operator_port``, the two ports are equal, or
            the config has no ``[runtime.services.gateway]``.
    """
    gateway = runtime.services.get("gateway")
    if gateway is None:
        raise ValueError(
            "nexus.toml has no [runtime.services.gateway]; the gateway's "
            "listener ports cannot be resolved."
        )
    lane = gateway_port_override()
    player_lane = player_port_override()
    if lane is None:
        if player_lane is not None:
            raise ValueError(
                f"{PLAYER_PORT_ENV} is set without {GATEWAY_PORT_ENV}; a player "
                f"listener override belongs to a lane: export {GATEWAY_PORT_ENV} "
                "for the lane's operator listener too."
            )
        ports = GatewayPorts(
            player=gateway.port, operator=runtime.gateway.operator_port
        )
    else:
        # A lane never takes a configured listener port: the player port is the
        # tunnel's address, and the operator port belongs to the default
        # instance, whose state does not live under the lane's directory.
        configured = (
            ("[runtime.services.gateway].port", gateway.port),
            ("[runtime.gateway].operator_port", runtime.gateway.operator_port),
        )
        for variable, port in (
            (GATEWAY_PORT_ENV, lane),
            (PLAYER_PORT_ENV, player_lane),
        ):
            for key, configured_port in configured:
                if port == configured_port:
                    raise ValueError(
                        f"{variable}={port} is {key}, a listener of the default "
                        f"instance; a lane takes ports that neither "
                        "[runtime.services.gateway].port nor "
                        "[runtime.gateway].operator_port names."
                    )
        ports = GatewayPorts(player=player_lane, operator=lane)
    if ports.player == ports.operator:
        raise ValueError(
            f"The gateway's player and operator listeners cannot share port "
            f"{ports.operator}; set {PLAYER_PORT_ENV} and {GATEWAY_PORT_ENV} "
            "(or [runtime.services.gateway].port and "
            "[runtime.gateway].operator_port) to two ports."
        )
    return ports


def operator_url(runtime: "Optional[RuntimeSettings]") -> str:
    """Base URL of the local gateway's operator listener.

    The port is ``NEXUS_GATEWAY_PORT`` when set, else
    ``runtime.gateway.operator_port``, else the model default when ``runtime``
    is None (a bare install without nexus.toml).
    """
    port = gateway_port_override()
    if port is None:
        if runtime is not None:
            port = runtime.gateway.operator_port
        else:
            from nexus.config.settings_models import RuntimeGatewaySettings

            port = RuntimeGatewaySettings.model_fields["operator_port"].default
    return f"http://{OPERATOR_HOST}:{port}"
