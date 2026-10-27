"""Run the gateway's two-listener launcher with one slot routed to a clone.

Run as ``python -m tests.slot_routed_serve <launcher argv>`` with
``NEXUS_ROUTED_SLOT`` naming the routed slot and
``NEXUS_ROUTED_SLOT_DATABASE`` naming the clone. It stands in for
``python -m nexus.api.serve`` in the supervisor's gateway argv template, so
the supervisor's own substitution still supplies the rest of the command
unchanged::

    ["{python}", "-m", "tests.slot_routed_serve", "--host", "{host}",
     "--port", "{port}", "--operator-port", "{operator_port}",
     "--log-config", "{log_config}"]

Before the launcher imports the gateway,
``tests.slot_routed_gateway.route_child_process`` routes the slot to the
clone and refuses every other slot; it raises when either variable is
missing or names an owner database, before any port binds. Then
``nexus.api.serve`` runs as ``__main__`` with the forwarded argv, so both
listeners, their ``--log-config`` logging and their ``Uvicorn running on``
banners are exactly the supervisor's. ``NEXUS_SLOT`` keeps its production
meaning, as in ``tests.slot_routed_gateway``.
"""

from __future__ import annotations

import runpy

from tests.slot_routed_gateway import route_child_process


def main() -> None:
    """Route the slot, then run ``python -m nexus.api.serve`` with this argv."""

    route_child_process()
    runpy.run_module("nexus.api.serve", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
