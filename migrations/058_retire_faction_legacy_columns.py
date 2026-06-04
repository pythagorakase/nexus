"""Retire legacy faction semantic columns after the Orrery cutover."""

from __future__ import annotations

import json


LEGACY_FACTION_COLUMNS = (
    "ideology",
    "history",
    "current_activity",
    "hidden_agenda",
    "territory",
    "power_level",
    "resources",
)
SNAPSHOT_KEY = "legacy_faction_columns"
RETIREMENT_KEY = "legacy_faction_column_retirement"
MIGRATION_ID = "058_retire_faction_legacy_columns"


def run(conn) -> None:
    """Snapshot old faction columns into extra_data, then drop the columns."""

    with conn.cursor() as cur:
        legacy_columns = _existing_legacy_columns(cur)
        if legacy_columns:
            _snapshot_legacy_columns(cur, legacy_columns)
            _drop_legacy_columns(cur, legacy_columns)

    conn.commit()


def _existing_legacy_columns(cur) -> tuple[str, ...]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'factions'
          AND column_name = ANY(%s)
        """,
        (list(LEGACY_FACTION_COLUMNS),),
    )
    existing = {row[0] for row in cur.fetchall()}
    return tuple(column for column in LEGACY_FACTION_COLUMNS if column in existing)


def _snapshot_legacy_columns(cur, legacy_columns: tuple[str, ...]) -> None:
    snapshot_pairs = ", ".join(f"'{column}', f.{column}" for column in legacy_columns)
    cur.execute(
        f"""
        WITH legacy_snapshots AS (
            SELECT
                f.id,
                snapshot.value AS snapshot
            FROM factions AS f
            CROSS JOIN LATERAL (
                VALUES (jsonb_strip_nulls(jsonb_build_object({snapshot_pairs})))
            ) AS snapshot(value)
            WHERE snapshot.value <> '{{}}'::jsonb
        )
        UPDATE factions AS f
        SET extra_data = jsonb_set(
            jsonb_set(
                COALESCE(f.extra_data, '{{}}'::jsonb),
                %s,
                COALESCE(f.extra_data -> %s, '{{}}'::jsonb)
                    || legacy_snapshots.snapshot,
                true
            ),
            %s,
            jsonb_build_object(
                'migration',
                %s,
                'source_columns',
                %s::jsonb
            ),
            true
        )
        FROM legacy_snapshots
        WHERE f.id = legacy_snapshots.id
        """,
        (
            [SNAPSHOT_KEY],
            SNAPSHOT_KEY,
            [RETIREMENT_KEY],
            MIGRATION_ID,
            json.dumps(list(legacy_columns)),
        ),
    )


def _drop_legacy_columns(cur, legacy_columns: tuple[str, ...]) -> None:
    drop_clauses = ",\n    ".join(
        f"DROP COLUMN IF EXISTS {column}" for column in legacy_columns
    )
    cur.execute(f"ALTER TABLE factions\n    {drop_clauses}")
