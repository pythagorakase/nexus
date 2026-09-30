"""Serve the real gateway entry point with one slot routed to a disposable clone.

Run as ``python -m tests.slot_routed_gateway`` with ``NEXUS_ROUTED_SLOT``
naming the routed slot and ``NEXUS_ROUTED_SLOT_DATABASE`` naming the clone.
Before any gateway module loads, ``tests.pg_fixtures.route_slot_to_disposable``
routes that slot to the clone and refuses every other slot; then
``nexus.api.narrative`` runs as ``__main__``, exactly as
``python -m nexus.api.narrative`` does (``NARRATIVE_API_PORT`` selects the
port). ``NEXUS_SLOT`` keeps its production meaning: when it names the routed
slot the gateway's scheduler owns the clone's deferred work, when it is unset
no scheduler starts, and any other slot fails at startup. A live gate
therefore drives the production HTTP surface in a child process without
reaching an owner database.
"""

from __future__ import annotations

import os
import runpy

from tests.pg_fixtures import route_slot_to_disposable


def main() -> None:
    """Route the slot, then run the gateway's own ``__main__`` block."""

    route_slot_to_disposable(
        setattr,
        slot=int(os.environ["NEXUS_ROUTED_SLOT"]),
        dbname=os.environ["NEXUS_ROUTED_SLOT_DATABASE"],
    )
    runpy.run_module("nexus.api.narrative", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
