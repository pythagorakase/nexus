"""Slot-free claim fixtures shared by the rollback-only epistemics tests.

The claim-accounts and valence shadows install post-090 and post-088 shapes in
the connection's temp schema, so a test's writes to ``claims``,
``claim_awareness``, ``backstory_secrets`` and ``character_relationships`` never
reach the public tables. The row helpers (characters, relationship chains,
chunks, minted claims, contagion settings) take an open cursor and name no
database: each test module supplies a cursor on its own disposable clone.
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
    """Insert one sequence-keyed chunk; return its ID and stamped world_time."""

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


def _insert_character(cur: Any, label: str) -> tuple[int, int]:
    """Insert one active character; return its entity and character IDs."""

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


def _insert_relationship(
    cur: Any,
    source_character_id: int,
    target_character_id: int,
    *,
    valence: str = "+3|trusting",
) -> None:
    """Write one attributed public relationship and its valence-shadow twin."""

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


def _insert_claim(
    cur: Any,
    *,
    chunk_id: int,
    source_entity_id: int,
    birth_world_time: datetime | None,
    scope: str = "bounded",
) -> int:
    """Mint one claim for a fresh ``threat_issued`` event; return the claim ID."""

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


def _chain(cur: Any, length: int) -> tuple[list[int], list[int]]:
    """Insert ``length`` characters linked by trusting relationships in order."""

    entities: list[int] = []
    characters: list[int] = []
    for index in range(length):
        entity, character = _insert_character(cur, f"chain-{index}")
        entities.append(entity)
        characters.append(character)
    for source, target in zip(characters, characters[1:]):
        _insert_relationship(cur, source, target)
    return entities, characters


def _canonical_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Canonicalize rows by ID so live and replayed projections compare."""

    return [
        {key: canonicalize(value) for key, value in sorted(row.items())}
        for row in sorted(rows, key=lambda item: int(item["id"]))
    ]
