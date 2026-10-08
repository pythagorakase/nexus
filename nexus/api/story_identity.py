"""The identity of the story a slot database holds (issue #822).

``public.story_identity`` holds one row in a save slot database and none in
``NEXUS_template``; ``public.story_lineage`` records the stories a story was
copied from. The cursor functions here run inside the caller's transaction:
they never commit and open no connection. Only :func:`detach_clone_identity`
opens (and commits) its own connection.
"""

from __future__ import annotations

from contextlib import closing
import re
from typing import Any, Literal

import psycopg2

from nexus.database import connection_kwargs, transaction

StoryOrigin = Literal["wizard", "clone", "import", "backfill"]


class StoryIdentityError(RuntimeError):
    """A database does not hold exactly one story identity row."""


def _first_value(row: Any) -> Any:
    """Return the first column of a mapping row or a tuple row."""
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def read_story_uuid(cur: Any) -> str:
    """Return the story_uuid of the database's single story_identity row.

    Raises:
        StoryIdentityError: When the table holds zero rows or more than one.
    """
    cur.execute("SELECT story_uuid::text AS story_uuid FROM public.story_identity")
    rows = cur.fetchall()
    if len(rows) != 1:
        raise StoryIdentityError(
            f"public.story_identity holds {len(rows)} rows; a story database "
            "holds exactly one"
        )
    return str(_first_value(rows[0]))


def replace_story_identity(cur: Any, *, origin: StoryOrigin) -> str:
    """Replace the database's identity with a new story_uuid and return it.

    Deleting the old row cascades to its story_lineage rows.
    """
    cur.execute("DELETE FROM public.story_identity")
    cur.execute(
        "INSERT INTO public.story_identity (origin) VALUES (%s) "
        "RETURNING story_uuid::text",
        (origin,),
    )
    return str(_first_value(cur.fetchone()))


def record_fork(
    cur: Any,
    *,
    child_uuid: str,
    parent_uuid: str,
    source_dbname: str,
    evidence: str,
) -> None:
    """Record that the story ``child_uuid`` is a fork of ``parent_uuid``."""
    cur.execute(
        """
        INSERT INTO public.story_lineage
            (child_uuid, parent_uuid, relation, source_dbname, evidence)
        VALUES (%s, %s, 'fork', %s, %s)
        """,
        (child_uuid, parent_uuid, source_dbname, evidence),
    )


def detach_clone_identity(dbname: str) -> str:
    """Give a disposable or rehearsal clone a fresh identity with no lineage.

    The clone's copied row (and any lineage it carried) is replaced by an
    origin ``clone`` row in one committed transaction, so the clone never
    carries the identity of the slot it was copied from.

    Raises:
        ValueError: When ``dbname`` names a save slot or ``NEXUS_template``;
            raised before any connection is opened.
        psycopg2.errors.UndefinedTable: When the database predates
            migration 146.
    """
    if re.fullmatch(r"save_0[1-5]", dbname) or dbname == "NEXUS_template":
        raise ValueError(
            f"detach_clone_identity refuses {dbname}: only a disposable or "
            "rehearsal clone is detached"
        )
    with closing(psycopg2.connect(**connection_kwargs(dbname))) as conn:
        with transaction(conn), conn.cursor() as cur:
            return replace_story_identity(cur, origin="clone")
