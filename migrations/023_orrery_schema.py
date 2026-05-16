"""Add Orrery identity spine and off-screen behavior schema."""

from __future__ import annotations

from typing import Sequence

from psycopg2 import sql


SUBTYPE_TABLES = (
    ("characters", "character"),
    ("factions", "faction"),
    ("places", "place"),
)


def run(conn) -> None:
    """Apply the Orrery schema migration."""

    _create_enum_types(conn)
    _create_entities_table(conn)
    for table_name, kind in SUBTYPE_TABLES:
        _add_entity_column(conn, table_name)
        _add_entity_fk(conn, table_name)
    _backfill_entity_spine(conn)
    _create_entity_kind_trigger(conn)
    for table_name, kind in SUBTYPE_TABLES:
        _install_entity_kind_trigger(conn, table_name, kind)
        _validate_existing_entity_kinds(conn, table_name, kind)
        _validate_entity_fk(conn, table_name)
        _create_unique_entity_index(conn, table_name)
        _attach_unique_entity_constraint(conn, table_name)
        _enforce_entity_not_null(conn, table_name)
    _create_identity_views(conn)
    _create_tag_schema(conn)
    _create_orrery_tables(conn)
    _create_world_time_support(conn)


def _execute(conn, statement: str, params: Sequence[object] | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(statement, params)


def _execute_autocommit(conn, statement: sql.Composed | str) -> None:
    conn.commit()
    previous = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
    finally:
        conn.autocommit = previous


def _exists(conn, query: str, params: Sequence[object]) -> bool:
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone() is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    return _exists(
        conn,
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    )


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    return _exists(
        conn,
        """
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = %s
          AND constraint_name = %s
        """,
        (table_name, constraint_name),
    )


def _create_enum_types(conn) -> None:
    _execute(
        conn,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'entity_kind') THEN
                CREATE TYPE entity_kind AS ENUM ('character', 'faction', 'place');
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'entity_tag_source_kind'
            ) THEN
                CREATE TYPE entity_tag_source_kind AS ENUM (
                    'authored', 'llm_generated', 'system', 'template',
                    'auto_registered'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'entity_tag_clearance_kind'
            ) THEN
                CREATE TYPE entity_tag_clearance_kind AS ENUM (
                    'event', 'semantic', 'authored'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type
                WHERE typname = 'entity_tag_reapplication_policy'
            ) THEN
                CREATE TYPE entity_tag_reapplication_policy AS ENUM (
                    'new_row', 'extend_expiry', 'replace'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'event_source_kind'
            ) THEN
                CREATE TYPE event_source_kind AS ENUM (
                    'apex', 'resolver', 'narrator', 'bleed', 'authored'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'event_role_kind'
            ) THEN
                CREATE TYPE event_role_kind AS ENUM (
                    'actor', 'target', 'observer', 'beneficiary', 'witness'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'event_severity_kind'
            ) THEN
                CREATE TYPE event_severity_kind AS ENUM (
                    'minor', 'moderate', 'major', 'critical'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'orrery_promotion_status'
            ) THEN
                CREATE TYPE orrery_promotion_status AS ENUM (
                    'pending', 'promoted', 'skipped'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'orrery_narration_status'
            ) THEN
                CREATE TYPE orrery_narration_status AS ENUM (
                    'none', 'queued', 'leased', 'succeeded', 'failed'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'orrery_job_state'
            ) THEN
                CREATE TYPE orrery_job_state AS ENUM (
                    'queued', 'leased', 'succeeded', 'failed'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'offscreen_embedding_status'
            ) THEN
                CREATE TYPE offscreen_embedding_status AS ENUM (
                    'pending', 'embedded', 'failed'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'world_layer_type'
            ) THEN
                CREATE TYPE world_layer_type AS ENUM (
                    'primary', 'flashback', 'dream', 'extradiegetic'
                );
            END IF;
        END $$;
        """,
    )
    conn.commit()


def _create_entities_table(conn) -> None:
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS entities (
            id         bigserial PRIMARY KEY,
            kind       entity_kind NOT NULL,
            is_active  boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_entities_kind ON entities (kind);
        """,
    )
    conn.commit()


def _add_entity_column(conn, table_name: str) -> None:
    if _column_exists(conn, table_name, "entity_id"):
        return
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN entity_id bigint").format(
                sql.Identifier(table_name)
            )
        )
    conn.commit()


def _add_entity_fk(conn, table_name: str) -> None:
    constraint_name = f"{table_name}_entity_id_fkey"
    if _constraint_exists(conn, table_name, constraint_name):
        return
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                ALTER TABLE {}
                ADD CONSTRAINT {}
                FOREIGN KEY (entity_id) REFERENCES entities(id) NOT VALID
                """
            ).format(sql.Identifier(table_name), sql.Identifier(constraint_name))
        )
    conn.commit()


def _backfill_entity_spine(conn) -> None:
    for table_name, kind in SUBTYPE_TABLES:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT id FROM {} WHERE entity_id IS NULL ORDER BY id").format(
                    sql.Identifier(table_name)
                )
            )
            subtype_ids = [row[0] for row in cur.fetchall()]

        for subtype_id in subtype_ids:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO entities (kind) VALUES (%s::entity_kind) RETURNING id",
                    (kind,),
                )
                entity_id = cur.fetchone()[0]
                cur.execute(
                    sql.SQL("UPDATE {} SET entity_id = %s WHERE id = %s").format(
                        sql.Identifier(table_name)
                    ),
                    (entity_id, subtype_id),
                )
        conn.commit()


def _create_entity_kind_trigger(conn) -> None:
    _execute(
        conn,
        """
        CREATE OR REPLACE FUNCTION orrery_ensure_subtype_entity_kind()
        RETURNS trigger AS $$
        DECLARE
            expected entity_kind := TG_ARGV[0]::entity_kind;
            actual entity_kind;
        BEGIN
            IF NEW.entity_id IS NULL THEN
                INSERT INTO entities (kind) VALUES (expected)
                RETURNING id INTO NEW.entity_id;
            END IF;

            SELECT kind INTO actual FROM entities WHERE id = NEW.entity_id;
            IF actual IS NULL THEN
                RAISE EXCEPTION 'Entity id % does not exist', NEW.entity_id;
            END IF;
            IF actual <> expected THEN
                RAISE EXCEPTION 'Entity id % has kind %, expected %',
                    NEW.entity_id, actual, expected;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """,
    )
    conn.commit()


def _install_entity_kind_trigger(conn, table_name: str, kind: str) -> None:
    trigger_name = f"trg_{table_name}_entity_kind"
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("DROP TRIGGER IF EXISTS {} ON {}").format(
                sql.Identifier(trigger_name), sql.Identifier(table_name)
            )
        )
        cur.execute(
            sql.SQL(
                """
                CREATE TRIGGER {}
                BEFORE INSERT OR UPDATE OF entity_id ON {}
                FOR EACH ROW
                EXECUTE FUNCTION orrery_ensure_subtype_entity_kind(%s)
                """
            ).format(sql.Identifier(trigger_name), sql.Identifier(table_name)),
            (kind,),
        )
    conn.commit()


def _validate_existing_entity_kinds(conn, table_name: str, kind: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                SELECT COUNT(*)
                FROM {} subtype
                JOIN entities e ON e.id = subtype.entity_id
                WHERE e.kind <> %s::entity_kind
                """
            ).format(sql.Identifier(table_name)),
            (kind,),
        )
        mismatch_count = cur.fetchone()[0]
        if mismatch_count:
            raise RuntimeError(
                f"{table_name}.entity_id has {mismatch_count} wrong-kind rows"
            )


def _validate_entity_fk(conn, table_name: str) -> None:
    constraint_name = f"{table_name}_entity_id_fkey"
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER TABLE {} VALIDATE CONSTRAINT {}").format(
                sql.Identifier(table_name), sql.Identifier(constraint_name)
            )
        )
    conn.commit()


def _create_unique_entity_index(conn, table_name: str) -> None:
    index_name = f"ix_{table_name}_entity_id_unique"
    _execute_autocommit(
        conn,
        sql.SQL(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {} ON {} (entity_id)"
        ).format(sql.Identifier(index_name), sql.Identifier(table_name)),
    )


def _attach_unique_entity_constraint(conn, table_name: str) -> None:
    constraint_name = f"{table_name}_entity_id_unique"
    if _constraint_exists(conn, table_name, constraint_name):
        return
    index_name = f"ix_{table_name}_entity_id_unique"
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} UNIQUE USING INDEX {}").format(
                sql.Identifier(table_name),
                sql.Identifier(constraint_name),
                sql.Identifier(index_name),
            )
        )
    conn.commit()


def _enforce_entity_not_null(conn, table_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {} WHERE entity_id IS NULL").format(
                sql.Identifier(table_name)
            )
        )
        null_count = cur.fetchone()[0]
        if null_count:
            raise RuntimeError(
                f"{table_name}.entity_id has {null_count} NULL rows after backfill"
            )
        cur.execute(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = 'entity_id'
            """,
            (table_name,),
        )
        is_nullable = cur.fetchone()[0]
        if is_nullable == "YES":
            cur.execute(
                sql.SQL("ALTER TABLE {} ALTER COLUMN entity_id SET NOT NULL").format(
                    sql.Identifier(table_name)
                )
            )
    conn.commit()


def _create_identity_views(conn) -> None:
    _execute(
        conn,
        """
        CREATE OR REPLACE VIEW entity_names_v AS
            SELECT e.id, e.kind, c.name
            FROM entities e
            JOIN characters c ON c.entity_id = e.id
            WHERE e.kind = 'character'
        UNION ALL
            SELECT e.id, e.kind, f.name
            FROM entities e
            JOIN factions f ON f.entity_id = e.id
            WHERE e.kind = 'faction'
        UNION ALL
            SELECT e.id, e.kind, p.name
            FROM entities e
            JOIN places p ON p.entity_id = e.id
            WHERE e.kind = 'place';

        CREATE OR REPLACE VIEW chunk_entity_references_v AS
            SELECT ccr.chunk_id, c.entity_id, ccr.reference::text AS reference_type
            FROM chunk_character_references ccr
            JOIN characters c ON c.id = ccr.character_id
        UNION ALL
            SELECT cfr.chunk_id, f.entity_id, NULL::text AS reference_type
            FROM chunk_faction_references cfr
            JOIN factions f ON f.id = cfr.faction_id
        UNION ALL
            SELECT pcr.chunk_id, p.entity_id, pcr.reference_type::text AS reference_type
            FROM place_chunk_references pcr
            JOIN places p ON p.id = pcr.place_id;

        CREATE OR REPLACE VIEW entity_relationships_v AS
            SELECT
                c1.entity_id AS source_entity_id,
                c2.entity_id AS target_entity_id,
                'character'::text AS relationship_scope,
                cr.relationship_type::text AS relationship_type,
                cr.emotional_valence::text AS valence,
                cr.dynamic,
                cr.recent_events,
                cr.history,
                cr.extra_data
            FROM character_relationships cr
            JOIN characters c1 ON c1.id = cr.character1_id
            JOIN characters c2 ON c2.id = cr.character2_id
        UNION ALL
            SELECT
                f1.entity_id AS source_entity_id,
                f2.entity_id AS target_entity_id,
                'faction'::text AS relationship_scope,
                fr.relationship_type::text AS relationship_type,
                NULL::text AS valence,
                fr.current_status AS dynamic,
                NULL::text AS recent_events,
                fr.history,
                fr.extra_data
            FROM faction_relationships fr
            JOIN factions f1 ON f1.id = fr.faction1_id
            JOIN factions f2 ON f2.id = fr.faction2_id
        UNION ALL
            SELECT
                f.entity_id AS source_entity_id,
                c.entity_id AS target_entity_id,
                'faction_character'::text AS relationship_scope,
                fcr.role::text AS relationship_type,
                NULL::text AS valence,
                fcr.current_status AS dynamic,
                NULL::text AS recent_events,
                fcr.history,
                fcr.extra_data
            FROM faction_character_relationships fcr
            JOIN factions f ON f.id = fcr.faction_id
            JOIN characters c ON c.id = fcr.character_id;
        """,
    )
    conn.commit()


def _create_tag_schema(conn) -> None:
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS tags (
            id                   bigserial PRIMARY KEY,
            tag                  text UNIQUE NOT NULL,
            category             text NOT NULL,
            is_ephemeral         boolean NOT NULL DEFAULT false,
            clearance_kind       entity_tag_clearance_kind,
            reapplication_policy entity_tag_reapplication_policy,
            clear_on             jsonb,
            synonym_for          bigint REFERENCES tags(id),
            deprecated           boolean NOT NULL DEFAULT false,
            description          text,
            created_at           timestamptz NOT NULL DEFAULT now(),
            CHECK (is_ephemeral = (clearance_kind IS NOT NULL))
        );

        CREATE TABLE IF NOT EXISTS entity_tags (
            id                    bigserial PRIMARY KEY,
            entity_id             bigint NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            tag_id                bigint NOT NULL REFERENCES tags(id),
            applied_at            timestamptz NOT NULL DEFAULT now(),
            applied_at_world_time timestamptz,
            clear_on_override     jsonb,
            cleared_at            timestamptz,
            template_id           text,
            source_kind           entity_tag_source_kind NOT NULL,
            UNIQUE (entity_id, tag_id, applied_at)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ix_entity_tags_current
            ON entity_tags (entity_id, tag_id)
            WHERE cleared_at IS NULL;

        CREATE OR REPLACE VIEW entity_tags_current AS
            SELECT
                et.id AS entity_tag_id,
                et.entity_id,
                e.kind AS entity_kind,
                t.tag,
                t.category,
                t.is_ephemeral,
                t.clearance_kind,
                et.applied_at,
                et.applied_at_world_time,
                et.source_kind,
                et.template_id
            FROM entity_tags et
            JOIN entities e ON e.id = et.entity_id
            JOIN tags t ON t.id = et.tag_id
            WHERE t.deprecated = false
              AND et.cleared_at IS NULL
              AND t.synonym_for IS NULL;
        """,
    )
    conn.commit()


def _create_orrery_tables(conn) -> None:
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS event_types (
            type        text PRIMARY KEY,
            category    text NOT NULL,
            severity    event_severity_kind,
            description text,
            deprecated  boolean NOT NULL DEFAULT false,
            synonym_for text REFERENCES event_types(type)
        );

        CREATE TABLE IF NOT EXISTS orrery_resolutions (
            id                       bigserial PRIMARY KEY,
            tick_chunk_id            bigint NOT NULL REFERENCES narrative_chunks(id),
            template_id              text NOT NULL,
            binding_hash             text NOT NULL,
            actor_entity_id          bigint REFERENCES entities(id) ON DELETE RESTRICT,
            priority                 integer NOT NULL,
            magnitude                numeric(4,3),
            state_delta              jsonb NOT NULL,
            brief                    text,
            event_ids                bigint[],
            promotion_status         orrery_promotion_status NOT NULL DEFAULT 'pending',
            promotion_verdict        jsonb,
            narration_status         orrery_narration_status NOT NULL DEFAULT 'none',
            narration_chunk_id       bigint,
            last_offered_chunk_id    bigint REFERENCES narrative_chunks(id),
            offer_count              integer NOT NULL DEFAULT 0,
            first_surfaced_chunk_id  bigint REFERENCES narrative_chunks(id),
            created_at               timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tick_chunk_id, template_id, binding_hash)
        );

        CREATE TABLE IF NOT EXISTS world_events (
            id                     bigserial PRIMARY KEY,
            event_type             text NOT NULL REFERENCES event_types(type),
            tick_chunk_id          bigint NOT NULL REFERENCES narrative_chunks(id),
            narration_chunk_id     bigint,
            actor_entity_id        bigint REFERENCES entities(id) ON DELETE RESTRICT,
            target_entity_id       bigint REFERENCES entities(id) ON DELETE RESTRICT,
            location_id            bigint REFERENCES places(id) ON DELETE RESTRICT,
            world_layer            world_layer_type,
            source                 event_source_kind NOT NULL,
            changed_fields         text[] NOT NULL DEFAULT '{}',
            magnitude              numeric(4,3),
            resolution_id          bigint REFERENCES orrery_resolutions(id),
            payload                jsonb NOT NULL DEFAULT '{}',
            superseded_by_event_id bigint REFERENCES world_events(id),
            created_at             timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS world_event_entities (
            event_id  bigint NOT NULL REFERENCES world_events(id) ON DELETE CASCADE,
            role      event_role_kind NOT NULL,
            entity_id bigint NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
            PRIMARY KEY (event_id, role, entity_id)
        );

        CREATE TABLE IF NOT EXISTS offscreen_narrations (
            id                    bigserial PRIMARY KEY,
            resolution_id         bigint NOT NULL REFERENCES orrery_resolutions(id),
            tick_chunk_id         bigint NOT NULL REFERENCES narrative_chunks(id),
            world_layer           world_layer_type,
            text                  text NOT NULL,
            perceptual_descriptor jsonb,
            embedding_status      offscreen_embedding_status NOT NULL DEFAULT 'pending',
            created_at            timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS orrery_narration_jobs (
            id            bigserial PRIMARY KEY,
            resolution_id bigint NOT NULL REFERENCES orrery_resolutions(id),
            slot          text NOT NULL,
            state         orrery_job_state NOT NULL DEFAULT 'queued',
            attempts      integer NOT NULL DEFAULT 0,
            available_at  timestamptz NOT NULL DEFAULT now(),
            lease_until   timestamptz,
            locked_by     text,
            last_error    text,
            provider      text,
            model_ref     text,
            created_at    timestamptz NOT NULL DEFAULT now(),
            updated_at    timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS tag_clearance_log (
            id                    bigserial PRIMARY KEY,
            entity_tag_id          bigint NOT NULL REFERENCES entity_tags(id),
            cleared_at            timestamptz NOT NULL DEFAULT now(),
            cleared_at_world_time timestamptz,
            mechanism             entity_tag_clearance_kind NOT NULL,
            triggering_event_id   bigint REFERENCES world_events(id),
            justification         jsonb,
            source_chunk_id       bigint REFERENCES narrative_chunks(id)
        );

        CREATE INDEX IF NOT EXISTS ix_world_events_tick_chunk_id
            ON world_events (tick_chunk_id);
        CREATE INDEX IF NOT EXISTS ix_world_events_actor_entity_id
            ON world_events (actor_entity_id);
        CREATE INDEX IF NOT EXISTS ix_world_events_target_entity_id
            ON world_events (target_entity_id);
        CREATE INDEX IF NOT EXISTS ix_world_events_location_id
            ON world_events (location_id);
        CREATE INDEX IF NOT EXISTS ix_world_events_changed_fields
            ON world_events USING GIN (changed_fields);
        CREATE INDEX IF NOT EXISTS ix_world_events_resolution_id
            ON world_events (resolution_id);
        CREATE INDEX IF NOT EXISTS ix_orrery_resolutions_tick_chunk_id
            ON orrery_resolutions (tick_chunk_id);
        CREATE INDEX IF NOT EXISTS ix_orrery_resolutions_actor_entity_id
            ON orrery_resolutions (actor_entity_id);
        CREATE INDEX IF NOT EXISTS ix_orrery_resolutions_status
            ON orrery_resolutions (promotion_status, narration_status);
        CREATE INDEX IF NOT EXISTS ix_offscreen_narrations_tick_chunk_id
            ON offscreen_narrations (tick_chunk_id);
        CREATE INDEX IF NOT EXISTS ix_orrery_jobs_state_available
            ON orrery_narration_jobs (state, available_at);
        """,
    )
    _add_fk_if_missing(
        conn,
        table_name="orrery_resolutions",
        constraint_name="orrery_resolutions_narration_chunk_id_fkey",
        column_name="narration_chunk_id",
        target_table="offscreen_narrations",
        target_column="id",
    )
    _add_fk_if_missing(
        conn,
        table_name="world_events",
        constraint_name="world_events_narration_chunk_id_fkey",
        column_name="narration_chunk_id",
        target_table="offscreen_narrations",
        target_column="id",
    )
    conn.commit()


def _add_fk_if_missing(
    conn,
    *,
    table_name: str,
    constraint_name: str,
    column_name: str,
    target_table: str,
    target_column: str,
) -> None:
    if _constraint_exists(conn, table_name, constraint_name):
        return
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                ALTER TABLE {}
                ADD CONSTRAINT {}
                FOREIGN KEY ({}) REFERENCES {}({})
                """
            ).format(
                sql.Identifier(table_name),
                sql.Identifier(constraint_name),
                sql.Identifier(column_name),
                sql.Identifier(target_table),
                sql.Identifier(target_column),
            )
        )


def _create_world_time_support(conn) -> None:
    if not _column_exists(conn, "chunk_metadata", "world_time"):
        _execute(conn, "ALTER TABLE chunk_metadata ADD COLUMN world_time timestamptz")
        conn.commit()

    _execute(
        conn,
        """
        CREATE OR REPLACE FUNCTION refresh_world_time_from_chunk()
        RETURNS void AS $$
        BEGIN
            WITH baseline AS (
                SELECT COALESCE(
                    (SELECT base_timestamp FROM global_variables WHERE id = true),
                    now()
                ) AS base_time
            ),
            computed AS (
                SELECT
                    cm.chunk_id,
                    baseline.base_time + COALESCE(
                        SUM(COALESCE(cm.time_delta, '0 seconds'::interval))
                            OVER (ORDER BY cm.chunk_id),
                        '0 seconds'::interval
                    ) AS world_time
                FROM chunk_metadata cm
                CROSS JOIN baseline
            )
            UPDATE chunk_metadata cm
            SET world_time = computed.world_time
            FROM computed
            WHERE cm.chunk_id = computed.chunk_id;
        END;
        $$ LANGUAGE plpgsql;

        CREATE OR REPLACE FUNCTION refresh_world_time_from_chunk_trigger()
        RETURNS trigger AS $$
        BEGIN
            PERFORM refresh_world_time_from_chunk();
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_chunk_metadata_refresh_world_time
            ON chunk_metadata;
        CREATE TRIGGER trg_chunk_metadata_refresh_world_time
            AFTER INSERT OR UPDATE OF time_delta ON chunk_metadata
            FOR EACH STATEMENT
            EXECUTE FUNCTION refresh_world_time_from_chunk_trigger();

        DROP FUNCTION IF EXISTS refresh_world_time_from_chunk(bigint);

        SELECT refresh_world_time_from_chunk();
        """,
    )
    conn.commit()
