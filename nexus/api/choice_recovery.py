"""Clear a recastable parent choice atomically with undo or startup recovery."""

import json
import logging
from typing import Any, Optional

from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.api.lore_adapter import compute_raw_text

logger = logging.getLogger("nexus.api.choice_recovery")


def clear_parent_choice(cur: Any, parent_chunk_id: int) -> None:
    """Clear the selection while preserving the parent's offered menu."""
    cur.execute(
        "SELECT storyteller_text, choice_object FROM narrative_chunks "
        "WHERE id = %s FOR UPDATE",
        (parent_chunk_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Parent chunk {parent_chunk_id} not found")
    storyteller_text, choice_object = row
    if not storyteller_text:
        raise ValueError(f"Parent chunk {parent_chunk_id} has no storyteller_text")
    if choice_object is not None:
        choice_object = dict(choice_object, selected=None)
    cur.execute(
        """
        UPDATE narrative_chunks
        SET choice_text = NULL, choice_object = %s, raw_text = %s
        WHERE id = %s
        """,
        (
            json.dumps(choice_object) if choice_object is not None else None,
            compute_raw_text(storyteller_text, choice_object, None),
            parent_chunk_id,
        ),
    )


def recover_orphaned_choice(conn: Any) -> Optional[int]:
    """Clear an unaccepted latest choice unless an incubator draft owns it.

    Lock both tables in commit order so the absence checks and reset cannot race
    an accepting transaction or an incubator write. A second startup is a no-op.
    """
    cleared = None
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "LOCK TABLE incubator, narrative_chunks IN SHARE ROW EXCLUSIVE MODE"
            )
            cur.execute("SELECT 1 FROM incubator LIMIT 1")
            if cur.fetchone() is not None:
                return None
            cur.execute(
                f"SELECT nc.id, nc.choice_text FROM narrative_chunks nc "
                f"WHERE {playable_narrative_predicate()} ORDER BY nc.id DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is not None and (row[1] or "").strip():
                cleared = int(row[0])
                clear_parent_choice(cur, cleared)
    if cleared is not None:
        logger.warning(
            "Startup recovery cleared orphaned player choice on chunk %s", cleared
        )
    return cleared


def recover_active_slot_choice(slot: int) -> Optional[int]:
    """Recover the active writable slot before serving narrative requests."""
    from nexus.api.db_pool import get_connection
    from nexus.api.save_slots import is_slot_locked
    from nexus.api.slot_utils import slot_dbname

    dbname = slot_dbname(slot)
    if is_slot_locked(slot, dbname=dbname):
        return None
    with get_connection(dbname) as conn:
        return recover_orphaned_choice(conn)
