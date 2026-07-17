"""Unit tests for asynchronous narrative commit helpers."""

import uuid

import asyncpg
import pytest

from nexus.agents.logon.apex_schema import FactionStateUpdate, NewFaction, StateUpdates
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.api.commit_handler import apply_state_updates, insert_chunk_metadata
from nexus.api.db_converters import create_new_faction
from nexus.api.slot_utils import get_slot_db_url


class RecordingAsyncConnection:
    """Async connection stand-in that records executed SQL."""

    def __init__(self):
        self.statements = []

    async def execute(self, sql, *args):
        self.statements.append((" ".join(sql.split()), args))


@pytest.mark.asyncio
async def test_async_faction_state_updates_do_not_write_legacy_activity():
    """Faction state updates should not touch obsolete faction columns."""

    conn = RecordingAsyncConnection()

    await apply_state_updates(
        conn,
        StateUpdates(
            factions=[
                FactionStateUpdate(
                    faction_id=42,
                    recent_actions=["Shifted lookouts to the tram stop."],
                )
            ]
        ),
    )

    assert all("UPDATE factions" not in sql for sql, _args in conn.statements)


@pytest.mark.asyncio
async def test_async_chunk_metadata_insert_carries_generation_model():
    """The async commit helper writes the incubator's provenance value."""

    conn = RecordingAsyncConnection()

    await insert_chunk_metadata(
        conn,
        chunk_id=42,
        season=1,
        episode=2,
        scene=3,
        world_layer="primary",
        time_delta=60,
        generation_model="resolved-async-model",
    )

    sql, args = conn.statements[-1]
    assert "generation_model" in sql
    assert args[-1] == "resolved-async-model"


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_live_async_faction_writes_tags_without_legacy_columns():
    """Async faction creation/update should use tags and leave retired columns empty."""

    try:
        conn = await asyncpg.connect(get_slot_db_url(dbname="save_05"))
    except asyncpg.PostgresError as exc:
        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")

    transaction = conn.transaction()
    await transaction.start()
    try:
        await conn.execute(
            """
            ALTER TABLE entity_tags
                ADD COLUMN IF NOT EXISTS expires_at_world_time timestamptz
            """
        )
        has_power_level = await conn.fetchval(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'factions'
              AND column_name = 'power_level'
            """
        )
        if has_power_level:
            await conn.execute(
                "ALTER TABLE factions ALTER COLUMN power_level DROP DEFAULT"
            )
        tag_suffix = uuid.uuid4().hex[:12]
        created_tag = f"test_async_faction_created_{tag_suffix}"
        updated_tag = f"test_async_faction_updated_{tag_suffix}"

        await _seed_faction_tag(conn, created_tag)
        await _seed_faction_tag(conn, updated_tag)

        faction_id = await create_new_faction(
            conn,
            NewFaction(
                name=f"Async Faction Write Test {tag_suffix}",
                summary="Rollback-scoped faction write-boundary test.",
                orrery_tags=OrreryTagBestowal(applied_tags=[created_tag]),
            ),
        )
        faction = await conn.fetchrow(
            """
            SELECT entity_id
            FROM factions
            WHERE id = $1
            """,
            faction_id,
        )
        assert faction is not None
        legacy_columns = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'factions'
              AND column_name = ANY($1::text[])
            ORDER BY column_name
            """,
            [
                "ideology",
                "history",
                "current_activity",
                "hidden_agenda",
                "territory",
                "power_level",
                "resources",
            ],
        )
        if legacy_columns:
            column_names = [row["column_name"] for row in legacy_columns]
            legacy_row = await conn.fetchrow(
                f"""
                SELECT {', '.join(column_names)}
                FROM factions
                WHERE id = $1
                """,
                faction_id,
            )
            assert legacy_row is not None
            for column_name in column_names:
                assert legacy_row[column_name] is None
        assert await _has_active_tag(conn, faction["entity_id"], created_tag)

        await apply_state_updates(
            conn,
            StateUpdates(
                factions=[
                    FactionStateUpdate(
                        faction_id=faction_id,
                        orrery_tags=OrreryTagBestowal(
                            applied_tags=[updated_tag],
                            tags_to_clear=[created_tag],
                        ),
                    )
                ]
            ),
        )

        assert await _has_active_tag(conn, faction["entity_id"], updated_tag)
        assert not await _has_active_tag(conn, faction["entity_id"], created_tag)
    finally:
        await transaction.rollback()
        await conn.close()


async def _seed_faction_tag(conn, tag: str) -> None:
    await conn.execute(
        """
        INSERT INTO tag_category_registry (category, entity_kind, prompt_order)
        VALUES ('ideology', 'faction'::entity_kind, 999)
        ON CONFLICT (category, entity_kind) DO NOTHING
        """
    )
    await conn.execute(
        """
        INSERT INTO tags (tag, category, is_ephemeral, deprecated, description)
        VALUES ($1, 'ideology', FALSE, FALSE, 'Rollback-scoped async test tag.')
        """,
        tag,
    )


async def _has_active_tag(conn, entity_id: int, tag: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT 1
            FROM entity_tags et
            JOIN tags t ON t.id = et.tag_id
            WHERE et.entity_id = $1
              AND t.tag = $2
              AND et.cleared_at IS NULL
            """,
            entity_id,
            tag,
        )
    )
