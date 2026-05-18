"""Prep work for Skald runtime tag bestowal.

Two small things, both required before
``nexus.agents.orrery.tag_writer.apply_tag_bestowal`` can run safely:

1. Add ``skald_inline`` to ``entity_tag_source_kind`` so runtime-bestowed tags
   are auditably distinct from the offline batch (``llm_generated``) used by
   the slot 2 backfill applicator.

2. Recreate ``ix_entity_tags_current`` as a UNIQUE partial index. It already
   exists as UNIQUE in slot 2 (which is why the offline applicator's
   ``ON CONFLICT (entity_id, tag_id) WHERE cleared_at IS NULL DO NOTHING``
   works there) but is a non-unique index on ``NEXUS_template``. The
   runtime tag writer relies on the same ``ON CONFLICT`` clause, so the
   constraint must match in every slot freshly created from the template.

``ALTER TYPE ... ADD VALUE`` is committed in its own transaction (cannot run
inside a multi-statement block on PG < 12; safe but cleaner everywhere). The
index recreation is then atomic via ``DROP ... IF EXISTS`` + ``CREATE UNIQUE``
in a second transaction.
"""

from __future__ import annotations

from psycopg2 import sql


def run(conn) -> None:
    """Apply the migration: enum value + unique partial index."""

    _add_source_kind(conn)
    _recreate_current_index_unique(conn)


def _add_source_kind(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "ALTER TYPE entity_tag_source_kind ADD VALUE IF NOT EXISTS {}"
            ).format(sql.Literal("skald_inline"))
        )
    conn.commit()


def _recreate_current_index_unique(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP INDEX IF EXISTS ix_entity_tags_current")
        cur.execute(
            """
            CREATE UNIQUE INDEX ix_entity_tags_current
              ON entity_tags (entity_id, tag_id)
              WHERE cleared_at IS NULL
            """
        )
    conn.commit()
