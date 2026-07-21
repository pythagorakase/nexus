"""Post-090 claim shadows for rollback-only tests on pre-090 slot databases."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


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
