"""Live intertitle hydration: the raw SQL runs against a real slot.

The formatting tests construct intertitle dicts directly, which cannot
catch a wrong column name in the loader's SQL — per the repo's testing
philosophy, the query itself must execute against real Postgres.
Skipped unless NEXUS_RUN_POSTGRES=1.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.api.slot_utils import get_slot_db_url

pytestmark = pytest.mark.requires_postgres

LIVE_SLOT = 2


def test_load_intertitle_executes_against_live_slot() -> None:
    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT))
    with sessionmaker(engine)() as session:
        anchor = session.execute(
            text("SELECT max(chunk_id) FROM chunk_metadata")
        ).scalar()
        assert anchor is not None
        intertitle = TurnCycleManager._load_intertitle(
            session, anchor_chunk_id=int(anchor)
        )

    assert intertitle is not None
    assert intertitle["season"] is not None
    assert intertitle["world_time"] is not None
    # The user character's place carries Earth-shaped WGS84 coordinates.
    if intertitle["location_geom"] is not None:
        assert intertitle["location_geom"].startswith("SRID=4326;POINT(")


def test_anchor_fallback_skips_retrograde_chunks() -> None:
    """A maturation chunk at head must not become the resolve/intertitle anchor."""

    import json as _json

    from sqlalchemy import text

    from nexus.agents.lore.utils.turn_context import TurnContext
    from nexus.agents.orrery.retrograde_markers import RETROGRADE_SUMMARY_MARKER

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT))
    with sessionmaker(engine)() as session:
        session.execute(
            text(
                """
                INSERT INTO narrative_chunks (raw_text, authorial_directives)
                VALUES ('synthetic maturation summary', CAST(:markers AS jsonb))
                """
            ),
            {"markers": _json.dumps([RETROGRADE_SUMMARY_MARKER])},
        )
        inserted = session.execute(
            text("SELECT max(id) FROM narrative_chunks")
        ).scalar()

        mgr = TurnCycleManager.__new__(TurnCycleManager)
        ctx = TurnContext(turn_id="t", user_input="x", start_time=0)
        anchor = TurnCycleManager._orrery_anchor_chunk_id(mgr, session, ctx)

        assert anchor is not None and anchor < inserted
        session.rollback()
