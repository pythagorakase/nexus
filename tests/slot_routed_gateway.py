"""Serve the real gateway entry point with one slot routed to a disposable clone.

Run as ``python -m tests.slot_routed_gateway`` with ``NEXUS_ROUTED_SLOT``
naming the routed slot and ``NEXUS_ROUTED_SLOT_DATABASE`` naming the clone.
Before any gateway module loads, ``route_child_process`` (through
``tests.pg_fixtures.route_slot_from_environment``) routes that slot to the
clone and refuses every other slot, and raises when either variable is
missing or names an owner database; then
``nexus.api.narrative`` runs as ``__main__``, exactly as
``python -m nexus.api.narrative`` does (``NARRATIVE_API_PORT`` selects the
port). ``NEXUS_SLOT`` keeps its production meaning: when it names the routed
slot the gateway's scheduler owns the clone's deferred work, when it is unset
no scheduler starts, and any other slot fails at startup. A live gate
therefore drives the production HTTP surface in a child process without
reaching an owner database. ``tests.slot_routed_uvicorn`` is the same gateway
behind the supervisor's uvicorn argv instead of ``NARRATIVE_API_PORT``.
"""

from __future__ import annotations

import runpy


def route_child_process() -> tuple[int, str]:
    """Route this child process's slot before its entry point loads.

    Returns the routed ``(slot, dbname)``; raises before routing anything
    when a routing variable is missing or names an owner database. Importing
    ``tests.pg_fixtures`` leaves the root logger unconfigured (issue #1037),
    so the entry point logs exactly as the production one does.
    """

    from tests.pg_fixtures import route_slot_from_environment

    return route_slot_from_environment()


def main() -> None:
    """Route the slot, then run the gateway's own ``__main__`` block."""

    route_child_process()
    runpy.run_module("nexus.api.narrative", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
