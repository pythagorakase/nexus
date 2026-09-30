"""Run the NEXUS CLI with one slot routed to a disposable clone.

Run as ``python -m tests.slot_routed_cli <cli argv>`` with
``NEXUS_ROUTED_SLOT`` naming the routed slot and
``NEXUS_ROUTED_SLOT_DATABASE`` naming the clone. The CLI process opens slot
databases itself, not only through the gateway: ``nexus up`` and
``nexus restart`` call ``recover_active_slot_choice(slot)`` in the supervisor
before they spawn the gateway. Routing only the gateway child would leave
that call on the owner slot, so this entry point routes the CLI process too.

``tests.slot_routed_gateway.route_child_process`` routes the slot and
refuses every other slot, and raises when either variable is missing or
names an owner database, before ``nexus.cli`` loads. Then ``nexus.cli`` runs
as ``__main__`` with the forwarded argv, exactly as ``python -m nexus.cli``
does.
"""

from __future__ import annotations

import runpy

from tests.slot_routed_gateway import route_child_process


def main() -> None:
    """Route the slot, then run the CLI's own ``__main__`` block."""

    route_child_process()
    runpy.run_module("nexus.cli", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
