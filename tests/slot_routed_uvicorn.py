"""Run uvicorn with one slot routed to a disposable clone.

Run as ``python -m tests.slot_routed_uvicorn <uvicorn argv>`` with
``NEXUS_ROUTED_SLOT`` naming the routed slot and
``NEXUS_ROUTED_SLOT_DATABASE`` naming the clone. It stands in for
``python -m uvicorn`` in a supervisor service's argv template, so the
supervisor's own substitution still supplies the rest of the command
unchanged::

    ["{python}", "-m", "tests.slot_routed_uvicorn", "nexus.api.narrative:app",
     "--host", "{host}", "--port", "{port}", "--log-config", "{log_config}"]

Before uvicorn imports the application,
``tests.slot_routed_gateway.route_child_process`` routes the slot to the
clone and refuses every other slot; it raises when either variable is
missing or names an owner database, before uvicorn starts or any port
binds. Then uvicorn's own ``__main__`` runs with the forwarded argv, so the
gateway, its ``--log-config`` logging and its ``Uvicorn running on`` banner
are exactly the supervisor's. ``NEXUS_SLOT`` keeps its production meaning, as
in ``tests.slot_routed_gateway``.
"""

from __future__ import annotations

import runpy

from tests.slot_routed_gateway import route_child_process


def main() -> None:
    """Route the slot, then run ``python -m uvicorn`` with this argv."""

    route_child_process()
    runpy.run_module("uvicorn", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
