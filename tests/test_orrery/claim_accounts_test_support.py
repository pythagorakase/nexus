"""Slot-free claim fixtures shared by the rollback-only epistemics tests.

The claim-accounts shadows install post-090 shapes in the connection's temp
schema, so a test's writes to ``claims``, ``claim_awareness`` and
``backstory_secrets`` stay in ``pg_temp`` and never reach the public tables.
The valence shadow is a ``pg_temp.character_relationships`` table with the
post-088 ``valence_current`` column, copied from the public rows when a test
opens its transaction.

Rows come from two kinds of helper. The ``seed_*`` helpers here (``seed_conduit``
and ``seed_chain``) commit a module's starting graph from its synchronous clone
fixture through ``tests.pg_fixtures`` (``seed_character`` and
``seed_relationship``), which refuse the owner's databases by name. The
``insert_transaction_*`` writers (characters, factions, relationships, chains)
write public rows inside the caller's rolled-back transaction, for the rows a
test must create mid-test; each first reads the cursor's database name and
refuses an owner database exactly as the seed helpers do. The other
in-transaction writers (``_insert_chunk``, ``_insert_pair_tag`` and
``_insert_claim``) refuse an owner cursor the same way before any statement;
each test module supplies a cursor on its own disposable clone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import count
from pathlib import Path
from typing import Any
from uuid import uuid4

from nexus.agents.orrery.epistemics import ClaimParticipant, mint_claim_for_event
from nexus.agents.orrery.relationship_provenance import relationship_producer
from nexus.agents.orrery.replay import canonicalize
from nexus.config.settings_models import OrreryContagionSettings
from tests.pg_fixtures import (
    require_disposable_target,
    seed_character,
    seed_relationship,
)


MIGRATION_SQL = Path("migrations/090_claim_accounts.sql").read_text()
DISTORTION_MIGRATION_SQL = Path("migrations/092_claim_distortion_depth.sql").read_text()


_CREATE_SHADOW_SQL = """
    CREATE TEMP TABLE claims ON COMMIT DROP AS TABLE public.claims;
    CREATE TEMP SEQUENCE claims_id_seq;
    SELECT setval(
        'pg_temp.claims_id_seq',
        COALESCE((SELECT max(id) FROM claims), 0) + 1,
        false
    );
    ALTER TABLE claims
        ALTER COLUMN id SET DEFAULT nextval('pg_temp.claims_id_seq'),
        ALTER COLUMN created_at SET DEFAULT now(),
        ALTER COLUMN id SET NOT NULL,
        ALTER COLUMN world_event_id SET NOT NULL,
        ALTER COLUMN summary SET NOT NULL,
        ALTER COLUMN scope SET NOT NULL,
        ALTER COLUMN created_at SET NOT NULL,
        ADD PRIMARY KEY (id),
        ADD CHECK (scope IN ('common', 'bounded', 'private'));

    CREATE TEMP TABLE claim_awareness
        ON COMMIT DROP AS TABLE public.claim_awareness;
    CREATE TEMP SEQUENCE claim_awareness_id_seq;
    SELECT setval(
        'pg_temp.claim_awareness_id_seq',
        COALESCE((SELECT max(id) FROM claim_awareness), 0) + 1,
        false
    );
    ALTER TABLE claim_awareness
        ALTER COLUMN id SET DEFAULT nextval('pg_temp.claim_awareness_id_seq'),
        ALTER COLUMN created_at SET DEFAULT now(),
        ALTER COLUMN id SET NOT NULL,
        ALTER COLUMN claim_id SET NOT NULL,
        ALTER COLUMN knower_entity_id SET NOT NULL,
        ALTER COLUMN source_tier SET NOT NULL,
        ALTER COLUMN created_at SET NOT NULL,
        ADD PRIMARY KEY (id),
        ADD UNIQUE (claim_id, knower_entity_id),
        ADD CHECK (
            source_tier IN ('participant', 'witness', 'told', 'granted')
        );

"""


_CREATE_BACKSTORY_SHADOW_SQL = """
    CREATE TEMP TABLE backstory_secrets (
        id bigserial PRIMARY KEY,
        claim_id bigint NOT NULL UNIQUE,
        status text NOT NULL DEFAULT 'latent'
            CHECK (status IN ('latent', 'revealed', 'retired'))
    ) ON COMMIT DROP;
"""


_POST_090_INDEX_SQL = """
    CREATE UNIQUE INDEX ux_claims_world_event_account_v1
        ON claims (world_event_id, account_label)
        WHERE world_event_id IS NOT NULL;
"""


def install_claim_accounts_shadow_sync(
    cur: Any, *, include_backstory_shadow: bool = True
) -> None:
    """Shadow durable projections and install 090 without touching public tables."""

    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'claims'
              AND column_name = 'account_label'
        ) AS applied
        """
    )
    row = cur.fetchone()
    public_is_post_090 = bool(row["applied"] if isinstance(row, Mapping) else row[0])
    cur.execute(_CREATE_SHADOW_SQL)
    if include_backstory_shadow:
        cur.execute(_CREATE_BACKSTORY_SHADOW_SQL)
    if public_is_post_090:
        cur.execute(_POST_090_INDEX_SQL)
    else:
        cur.execute(
            """
            CREATE UNIQUE INDEX ux_claims_world_event_v1
                ON claims (world_event_id)
                WHERE world_event_id IS NOT NULL
            """
        )
        cur.execute(MIGRATION_SQL)
    cur.execute(
        "SELECT EXISTS ("
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = ANY(current_schemas(false)) "
        "AND table_name = 'claims' AND column_name = 'distortion_min_depth'"
        ")"
    )
    distortion_row = cur.fetchone()
    distortion_shaped = bool(
        next(iter(distortion_row.values()))
        if isinstance(distortion_row, Mapping)
        else distortion_row[0]
    )
    if not distortion_shaped:
        cur.execute(DISTORTION_MIGRATION_SQL)


async def install_claim_accounts_shadow_async(
    conn: Any, *, include_backstory_shadow: bool = True
) -> None:
    """Asyncpg twin of :func:`install_claim_accounts_shadow_sync`."""

    public_is_post_090 = bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'claims'
                  AND column_name = 'account_label'
            )
            """
        )
    )
    await conn.execute(_CREATE_SHADOW_SQL)
    if include_backstory_shadow:
        await conn.execute(_CREATE_BACKSTORY_SHADOW_SQL)
    if public_is_post_090:
        await conn.execute(_POST_090_INDEX_SQL)
    else:
        await conn.execute(
            """
            CREATE UNIQUE INDEX ux_claims_world_event_v1
                ON claims (world_event_id)
                WHERE world_event_id IS NOT NULL
            """
        )
        await conn.execute(MIGRATION_SQL)
    distortion_shaped = bool(
        await conn.fetchval(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = ANY(current_schemas(false)) "
            "AND table_name = 'claims' "
            "AND column_name = 'distortion_min_depth'"
            ")"
        )
    )
    if not distortion_shaped:
        await conn.execute(DISTORTION_MIGRATION_SQL)


# The chunk_metadata slug trigger renders scene with TO_CHAR(..., 'FM000');
# scenes >= 1000 overflow the mask to literal '###' and collide. Fixtures
# must therefore use small bounded scene numbers, never chunk ids (the
# narrative_chunks sequence never rolls back and grows without bound).
_SCENE_NUMBERS = count(1)
EPISTEMICS = {
    "enabled": True,
    "claim_event_types": ["threat_issued"],
    "aware_roles": ["actor", "target", "observer", "witness"],
}


def _install_valence_shadow(cur: Any) -> None:
    """Shadow the pending-088 table shape in this connection's temp schema."""

    cur.execute(
        r"""
        CREATE TEMP TABLE character_relationships ON COMMIT DROP AS
        SELECT cr.* FROM public.character_relationships cr;

        ALTER TABLE pg_temp.character_relationships
            ADD COLUMN IF NOT EXISTS valence_current numeric;

        UPDATE pg_temp.character_relationships
        SET valence_current = substring(
            emotional_valence::text FROM '^([+-]?[0-9]+)\|'
        )::numeric / 5.5
        WHERE valence_current IS NULL
        """
    )


def _settings(
    *,
    trusting: str = "1h",
    neutral: str = "never",
    hostile: str = "never",
    depth_cap: int = 4,
    age_horizon: str = "14d",
    fan_out_cap: int = 6,
    channels: Mapping[str, Any] | None = None,
    culture_profiles: Mapping[str, float] | None = None,
    enabled: bool = True,
) -> OrreryContagionSettings:
    """Return validated contagion settings with the Stage 2c fixture defaults."""

    return OrreryContagionSettings.model_validate(
        {
            "enabled": enabled,
            "dyad_tiers": {
                "trusting": trusting,
                "neutral": neutral,
                "hostile": hostile,
            },
            "dyad_overrides": {},
            "channels": dict(channels or {}),
            "culture_profiles": dict(culture_profiles or {}),
            "guards": {
                "depth_cap": depth_cap,
                "age_horizon": age_horizon,
                "fan_out_cap": fan_out_cap,
            },
        }
    )


def _insert_chunk(
    cur: Any,
    *,
    time_delta: timedelta = timedelta(0),
    world_layer: str = "primary",
) -> tuple[int, datetime]:
    """Insert one sequence-keyed chunk; return its ID and stamped world_time.

    Refuses an owner database before writing (``require_transaction_target``).
    """

    require_transaction_target(cur)
    token = uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES (%s, 'Rollback-only Stage 2c fixture.')
        RETURNING id
        """,
        (f"Stage 2c propagation fixture {token}.",),
    )
    chunk_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, time_delta,
            generation_date, slug
        ) VALUES (
            %s, 99, 99, %s, %s::world_layer_type, %s, now(), %s
        )
        """,
        (chunk_id, next(_SCENE_NUMBERS), world_layer, time_delta, token[:10]),
    )
    cur.execute(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s", (chunk_id,)
    )
    stamped_world_time = cur.fetchone()["world_time"]
    assert stamped_world_time is not None
    return chunk_id, stamped_world_time


def require_transaction_target(cur: Any) -> str:
    """Return the cursor's database name, refusing an owner database.

    The name is read client side from the psycopg2 connection
    (``connection.info.dbname``, libpq's ``PQdb``), so the check runs no
    statement: a cursor on the template or a save slot raises through
    ``tests.pg_fixtures.require_disposable_target`` before anything reaches
    the server.
    """

    return require_disposable_target(str(cur.connection.info.dbname))


def insert_transaction_character(cur: Any, label: str) -> tuple[int, int]:
    """Insert one active character in the caller's transaction.

    Returns its entity and character IDs. This is the transaction-scoped twin
    of ``tests.pg_fixtures.seed_character`` for a character a test creates
    mid-test; it refuses an owner database before writing.
    """

    require_transaction_target(cur)
    token = uuid4().hex[:10]
    cur.execute(
        "INSERT INTO entities (kind, is_active) "
        "VALUES ('character', true) RETURNING id"
    )
    entity_id = int(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO characters (name, entity_id) VALUES (%s, %s) RETURNING id",
        (f"propagation-{label}-{token}", entity_id),
    )
    return entity_id, int(cur.fetchone()["id"])


def insert_transaction_relationship(
    cur: Any,
    source_character_id: int,
    target_character_id: int,
    *,
    valence: str = "+3|trusting",
) -> None:
    """Write one attributed relationship and its valence-shadow twin in-transaction.

    ``tests.pg_fixtures.seed_relationship`` (through ``seed_conduit``) is the
    writer for a module's starting graph: it commits from the synchronous clone
    fixture, and each test's valence shadow copies the committed row. This
    writer exists next to it for a relationship a test must create inside its
    own rolled-back transaction: one whose endpoints the test itself creates
    mid-test, or a conduit added after the test has already authored state that
    a committed edge would change. It refuses an owner database exactly as the
    seed helpers do, attributes the public row to ``manual`` under migration
    115, and writes the ``pg_temp`` twin that the drain reads, because the
    shadow was copied before the row existed.
    """

    require_transaction_target(cur)
    with relationship_producer(cur, "manual"):
        cur.execute(
            """
            INSERT INTO public.character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, dynamic, recent_events, history
            ) VALUES (
                %s, %s, 'associate', %s,
                'Rollback-only Stage 2c conduit.', 'None.', 'Fixture.'
            )
            """,
            (source_character_id, target_character_id, valence),
        )
    cur.execute(
        """
        INSERT INTO pg_temp.character_relationships (
            character1_id, character2_id, relationship_type,
            emotional_valence, valence_current, dynamic, recent_events, history
        ) VALUES (
            %s, %s, 'associate', %s, %s,
            'Rollback-only Stage 2c conduit.', 'None.', 'Fixture.'
        )
        """,
        (
            source_character_id,
            target_character_id,
            valence,
            Decimal(valence.split("|", maxsplit=1)[0]) / Decimal("5.5"),
        ),
    )


def insert_transaction_faction(cur: Any, label: str) -> int:
    """Insert one active faction in the caller's transaction; return its entity.

    The transaction-scoped twin of ``tests.pg_fixtures.seed_faction``: the row
    takes the next free ``factions.id``, and an owner database is refused
    before writing.
    """

    require_transaction_target(cur)
    cur.execute(
        "INSERT INTO entities (kind, is_active) "
        "VALUES ('faction', true) RETURNING id"
    )
    entity_id = int(cur.fetchone()["id"])
    cur.execute("SELECT coalesce(max(id), 0) + 1 AS id FROM factions")
    faction_id = int(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO factions (id, name, entity_id) VALUES (%s, %s, %s)",
        (faction_id, f"propagation-{label}-{uuid4().hex[:10]}", entity_id),
    )
    return entity_id


def seed_conduit(
    dbname: str,
    source_character_id: int,
    target_character_id: int,
    *,
    valence: str = "+3|trusting",
) -> None:
    """Commit one Stage 2c ``associate`` conduit through ``seed_relationship``.

    Called from a module's synchronous clone fixture. ``valence_current`` is
    derived by the table's valence trigger, and each test's valence shadow
    copies the committed row when the test opens its transaction.
    """

    seed_relationship(
        dbname,
        subject_character_id=source_character_id,
        object_character_id=target_character_id,
        relationship_type="associate",
        emotional_valence=valence,
        dynamic="Stage 2c conduit fixture.",
        recent_events="None.",
        history="Fixture.",
    )


def seed_chain(dbname: str, label: str, length: int) -> list[int]:
    """Commit ``length`` characters linked in order by trusting conduits.

    Returns the chain's entity IDs in hop order. The fixture twin of
    ``insert_transaction_chain``: every character goes through
    ``seed_character`` and every edge through ``seed_conduit``.
    """

    entities: list[int] = []
    characters: list[int] = []
    for index in range(length):
        character_id, entity_id = seed_character(dbname, name=f"{label}-{index}")
        entities.append(entity_id)
        characters.append(character_id)
    for source, target in zip(characters, characters[1:]):
        seed_conduit(dbname, source, target)
    return entities


def _insert_pair_tag(
    cur: Any, subject_entity_id: int, object_entity_id: int, tag: str
) -> None:
    """Attach one registered pair tag from subject to object entity.

    Refuses an owner database before writing (``require_transaction_target``).
    """

    require_transaction_target(cur)
    cur.execute(
        """
        INSERT INTO entity_pair_tags (
            subject_entity_id, object_entity_id, pair_tag_id,
            source_kind, template_id
        )
        SELECT %s, %s, id, 'template', 'test_claim_propagation_live'
        FROM pair_tags WHERE tag = %s AND NOT deprecated
        """,
        (subject_entity_id, object_entity_id, tag),
    )
    assert cur.rowcount == 1


def _insert_claim(
    cur: Any,
    *,
    chunk_id: int,
    source_entity_id: int,
    birth_world_time: datetime | None,
    scope: str = "bounded",
) -> int:
    """Mint one claim for a fresh ``threat_issued`` event; return the claim ID.

    Refuses an owner database before writing (``require_transaction_target``).
    """

    require_transaction_target(cur)
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, world_layer,
            source, changed_fields, payload
        ) VALUES (
            'threat_issued', %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb
        )
        RETURNING id
        """,
        (chunk_id, source_entity_id),
    )
    event_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO world_event_entities (event_id, role, entity_id)
        VALUES (%s, 'actor', %s)
        """,
        (event_id, source_entity_id),
    )
    cur.execute("SELECT kind::text FROM entities WHERE id = %s", (source_entity_id,))
    source_kind = str(cur.fetchone()["kind"])
    minted = mint_claim_for_event(
        cur,
        world_event_id=event_id,
        event_type="threat_issued",
        summary="Rollback-only propagated claim.",
        participants=(
            ClaimParticipant(
                source_entity_id,
                "actor",
                f"Propagation source {source_entity_id}",
                source_kind,
            ),
        ),
        source_chunk_id=chunk_id,
        source_resolution_id=None,
        settings=EPISTEMICS,
    )
    assert minted is not None
    claim_id = minted.claim_id
    if scope != "bounded":
        cur.execute("UPDATE claims SET scope = %s WHERE id = %s", (scope, claim_id))
    cur.execute(
        """
        SELECT acquired_at_world_time
        FROM claim_awareness
        WHERE claim_id = %s AND knower_entity_id = %s
        """,
        (claim_id, source_entity_id),
    )
    assert cur.fetchone()["acquired_at_world_time"] == birth_world_time
    return claim_id


def insert_transaction_chain(cur: Any, length: int) -> tuple[list[int], list[int]]:
    """Insert ``length`` characters linked by trusting relationships in order.

    Transaction-scoped: every row goes through ``insert_transaction_character``
    and ``insert_transaction_relationship``, so an owner database is refused
    before the first write. ``seed_chain`` is the fixture twin.
    """

    entities: list[int] = []
    characters: list[int] = []
    for index in range(length):
        entity, character = insert_transaction_character(cur, f"chain-{index}")
        entities.append(entity)
        characters.append(character)
    for source, target in zip(characters, characters[1:]):
        insert_transaction_relationship(cur, source, target)
    return entities, characters


def _canonical_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Canonicalize rows by ID so live and replayed projections compare."""

    return [
        {key: canonicalize(value) for key, value in sorted(row.items())}
        for row in sorted(rows, key=lambda item: int(item["id"]))
    ]
