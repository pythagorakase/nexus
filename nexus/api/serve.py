"""Serve the gateway's player and operator projections from one process (#824).

``python -m nexus.api.serve --host H --port P --operator-port O --log-config L``
runs two uvicorn servers in one event loop over the one gateway app,
``nexus.api.narrative:app``:

- the operator projection (the whole runtime) on ``127.0.0.1:O``
  (:data:`nexus.runtime.contract.OPERATOR_HOST`), which runs the gateway's
  one lifespan (the slot scheduler) and starts first;
- the player projection on ``H:P``, the address the Cloudflare tunnel
  reaches, with no lifespan of its own; it starts only after the operator
  listener has started, so the scheduler exists before any player request.
  ``--port off`` serves no player listener (an operator-only lane).

SIGINT or SIGTERM stops both listeners and runs the lifespan shutdown once:
uvicorn's ``capture_signals`` chain hands the signal to the player server,
which re-raises it to the operator server after its own shutdown. If either
server fails to start or exits on its own, the launcher stops the other and
exits nonzero.

This module imports nothing from ``nexus.api.narrative`` at module scope
(the ``nexus.api`` no-side-effect rule); :func:`main` imports the gateway.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import TYPE_CHECKING, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexus.api.route_capabilities import Plane, build_operator_app, build_player_app
from nexus.config import get_gateway_cors_allowed_origins
from nexus.runtime.contract import OPERATOR_HOST

if TYPE_CHECKING:
    import uvicorn

# How often the launcher checks whether the operator listener has started.
_START_POLL_SECONDS = 0.05


def build_plane_app(source: FastAPI, plane: Plane) -> FastAPI:
    """Project ``plane`` of the gateway app ``source`` for one listener.

    The projection gets that plane's credentialed CORS list
    (``[runtime.gateway].<plane>_cors_allowed_origins``, D-824-CORS); the
    gateway app carries no middleware of its own, so nothing else is copied.
    """
    if plane == "player":
        projection = build_player_app(source)
    elif plane == "operator":
        projection = build_operator_app(source)
    else:
        raise ValueError(f"Unknown plane {plane!r}; expected 'player' or 'operator'")
    projection.add_middleware(
        CORSMiddleware,
        allow_origins=get_gateway_cors_allowed_origins(plane),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return projection


def _port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"must be an integer port, got {raw!r}"
        ) from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"must be 1-65535, got {port}")
    return port


def _player_port(raw: str) -> Optional[int]:
    return None if raw == "off" else _port(raw)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nexus.api.serve",
        description=(
            "Serve the gateway's player projection on --host:--port and its "
            f"operator projection on {OPERATOR_HOST}:--operator-port."
        ),
    )
    parser.add_argument("--host", required=True, help="Bind host of the player")
    parser.add_argument(
        "--port",
        required=True,
        type=_player_port,
        help="Player listener port (1-65535), or 'off' for no player listener",
    )
    parser.add_argument(
        "--operator-port",
        required=True,
        type=_port,
        help=f"Operator listener port on {OPERATOR_HOST} (1-65535)",
    )
    parser.add_argument(
        "--log-config",
        required=True,
        help="dictConfig JSON both listeners log through",
    )
    return parser


async def _run_server(server: "uvicorn.Server") -> int:
    """Serve until ``server`` stops; return its exit status (0 or nonzero).

    uvicorn calls ``sys.exit(1)`` when its listener cannot bind; inside a
    task that would escape the event loop and skip the other listener's
    shutdown, so it becomes this status and :func:`_serve` stops the other.
    """
    try:
        await server.serve()
    except (
        SystemExit
    ) as exc:  # nexus-exception-disposition: fail; reason=bind; safety=exit 1
        return exc.code if isinstance(exc.code, int) and exc.code else 1
    return 0


async def _serve(operator: "uvicorn.Server", player: "Optional[uvicorn.Server]") -> int:
    """Start the operator listener, then the player listener; stop them together."""
    operator_task = asyncio.create_task(_run_server(operator))
    while not operator.started:
        if operator_task.done():
            # The lifespan or the bind failed before the listener started.
            return operator_task.result() or 1
        await asyncio.sleep(_START_POLL_SECONDS)
    if player is None:
        code = await operator_task
        return code
    player_task = asyncio.create_task(_run_server(player))
    await asyncio.wait(
        {operator_task, player_task}, return_when=asyncio.FIRST_COMPLETED
    )
    if player_task.done():
        player_code = player_task.result()
        operator.should_exit = True
        operator_code = await operator_task
        if not player.started:
            return player_code or 1
        return player_code or operator_code
    # The operator listener stopped while the player listener still serves.
    player.should_exit = True
    await player_task
    return operator_task.result() or 1


def main(argv: Optional[List[str]] = None) -> None:
    """Parse the listener arguments and serve both planes until signaled."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.port == args.operator_port:
        parser.error(
            f"--port and --operator-port are both {args.port}; the player and "
            "operator listeners need two ports"
        )

    import uvicorn

    from nexus.api.narrative import app as gateway

    operator = uvicorn.Server(
        uvicorn.Config(
            build_plane_app(gateway, "operator"),
            host=OPERATOR_HOST,
            port=args.operator_port,
            lifespan="on",
            log_config=args.log_config,
        )
    )
    player = (
        None
        if args.port is None
        else uvicorn.Server(
            uvicorn.Config(
                build_plane_app(gateway, "player"),
                host=args.host,
                port=args.port,
                lifespan="off",
                log_config=args.log_config,
            )
        )
    )
    # uvicorn re-raises a captured SIGINT once its graceful shutdown is done
    # (Server.capture_signals); both listeners and the lifespan have stopped.
    try:
        code = asyncio.run(_serve(operator, player))
    except (
        KeyboardInterrupt
    ):  # nexus-exception-disposition: safe-continuation; reason=sigint; safety=shut
        code = 0
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
