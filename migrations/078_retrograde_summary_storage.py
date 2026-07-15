"""Move Retrograde event summaries out of narrative continuity storage.

Legacy Retrograde summaries were finalized ``narrative_chunks`` rows.  That
made generated history look like played narrative to chronology, checkpoint,
and reader code.  This migration gives the summaries their own identity and
moves every dimension-specific embedding with them.

The migration runner owns the transaction boundary.  ``run`` deliberately
does not commit: every catalog preflight, copy, payload cleanup, and legacy-row
delete rolls back together if any invariant fails.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from psycopg2 import sql


RETROGRADE_SUMMARY_MARKER = "orrery:retrograde_event_summary"
RETROGRADE_EVENT_MARKER_PREFIX = "orrery:retrograde_event:"
RETROGRADE_PROLOGUE_MARKER = "orrery:retrograde_prologue_anchor"
SOURCE_EMBEDDING_TABLE = re.compile(r"^chunk_embeddings_(?P<dimensions>\d+)d$")
TARGET_EMBEDDING_TABLE = re.compile(
    r"^retrograde_summary_embeddings_(?P<dimensions>\d+)d$"
)
MATURATION_EVENT_REF = re.compile(r"^maturation_job_(?P<job_id>[1-9]\d*)_")
LEGACY_MANIFEST_SCHEMA_VERSION = "orrery_retrograde_maturation_manifest.v0"
TARGET_MANIFEST_SCHEMA_VERSION = "orrery_retrograde_maturation_manifest.v1"
VALID_CHRONOLOGIES = frozenset({"deep_past", "recent_past", "opening_pressure"})


def run(conn: Any) -> None:
    """Create dedicated storage and atomically migrate all legacy summaries."""

    with conn.cursor() as cur:
        _require_clean_target(cur)
        _require_base_schema(cur)
        _lock_legacy_writers(cur)
        embedding_tables = _discover_source_embedding_tables(cur)
        _lock_source_embedding_tables(cur, embedding_tables)
        legacy_rows = _load_and_validate_legacy_rows(cur)
        backfill_rows = _load_and_validate_backfill_events(cur)
        legacy_ids = [int(row[0]) for row in legacy_rows]
        recording_boundaries = _resolve_recording_boundaries(cur, legacy_rows)
        backfill_boundaries = _resolve_backfill_recording_boundaries(cur, backfill_rows)
        all_boundaries = set(recording_boundaries.values()) | set(
            backfill_boundaries.values()
        )
        invalid_boundaries = sorted(all_boundaries & set(legacy_ids))
        if invalid_boundaries:
            raise RuntimeError(
                "Retrograde summaries cannot record against legacy summary "
                f"chunks that migration 078 will delete: {invalid_boundaries}"
            )
        _validate_narrative_references(cur, legacy_ids, embedding_tables)
        _require_embedding_stamp_coverage(cur, legacy_rows, embedding_tables)

        identity_start = max(legacy_ids, default=0) + 1
        _create_summary_table(cur, identity_start=identity_start)
        for table_name, dimensions in embedding_tables:
            _create_summary_embedding_table(cur, table_name, dimensions)

        _copy_summaries(cur, legacy_rows, recording_boundaries)
        _copy_backfill_summaries(cur, backfill_rows, backfill_boundaries)
        embedding_counts = _copy_embeddings(cur, embedding_tables, legacy_ids)
        _update_maturation_manifests(cur, legacy_ids)
        _remove_legacy_payload_links(cur, legacy_ids)
        _delete_legacy_chunks(cur, legacy_ids)
        _install_legacy_write_guards(cur)
        _validate_postconditions(
            cur,
            expected_summary_count=len(legacy_ids) + len(backfill_rows),
            expected_embedding_counts=embedding_counts,
        )


def _require_clean_target(cur: Any) -> None:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND (
              table_name = 'retrograde_summaries'
              OR table_name ~ '^retrograde_summary_embeddings_[0-9]+d$'
          )
        ORDER BY table_name
        """
    )
    existing = [str(row[0]) for row in cur.fetchall()]
    if existing:
        raise RuntimeError(
            "Migration 078 requires a clean target schema; found: "
            + ", ".join(existing)
        )


def _require_base_schema(cur: Any) -> None:
    requirements = {
        "narrative_chunks": {
            "id",
            "raw_text",
            "storyteller_text",
            "choice_object",
            "choice_text",
            "authorial_directives",
            "state",
            "embedding_generated_at",
            "created_at",
        },
        "chunk_metadata": {
            "chunk_id",
            "season",
            "episode",
            "scene",
            "world_layer",
        },
        "world_events": {
            "id",
            "tick_chunk_id",
            "source",
            "payload",
            "created_at",
        },
        "orrery_maturation_jobs": {
            "id",
            "requesting_chunk_id",
            "result_manifest",
            "updated_at",
        },
    }
    for table_name, required_columns in requirements.items():
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        )
        actual = {str(row[0]) for row in cur.fetchall()}
        missing = sorted(required_columns - actual)
        if missing:
            raise RuntimeError(
                f"Migration 078 requires public.{table_name} columns: {missing}"
            )

    cur.execute("SELECT to_regtype('vector') IS NOT NULL")
    if not bool(cur.fetchone()[0]):
        raise RuntimeError("Migration 078 requires the pgvector vector type")


def _lock_legacy_writers(cur: Any) -> None:
    """Freeze every legacy writer before the migration reads its source set."""

    cur.execute(
        """
        LOCK TABLE
            world_events,
            narrative_chunks,
            chunk_metadata,
            orrery_maturation_jobs
        IN ACCESS EXCLUSIVE MODE
        """
    )


def _lock_source_embedding_tables(
    cur: Any, embedding_tables: Iterable[tuple[str, int]]
) -> None:
    """Hold dynamic source-vector tables stable through copy and delete."""

    for table_name, _dimensions in embedding_tables:
        cur.execute(
            sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                sql.Identifier(table_name)
            )
        )


def _discover_source_embedding_tables(cur: Any) -> list[tuple[str, int]]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name ~ '^chunk_embeddings_[0-9]+d$'
        ORDER BY table_name
        """
    )
    tables: list[tuple[str, int]] = []
    dimensions_seen: dict[int, str] = {}
    for (raw_name,) in cur.fetchall():
        table_name = str(raw_name)
        match = SOURCE_EMBEDDING_TABLE.fullmatch(table_name)
        if match is None:
            raise RuntimeError(f"Unexpected embedding table name {table_name!r}")
        dimensions = int(match.group("dimensions"))
        if dimensions <= 0:
            raise RuntimeError(f"Embedding table {table_name!r} has zero dimensions")
        prior = dimensions_seen.get(dimensions)
        if prior is not None:
            raise RuntimeError(
                "Multiple source embedding tables canonicalize to the same "
                f"dimension: {prior!r}, {table_name!r}"
            )
        dimensions_seen[dimensions] = table_name
        _validate_source_embedding_table(cur, table_name, dimensions)
        tables.append((table_name, dimensions))
    return tables


def _validate_source_embedding_table(
    cur: Any, table_name: str, dimensions: int
) -> None:
    cur.execute(
        """
        SELECT
            a.attname,
            format_type(a.atttypid, a.atttypmod),
            a.attnotnull
        FROM pg_attribute AS a
        WHERE a.attrelid = to_regclass(%s)
          AND a.attnum > 0
          AND NOT a.attisdropped
        """,
        (f"public.{table_name}",),
    )
    columns = {
        str(name): (str(formatted_type), bool(not_null))
        for name, formatted_type, not_null in cur.fetchall()
    }
    expected = {
        "chunk_id": ("bigint", True),
        "model": ("text", True),
        "embedding": (f"vector({dimensions})", True),
        "created_at": ("timestamp with time zone", True),
    }
    mismatches = {
        name: {"expected": spec, "actual": columns.get(name)}
        for name, spec in expected.items()
        if columns.get(name) != spec
    }
    if mismatches:
        raise RuntimeError(
            f"Embedding table public.{table_name} failed catalog preflight: "
            f"{mismatches}"
        )

    cur.execute(
        sql.SQL(
            """
            SELECT chunk_id, model, count(*)
            FROM {}
            GROUP BY chunk_id, model
            HAVING count(*) > 1
            LIMIT 1
            """
        ).format(sql.Identifier(table_name))
    )
    duplicate = cur.fetchone()
    if duplicate is not None:
        raise RuntimeError(
            f"Embedding table {table_name} contains duplicate identity {duplicate!r}"
        )


def _load_and_validate_legacy_rows(cur: Any) -> list[tuple[Any, ...]]:
    marker_json = json.dumps([RETROGRADE_SUMMARY_MARKER])
    cur.execute(
        """
        SELECT id
        FROM world_events
        WHERE payload ? 'retrograde_summary_chunk_id'
          AND (payload ->> 'retrograde_summary_chunk_id') !~ '^[1-9][0-9]*$'
        LIMIT 1
        """
    )
    malformed_link = cur.fetchone()
    if malformed_link is not None:
        raise RuntimeError(
            "Malformed world_events.payload.retrograde_summary_chunk_id on "
            f"world event {malformed_link[0]}"
        )

    cur.execute(
        """
        SELECT (payload ->> 'retrograde_summary_chunk_id')::bigint, count(*)
        FROM world_events
        WHERE payload ? 'retrograde_summary_chunk_id'
        GROUP BY (payload ->> 'retrograde_summary_chunk_id')::bigint
        HAVING count(*) <> 1
        LIMIT 1
        """
    )
    duplicate_link = cur.fetchone()
    if duplicate_link is not None:
        raise RuntimeError(
            "Legacy Retrograde summary link is not one-to-one: "
            f"chunk={duplicate_link[0]} events={duplicate_link[1]}"
        )

    cur.execute(
        """
        WITH marked AS (
            SELECT id
            FROM narrative_chunks
            WHERE authorial_directives @> %s::jsonb
        ),
        linked AS (
            SELECT (payload ->> 'retrograde_summary_chunk_id')::bigint AS id
            FROM world_events
            WHERE payload ? 'retrograde_summary_chunk_id'
        )
        SELECT
            COALESCE(marked.id, linked.id) AS id,
            marked.id IS NOT NULL AS is_marked,
            linked.id IS NOT NULL AS is_linked
        FROM marked
        FULL OUTER JOIN linked USING (id)
        WHERE marked.id IS NULL OR linked.id IS NULL
        ORDER BY id
        LIMIT 1
        """,
        (marker_json,),
    )
    unmatched = cur.fetchone()
    if unmatched is not None:
        raise RuntimeError(
            "Legacy Retrograde summaries must have both marker and world-event "
            f"link: chunk={unmatched[0]} marked={unmatched[1]} linked={unmatched[2]}"
        )

    cur.execute(
        """
        SELECT
            nc.id,
            we.id AS world_event_id,
            we.tick_chunk_id,
            we.payload ->> 'chronology' AS chronology,
            COALESCE(
                NULLIF(btrim(nc.storyteller_text), ''),
                NULLIF(btrim(nc.raw_text), '')
            ) AS summary_text,
            nc.embedding_generated_at,
            nc.created_at,
            nc.authorial_directives,
            we.payload ->> 'retrograde_event_ref' AS event_ref,
            we.payload ->> 'summary' AS event_summary,
            we.source::text AS source,
            nc.state::text AS chunk_state,
            nc.choice_object,
            nc.choice_text,
            count(cm.chunk_id) AS metadata_count,
            min(cm.season) AS season,
            min(cm.episode) AS episode,
            min(cm.world_layer::text) AS world_layer,
            nc.raw_text,
            nc.storyteller_text
        FROM narrative_chunks AS nc
        JOIN world_events AS we
          ON (we.payload ->> 'retrograde_summary_chunk_id')::bigint = nc.id
        LEFT JOIN chunk_metadata AS cm ON cm.chunk_id = nc.id
        WHERE nc.authorial_directives @> %s::jsonb
        GROUP BY nc.id, we.id
        ORDER BY nc.id
        """,
        (marker_json,),
    )
    rows = list(cur.fetchall())
    for row in rows:
        (
            chunk_id,
            world_event_id,
            recorded_at_chunk_id,
            chronology,
            summary_text,
            _embedding_generated_at,
            _created_at,
            directives,
            event_ref,
            event_summary,
            source,
            chunk_state,
            choice_object,
            choice_text,
            metadata_count,
            season,
            episode,
            world_layer,
            raw_text,
            storyteller_text,
        ) = row
        problems: list[str] = []
        if recorded_at_chunk_id is None or int(recorded_at_chunk_id) == int(chunk_id):
            problems.append("recorded_at/tick anchor is missing or self-referential")
        if chronology not in VALID_CHRONOLOGIES:
            problems.append(f"invalid chronology {chronology!r}")
        normalized_event_summary = str(event_summary or "").strip()
        normalized_raw_text = str(raw_text or "").strip()
        normalized_storyteller_text = str(storyteller_text or "").strip()
        if not normalized_raw_text:
            problems.append("raw_text is blank")
        if not normalized_storyteller_text:
            problems.append("storyteller_text is blank")
        if normalized_raw_text != normalized_storyteller_text:
            problems.append("raw_text and storyteller_text diverge")
        if normalized_storyteller_text != normalized_event_summary:
            problems.append("narrative and world-event summaries diverge")
        if not summary_text:
            problems.append("derived summary text is blank")
        if source != "retrograde":
            problems.append(f"world event source is {source!r}")
        if chunk_state != "finalized":
            problems.append(f"narrative state is {chunk_state!r}")
        if choice_object is not None or choice_text is not None:
            problems.append("summary chunk carries player choices")
        if int(metadata_count) != 1:
            problems.append(f"metadata row count is {metadata_count}")
        if season != 0 or episode != 0 or world_layer != "retrograde":
            problems.append(
                f"metadata is season={season} episode={episode} layer={world_layer!r}"
            )
        if not event_ref:
            problems.append("world event has no retrograde_event_ref")
        marker = f"{RETROGRADE_EVENT_MARKER_PREFIX}{event_ref}"
        if (
            not isinstance(directives, list)
            or directives.count(RETROGRADE_SUMMARY_MARKER) != 1
        ):
            problems.append("missing unique shared Retrograde summary marker")
        if not isinstance(directives, list) or directives.count(marker) != 1:
            problems.append(f"missing unique event marker {marker!r}")
        if problems:
            raise RuntimeError(
                f"Legacy Retrograde summary {chunk_id} / event {world_event_id} "
                "failed preflight: " + "; ".join(problems)
            )
    return rows


def _load_and_validate_backfill_events(cur: Any) -> list[tuple[Any, ...]]:
    """Load canonical Retrograde events that never received a legacy chunk.

    The world event is the durable source of truth for these rows.  Migration
    078 refuses to invent prose, chronology, or timestamps when that canonical
    payload is malformed.
    """

    cur.execute(
        """
        SELECT
            id,
            payload ->> 'retrograde_event_ref' AS event_ref,
            payload ->> 'chronology' AS chronology,
            payload ->> 'summary' AS summary_text,
            created_at,
            jsonb_typeof(payload -> 'retrograde_event_ref') AS event_ref_type,
            jsonb_typeof(payload -> 'chronology') AS chronology_type,
            jsonb_typeof(payload -> 'summary') AS summary_type
        FROM world_events
        WHERE source = 'retrograde'::event_source_kind
          AND NOT (payload ? 'retrograde_summary_chunk_id')
        ORDER BY id
        """
    )
    rows = list(cur.fetchall())
    for row in rows:
        (
            world_event_id,
            event_ref,
            chronology,
            summary_text,
            created_at,
            event_ref_type,
            chronology_type,
            summary_type,
        ) = row
        problems: list[str] = []
        if event_ref_type != "string" or not str(event_ref or "").strip():
            problems.append("payload.retrograde_event_ref is not a nonblank string")
        if chronology_type != "string" or chronology not in VALID_CHRONOLOGIES:
            problems.append(f"invalid payload.chronology {chronology!r}")
        if summary_type != "string" or not str(summary_text or "").strip():
            problems.append("payload.summary is not a nonblank string")
        if created_at is None:
            problems.append("created_at is null")
        if problems:
            raise RuntimeError(
                f"Retrograde world event {world_event_id} cannot be backfilled: "
                + "; ".join(problems)
            )
    return rows


def _resolve_recording_boundaries(
    cur: Any, legacy_rows: list[tuple[Any, ...]]
) -> dict[int, int]:
    """Recover the accepted narrative boundary for each legacy summary."""

    prologue_ids = _load_prologue_ids(cur)
    return {
        int(row[0]): _resolve_event_recording_boundary(
            cur,
            event_ref=str(row[8] or ""),
            prologue_ids=prologue_ids,
            artifact=f"legacy summary {int(row[0])}",
        )
        for row in legacy_rows
    }


def _resolve_backfill_recording_boundaries(
    cur: Any, backfill_rows: list[tuple[Any, ...]]
) -> dict[int, int]:
    """Recover recording boundaries for world events with no legacy chunk."""

    prologue_ids = _load_prologue_ids(cur)
    return {
        int(row[0]): _resolve_event_recording_boundary(
            cur,
            event_ref=str(row[1]),
            prologue_ids=prologue_ids,
            artifact=f"Retrograde world event {int(row[0])}",
        )
        for row in backfill_rows
    }


def _load_prologue_ids(cur: Any) -> list[int]:
    cur.execute(
        """
        SELECT id
        FROM narrative_chunks
        WHERE authorial_directives @> %s::jsonb
        ORDER BY id
        """,
        (json.dumps([RETROGRADE_PROLOGUE_MARKER]),),
    )
    return [int(row[0]) for row in cur.fetchall()]


def _resolve_event_recording_boundary(
    cur: Any,
    *,
    event_ref: str,
    prologue_ids: list[int],
    artifact: str,
) -> int:
    """Use durable runtime job state, or the single wizard prologue anchor."""

    match = MATURATION_EVENT_REF.match(event_ref)
    if match is None:
        if event_ref.startswith("maturation_job_"):
            raise RuntimeError(
                f"{artifact} has malformed maturation event ref {event_ref!r}"
            )
        if len(prologue_ids) != 1:
            raise RuntimeError(
                f"{artifact} requires exactly one prologue anchor; "
                f"found {prologue_ids}"
            )
        return prologue_ids[0]

    job_id = int(match.group("job_id"))
    cur.execute(
        """
        SELECT j.requesting_chunk_id, nc.id
        FROM orrery_maturation_jobs AS j
        LEFT JOIN narrative_chunks AS nc ON nc.id = j.requesting_chunk_id
        WHERE j.id = %s
        """,
        (job_id,),
    )
    job_row = cur.fetchone()
    if job_row is None:
        raise RuntimeError(
            f"{artifact} names missing maturation job {job_id} in "
            f"event ref {event_ref!r}"
        )
    requesting_chunk_id = int(job_row[0])
    if job_row[1] is None:
        raise RuntimeError(
            f"{artifact} names maturation job {job_id}, whose requesting "
            f"chunk {requesting_chunk_id} does not exist"
        )
    return requesting_chunk_id


def _require_embedding_stamp_coverage(
    cur: Any,
    legacy_rows: list[tuple[Any, ...]],
    embedding_tables: Iterable[tuple[str, int]],
) -> None:
    """Reject legacy rows that claim embedding success without any vector."""

    stamped_ids = {int(row[0]) for row in legacy_rows if row[5] is not None}
    if not stamped_ids:
        return

    covered_ids: set[int] = set()
    for table_name, _dimensions in embedding_tables:
        cur.execute(
            sql.SQL("SELECT DISTINCT chunk_id FROM {} WHERE chunk_id = ANY(%s)").format(
                sql.Identifier(table_name)
            ),
            (sorted(stamped_ids),),
        )
        covered_ids.update(int(row[0]) for row in cur.fetchall())

    missing = sorted(stamped_ids - covered_ids)
    if missing:
        raise RuntimeError(
            "Legacy Retrograde summaries have non-null embedding stamps but "
            f"no vector rows to migrate: {missing}"
        )


def _validate_narrative_references(
    cur: Any,
    legacy_ids: list[int],
    embedding_tables: Iterable[tuple[str, int]],
) -> None:
    if not legacy_ids:
        return
    allowed_cascades = {("chunk_metadata", "chunk_id")}
    allowed_cascades.update((name, "chunk_id") for name, _ in embedding_tables)
    cur.execute(
        """
        SELECT
            child.relname AS child_table,
            child_column.attname AS child_column,
            c.conname,
            c.confdeltype
        FROM pg_constraint AS c
        JOIN pg_class AS child ON child.oid = c.conrelid
        JOIN pg_namespace AS child_ns ON child_ns.oid = child.relnamespace
        JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS child_key(attnum, pos)
          ON true
        JOIN LATERAL unnest(c.confkey) WITH ORDINALITY AS parent_key(attnum, pos)
          ON parent_key.pos = child_key.pos
        JOIN pg_attribute AS child_column
          ON child_column.attrelid = c.conrelid
         AND child_column.attnum = child_key.attnum
        JOIN pg_attribute AS parent_column
          ON parent_column.attrelid = c.confrelid
         AND parent_column.attnum = parent_key.attnum
        WHERE c.contype = 'f'
          AND c.confrelid = 'public.narrative_chunks'::regclass
          AND child_ns.nspname = 'public'
          AND parent_column.attname = 'id'
          AND array_length(c.conkey, 1) = 1
        ORDER BY child.relname, child_column.attname
        """
    )
    for table_name, column_name, constraint_name, delete_action in cur.fetchall():
        identity = (str(table_name), str(column_name))
        cur.execute(
            sql.SQL("SELECT count(*) FROM {} WHERE {} = ANY(%s)").format(
                sql.Identifier(str(table_name)),
                sql.Identifier(str(column_name)),
            ),
            (legacy_ids,),
        )
        reference_count = int(cur.fetchone()[0])
        if not reference_count:
            continue
        if identity not in allowed_cascades or delete_action != "c":
            raise RuntimeError(
                "Legacy Retrograde summaries have an unexpected narrative "
                f"reference: {table_name}.{column_name} via {constraint_name} "
                f"(rows={reference_count}, delete_action={delete_action!r})"
            )


def _create_summary_table(cur: Any, *, identity_start: int) -> None:
    cur.execute(
        f"""
        CREATE TABLE retrograde_summaries (
            id bigint GENERATED BY DEFAULT AS IDENTITY
                (START WITH {identity_start}) PRIMARY KEY,
            world_event_id bigint NOT NULL UNIQUE
                REFERENCES world_events(id) ON DELETE CASCADE,
            recorded_at_chunk_id bigint NOT NULL
                REFERENCES narrative_chunks(id) ON DELETE RESTRICT,
            chronology text NOT NULL
                CHECK (chronology IN ('deep_past', 'recent_past', 'opening_pressure')),
            summary_text text NOT NULL CHECK (btrim(summary_text) <> ''),
            embedding_generated_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX ix_retrograde_summaries_recorded_at
            ON retrograde_summaries (recorded_at_chunk_id, id);
        CREATE INDEX ix_retrograde_summaries_chronology
            ON retrograde_summaries (chronology, id);
        CREATE INDEX ix_retrograde_summaries_text
            ON retrograde_summaries
            USING gin (to_tsvector('english', summary_text));

        COMMENT ON TABLE retrograde_summaries IS
            'Generated Retrograde event prose. Separate from narrative_chunks '
            'so simulated history does not advance played-story continuity.';
        COMMENT ON COLUMN retrograde_summaries.recorded_at_chunk_id IS
            'Accepted narrative boundary at which this generated history was '
            'recorded. Wizard history uses the synthetic prologue anchor.';
        """
    )


def _create_summary_embedding_table(
    cur: Any, source_table_name: str, dimensions: int
) -> None:
    source_match = SOURCE_EMBEDDING_TABLE.fullmatch(source_table_name)
    if source_match is None or int(source_match.group("dimensions")) != dimensions:
        raise AssertionError("source embedding table was not catalog-validated")
    target_table_name = _target_embedding_table(dimensions)
    if TARGET_EMBEDDING_TABLE.fullmatch(target_table_name) is None:
        raise AssertionError("generated target embedding table name is invalid")
    cur.execute(
        sql.SQL(
            """
            CREATE TABLE {} (
                summary_id bigint NOT NULL
                    REFERENCES retrograde_summaries(id) ON DELETE CASCADE,
                model text NOT NULL,
                embedding vector({}) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (summary_id, model)
            )
            """
        ).format(sql.Identifier(target_table_name), sql.Literal(dimensions))
    )
    cur.execute(
        sql.SQL("CREATE INDEX {} ON {} (model)").format(
            sql.Identifier(f"{target_table_name}_model_idx"),
            sql.Identifier(target_table_name),
        )
    )


def _copy_summaries(
    cur: Any,
    legacy_rows: list[tuple[Any, ...]],
    recording_boundaries: dict[int, int],
) -> None:
    for row in legacy_rows:
        summary_id = int(row[0])
        cur.execute(
            """
            INSERT INTO retrograde_summaries (
                id,
                world_event_id,
                recorded_at_chunk_id,
                chronology,
                summary_text,
                embedding_generated_at,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                summary_id,
                int(row[1]),
                recording_boundaries[summary_id],
                str(row[3]),
                str(row[19]).strip(),
                row[5],
                row[6],
            ),
        )


def _copy_backfill_summaries(
    cur: Any,
    backfill_rows: list[tuple[Any, ...]],
    recording_boundaries: dict[int, int],
) -> None:
    """Insert missing event summaries with fresh dedicated identities."""

    for row in backfill_rows:
        world_event_id = int(row[0])
        cur.execute(
            """
            INSERT INTO retrograde_summaries (
                world_event_id,
                recorded_at_chunk_id,
                chronology,
                summary_text,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                world_event_id,
                recording_boundaries[world_event_id],
                str(row[2]),
                str(row[3]).strip(),
                row[4],
            ),
        )


def _copy_embeddings(
    cur: Any,
    embedding_tables: Iterable[tuple[str, int]],
    legacy_ids: list[int],
) -> dict[str, int]:
    copied: dict[str, int] = {}
    for source_table_name, dimensions in embedding_tables:
        target_table_name = _target_embedding_table(dimensions)
        cur.execute(
            sql.SQL("SELECT count(*) FROM {} WHERE chunk_id = ANY(%s)").format(
                sql.Identifier(source_table_name)
            ),
            (legacy_ids,),
        )
        expected = int(cur.fetchone()[0])
        if legacy_ids:
            cur.execute(
                sql.SQL(
                    """
                    INSERT INTO {} (summary_id, model, embedding, created_at)
                    SELECT chunk_id, model, embedding, created_at
                    FROM {}
                    WHERE chunk_id = ANY(%s)
                    ORDER BY chunk_id, model
                    """
                ).format(
                    sql.Identifier(target_table_name),
                    sql.Identifier(source_table_name),
                ),
                (legacy_ids,),
            )
        copied[target_table_name] = expected
    return copied


def _target_embedding_table(dimensions: int) -> str:
    if dimensions <= 0:
        raise ValueError(f"Embedding dimensions must be positive, got {dimensions}")
    table_name = f"retrograde_summary_embeddings_{dimensions:04d}d"
    if TARGET_EMBEDDING_TABLE.fullmatch(table_name) is None:
        raise AssertionError("generated target embedding table name is invalid")
    return table_name


def _update_maturation_manifests(cur: Any, legacy_ids: list[int]) -> None:
    cur.execute(
        """
        SELECT id, result_manifest
        FROM orrery_maturation_jobs
        WHERE result_manifest <> '{}'::jsonb
        ORDER BY id
        """
    )
    job_rows = list(cur.fetchall())
    legacy_id_set = set(legacy_ids)

    cur.execute(
        """
        SELECT
            (payload ->> 'retrograde_summary_chunk_id')::bigint,
            payload ->> 'retrograde_event_ref'
        FROM world_events
        WHERE payload ? 'retrograde_summary_chunk_id'
        ORDER BY id
        """
    )
    legacy_owner_by_summary: dict[int, int | None] = {}
    for summary_id_raw, event_ref_raw in cur.fetchall():
        summary_id = int(summary_id_raw)
        match = MATURATION_EVENT_REF.match(str(event_ref_raw or ""))
        legacy_owner_by_summary[summary_id] = (
            int(match.group("job_id")) if match is not None else None
        )

    for job_id_raw, raw_manifest in job_rows:
        job_id = int(job_id_raw)
        manifest = _rewrite_maturation_manifest(
            job_id=job_id,
            raw_manifest=raw_manifest,
            legacy_id_set=legacy_id_set,
            legacy_owner_by_summary=legacy_owner_by_summary,
        )

        cur.execute(
            """
            UPDATE orrery_maturation_jobs
            SET result_manifest = %s::jsonb,
                updated_at = now()
            WHERE id = %s
            """,
            (json.dumps(manifest), job_id),
        )

    cur.execute(
        """
        SELECT id
        FROM orrery_maturation_jobs
        WHERE result_manifest <> '{}'::jsonb
          AND result_manifest ->> 'schema_version'
              IS DISTINCT FROM %s
        LIMIT 1
        """,
        (TARGET_MANIFEST_SCHEMA_VERSION,),
    )
    stale_version = cur.fetchone()
    if stale_version is not None:
        raise RuntimeError(
            f"Maturation job {stale_version[0]} retained a non-v1 manifest"
        )
    cur.execute(
        """
        SELECT id
        FROM orrery_maturation_jobs
        WHERE result_manifest ? 'embedding_pending_chunk_ids'
        LIMIT 1
        """
    )
    remaining = cur.fetchone()
    if remaining is not None:
        raise RuntimeError(
            f"Maturation job {remaining[0]} retained the legacy pending-chunk key"
        )

    cur.execute(
        """
        SELECT j.id
        FROM orrery_maturation_jobs AS j
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE
                WHEN jsonb_typeof(
                    j.result_manifest #> '{embedding,results}'
                ) = 'array'
                THEN j.result_manifest #> '{embedding,results}'
                ELSE '[]'::jsonb
            END
        ) AS result(value)
        WHERE result.value ? 'chunk_id'
        LIMIT 1
        """
    )
    stale_result = cur.fetchone()
    if stale_result is not None:
        raise RuntimeError(
            f"Maturation job {stale_result[0]} retained a legacy chunk_id result"
        )


def _rewrite_maturation_manifest(
    *,
    job_id: int,
    raw_manifest: Any,
    legacy_id_set: set[int],
    legacy_owner_by_summary: dict[int, int | None],
) -> dict[str, Any]:
    """Strictly translate one nonempty v0 manifest to the v1 identity schema."""

    if not isinstance(raw_manifest, dict):
        raise RuntimeError(f"Maturation job {job_id} has a non-object manifest")
    manifest = dict(raw_manifest)
    version = manifest.get("schema_version")
    if version != LEGACY_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"Maturation job {job_id} has manifest schema {version!r}; "
            f"expected {LEGACY_MANIFEST_SCHEMA_VERSION!r}"
        )
    if "embedding_pending_summary_ids" in manifest:
        raise RuntimeError(
            f"Maturation job {job_id} already uses the v1 pending-summary key"
        )

    pending_ids: list[int] | None = None
    if "embedding_pending_chunk_ids" in manifest:
        raw_pending = manifest.pop("embedding_pending_chunk_ids")
        if not isinstance(raw_pending, list):
            raise RuntimeError(
                f"Maturation job {job_id} has non-array pending chunk ids"
            )
        pending_ids = [
            _strict_positive_manifest_id(
                value,
                artifact=f"Maturation job {job_id} pending chunk id",
            )
            for value in raw_pending
        ]
        if len(set(pending_ids)) != len(pending_ids):
            raise RuntimeError(
                f"Maturation job {job_id} has duplicate pending chunk ids"
            )
        unknown_pending = sorted(set(pending_ids) - legacy_id_set)
        if unknown_pending:
            raise RuntimeError(
                f"Maturation job {job_id} references unknown summary ids "
                f"{unknown_pending}"
            )
        wrong_owner = sorted(
            summary_id
            for summary_id in pending_ids
            if legacy_owner_by_summary.get(summary_id) != job_id
        )
        if wrong_owner:
            raise RuntimeError(
                f"Maturation job {job_id} references summaries owned by a "
                f"different source: {wrong_owner}"
            )
        manifest["embedding_pending_summary_ids"] = pending_ids
    elif manifest.get("persisted") is True:
        raise RuntimeError(
            f"Persisted maturation job {job_id} has no legacy pending-chunk key"
        )

    result_ids: list[int] = []
    if "embedding" in manifest:
        embedding = manifest["embedding"]
        if not isinstance(embedding, dict):
            raise RuntimeError(
                f"Maturation job {job_id} has non-object embedding audit"
            )
        embedding = dict(embedding)
        if "results" in embedding:
            raw_results = embedding["results"]
            if not isinstance(raw_results, list):
                raise RuntimeError(
                    f"Maturation job {job_id} has non-array embedding results"
                )
            rewritten_results = []
            for index, raw_result in enumerate(raw_results):
                if not isinstance(raw_result, dict):
                    raise RuntimeError(
                        f"Maturation job {job_id} embedding result {index} "
                        "is not an object"
                    )
                if "summary_id" in raw_result or "chunk_id" not in raw_result:
                    raise RuntimeError(
                        f"Maturation job {job_id} embedding result {index} "
                        "does not have the expected legacy chunk_id identity"
                    )
                summary_id = _strict_positive_manifest_id(
                    raw_result["chunk_id"],
                    artifact=(
                        f"Maturation job {job_id} embedding result {index} chunk_id"
                    ),
                )
                if summary_id not in legacy_id_set:
                    raise RuntimeError(
                        f"Maturation job {job_id} embedding result {index} "
                        f"references unknown summary id {summary_id}"
                    )
                if legacy_owner_by_summary.get(summary_id) != job_id:
                    raise RuntimeError(
                        f"Maturation job {job_id} embedding result {index} "
                        f"references summary {summary_id} owned by another source"
                    )
                rewritten = dict(raw_result)
                del rewritten["chunk_id"]
                rewritten["summary_id"] = summary_id
                rewritten_results.append(rewritten)
                result_ids.append(summary_id)
            if len(set(result_ids)) != len(result_ids):
                raise RuntimeError(
                    f"Maturation job {job_id} has duplicate embedding results"
                )
            embedding["results"] = rewritten_results
        manifest["embedding"] = embedding

    if result_ids and pending_ids is not None and set(result_ids) != set(pending_ids):
        raise RuntimeError(
            f"Maturation job {job_id} embedding results do not match its "
            "pending summary identities"
        )

    manifest["schema_version"] = TARGET_MANIFEST_SCHEMA_VERSION
    return manifest


def _strict_positive_manifest_id(value: Any, *, artifact: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"{artifact} is not a positive integer: {value!r}")
    return value


def _remove_legacy_payload_links(cur: Any, legacy_ids: list[int]) -> None:
    if not legacy_ids:
        return
    cur.execute(
        """
        UPDATE world_events
        SET payload = payload - 'retrograde_summary_chunk_id'
        WHERE (payload ->> 'retrograde_summary_chunk_id')::bigint = ANY(%s)
        """,
        (legacy_ids,),
    )
    if cur.rowcount != len(legacy_ids):
        raise RuntimeError(
            "Migration 078 payload cleanup count changed after preflight: "
            f"expected {len(legacy_ids)}, updated {cur.rowcount}"
        )


def _delete_legacy_chunks(cur: Any, legacy_ids: list[int]) -> None:
    if not legacy_ids:
        return
    cur.execute("DELETE FROM narrative_chunks WHERE id = ANY(%s)", (legacy_ids,))
    if cur.rowcount != len(legacy_ids):
        raise RuntimeError(
            "Migration 078 legacy delete count changed after preflight: "
            f"expected {len(legacy_ids)}, deleted {cur.rowcount}"
        )


def _install_legacy_write_guards(cur: Any) -> None:
    """Make pre-078 writers fail once the migration releases its locks."""

    cur.execute(
        """
        CREATE FUNCTION nexus_reject_legacy_retrograde_summary_chunk()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $guard$
        BEGIN
            IF NEW.authorial_directives
                @> '["orrery:retrograde_event_summary"]'::jsonb
            THEN
                RAISE EXCEPTION
                    'Retrograde event summaries belong in retrograde_summaries'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $guard$;

        CREATE TRIGGER trg_narrative_chunks_reject_retrograde_summary
        BEFORE INSERT OR UPDATE OF authorial_directives
        ON narrative_chunks
        FOR EACH ROW
        EXECUTE FUNCTION nexus_reject_legacy_retrograde_summary_chunk();

        CREATE FUNCTION nexus_reject_legacy_retrograde_summary_link()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $guard$
        BEGIN
            IF NEW.payload ? 'retrograde_summary_chunk_id' THEN
                RAISE EXCEPTION
                    'retrograde_summary_chunk_id is retired after migration 078'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $guard$;

        CREATE TRIGGER trg_world_events_reject_retrograde_summary_link
        BEFORE INSERT OR UPDATE OF payload
        ON world_events
        FOR EACH ROW
        EXECUTE FUNCTION nexus_reject_legacy_retrograde_summary_link();

        CREATE FUNCTION nexus_require_retrograde_maturation_manifest_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $guard$
        BEGIN
            IF NEW.result_manifest = '{}'::jsonb THEN
                RETURN NEW;
            END IF;

            IF jsonb_typeof(NEW.result_manifest) IS DISTINCT FROM 'object'
                OR NEW.result_manifest ->> 'schema_version'
                    IS DISTINCT FROM %s
            THEN
                RAISE EXCEPTION
                    'Nonempty maturation manifests must use the v1 schema '
                    'after migration 078'
                    USING ERRCODE = '23514';
            END IF;

            IF NEW.result_manifest ? 'embedding_pending_chunk_ids' THEN
                RAISE EXCEPTION
                    'embedding_pending_chunk_ids is retired after migration 078'
                    USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM jsonb_array_elements(
                    CASE
                        WHEN jsonb_typeof(
                            NEW.result_manifest #> '{embedding,results}'
                        ) = 'array'
                        THEN NEW.result_manifest #> '{embedding,results}'
                        ELSE '[]'::jsonb
                    END
                ) AS result(value)
                WHERE jsonb_typeof(result.value) = 'object'
                  AND result.value ? 'chunk_id'
            ) THEN
                RAISE EXCEPTION
                    'Maturation embedding results must use summary_id '
                    'after migration 078'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END
        $guard$;

        CREATE TRIGGER trg_orrery_maturation_jobs_require_manifest_v1
        BEFORE INSERT OR UPDATE OF result_manifest
        ON orrery_maturation_jobs
        FOR EACH ROW
        EXECUTE FUNCTION nexus_require_retrograde_maturation_manifest_v1();
        """,
        (TARGET_MANIFEST_SCHEMA_VERSION,),
    )


def _validate_postconditions(
    cur: Any,
    *,
    expected_summary_count: int,
    expected_embedding_counts: dict[str, int],
) -> None:
    cur.execute("SELECT count(*) FROM retrograde_summaries")
    actual_summary_count = int(cur.fetchone()[0])
    if actual_summary_count != expected_summary_count:
        raise RuntimeError(
            "Migration 078 summary copy count mismatch: "
            f"expected {expected_summary_count}, copied {actual_summary_count}"
        )

    for table_name, expected in expected_embedding_counts.items():
        cur.execute(
            sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table_name))
        )
        actual = int(cur.fetchone()[0])
        if actual != expected:
            raise RuntimeError(
                f"Migration 078 embedding copy mismatch for {table_name}: "
                f"expected {expected}, copied {actual}"
            )

    cur.execute(
        """
        SELECT count(*)
        FROM narrative_chunks
        WHERE authorial_directives @> %s::jsonb
        """,
        (json.dumps([RETROGRADE_SUMMARY_MARKER]),),
    )
    remaining_chunks = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT count(*)
        FROM world_events
        WHERE payload ? 'retrograde_summary_chunk_id'
        """
    )
    remaining_links = int(cur.fetchone()[0])
    if remaining_chunks or remaining_links:
        raise RuntimeError(
            "Migration 078 left legacy summary artifacts: "
            f"chunks={remaining_chunks}, payload_links={remaining_links}"
        )

    cur.execute(
        """
        SELECT count(*)
        FROM world_events AS we
        LEFT JOIN retrograde_summaries AS rs ON rs.world_event_id = we.id
        WHERE we.source = 'retrograde'::event_source_kind
          AND rs.id IS NULL
        """
    )
    missing_summaries = int(cur.fetchone()[0])
    if missing_summaries:
        raise RuntimeError(
            "Migration 078 left canonical Retrograde world events without "
            f"dedicated summaries: {missing_summaries}"
        )

    cur.execute(
        """
        SELECT count(*)
        FROM pg_trigger AS t
        JOIN pg_class AS c ON c.oid = t.tgrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND (c.relname, t.tgname) IN (
            (
                'narrative_chunks',
                'trg_narrative_chunks_reject_retrograde_summary'
            ),
            (
                'world_events',
                'trg_world_events_reject_retrograde_summary_link'
            ),
            (
                'orrery_maturation_jobs',
                'trg_orrery_maturation_jobs_require_manifest_v1'
            )
        )
          AND NOT t.tgisinternal
          AND t.tgenabled <> 'D'
        """
    )
    guard_count = int(cur.fetchone()[0])
    if guard_count != 3:
        raise RuntimeError(
            "Migration 078 did not install all legacy write guards: "
            f"found {guard_count}"
        )
