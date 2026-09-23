"""Disposable slot routing for request-boundary PostgreSQL regressions."""

from collections.abc import Iterator

import pytest

from nexus.api import new_story_flow, setup_endpoints, slot_mutations, slot_state
from nexus.api import slot_utils
from tests.pg_fixtures import disposable_slot_database


@pytest.fixture
def offline_gate_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Route slot 4 to a real template clone, including the unchanged lock guard.

    The template supplies global_variables, assets.new_story_creator,
    assets.traits, narrative/incubator tables, generation leases, and Orrery
    queues. Only this clone is written; the helper closes pools and drops it.
    """
    with disposable_slot_database("qa640_offline_gate") as dbname:

        def fixture_slot_dbname(slot: int) -> str:
            assert slot == 4, f"Unexpected slot access: {slot}"
            return dbname

        monkeypatch.setattr(
            slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {dbname}
        )
        for module in (
            slot_utils,
            slot_mutations,
            slot_state,
            new_story_flow,
            setup_endpoints,
        ):
            monkeypatch.setattr(module, "slot_dbname", fixture_slot_dbname)
        yield dbname
