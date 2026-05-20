"""Add the entity_pair_tags substrate for multi-entity (relational) tags.

Single-entity tags live in `entity_tags` (and their vocabulary in `tags`); this
migration introduces the parallel `entity_pair_tags` table for directed binary
relations between entities, with their vocabulary in a new `pair_tags`
registry.

Seeds the 12 multi-entity relations settled in
`temp/orrery/orrery_vocabulary.md` ("Multi-Entity Tags — Settled, 12 total"):

- Place-bound (6): `knows_location`, `can_access`, `claims`, `resides_at`,
  `operates_from`, `originates_from`
- Character/faction relations (6): `pursuing`, `handles`, `obligation`,
  `authority_over`, `protects`, `mentors`

`pursuing` is the only seeded ephemeral relation; the rest are durable.

The companion writer lives in `nexus.agents.orrery.tag_writer`
(`apply_pair_tag_bestowal`, `clear_pair_tag`). Read predicates
(`has_pair_tag`, `inbound_pair_tag_subjects`, `outbound_pair_tag_objects`) and
the binding-composer extension will be added in a follow-up PR.

Design rationale: scope-bound status, fame as detection radius, package
self-awareness (issue #282) all depend on this substrate.
"""

from __future__ import annotations

from typing import Sequence

from psycopg2.extensions import connection


# (tag, subject_kinds, object_kinds, is_ephemeral, description)
PAIR_TAG_SEED: Sequence[tuple[str, list[str], list[str], bool, str]] = (
    # Place-bound (durable)
    (
        "knows_location",
        ["character"],
        ["place"],
        False,
        "Subject knows of the place's existence and how to find it.",
    ),
    (
        "can_access",
        ["character", "faction"],
        ["place"],
        False,
        "Subject has permission to enter the place (direct individual or group-mediated).",
    ),
    (
        "claims",
        ["faction"],
        ["place"],
        False,
        "Subject (faction) asserts a territorial claim on the place; contestation emerges from row cardinality.",
    ),
    (
        "resides_at",
        ["character"],
        ["place"],
        False,
        "Subject's habitual residence. Multi-residence is supported via multiple rows.",
    ),
    (
        "operates_from",
        ["faction"],
        ["place"],
        False,
        "Faction's operational base. Distinct from `claims` — claim is territorial, operates_from is functional.",
    ),
    (
        "originates_from",
        ["character"],
        ["place"],
        False,
        "Character's origin or hometown.",
    ),
    # Character / faction relations
    (
        "pursuing",
        ["character", "faction"],
        ["character"],
        True,
        "Subject is actively hunting the target. Ephemeral; also confers narrow targeted detection sensitivity for that target (see issue #282).",
    ),
    (
        "handles",
        ["character"],
        ["character"],
        False,
        "Subject is the operational handler of the target (covert / espionage / criminal flavor).",
    ),
    (
        "obligation",
        ["character", "faction"],
        ["character", "faction"],
        False,
        "Subject owes a debt / oath / loyalty to the target. Kind inferable from establishing event.",
    ),
    (
        "authority_over",
        ["character", "faction"],
        ["character", "faction"],
        False,
        "Subject holds institutional or positional power over the target.",
    ),
    (
        "protects",
        ["character", "faction"],
        ["character"],
        False,
        "Subject is in an active protective relationship with the target. Durable.",
    ),
    (
        "mentors",
        ["character"],
        ["character"],
        False,
        "Subject teaches or trains the target.",
    ),
)


def run(conn: connection) -> None:
    """Create the entity_pair_tags substrate and seed the 12 settled relations."""

    with conn.cursor() as cur:
        # Registry of relation types (analog of `tags` but with kind validation columns)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pair_tags (
                id                   bigserial PRIMARY KEY,
                tag                  text UNIQUE NOT NULL,
                subject_kinds        text[] NOT NULL,
                object_kinds         text[] NOT NULL,
                is_ephemeral         boolean NOT NULL DEFAULT FALSE,
                clearance_kind       entity_tag_clearance_kind,
                reapplication_policy entity_tag_reapplication_policy,
                clear_on             jsonb,
                deprecated           boolean NOT NULL DEFAULT FALSE,
                description          text,
                created_at           timestamptz NOT NULL DEFAULT now(),
                CHECK (is_ephemeral = (clearance_kind IS NOT NULL)),
                CHECK (array_length(subject_kinds, 1) >= 1),
                CHECK (array_length(object_kinds, 1) >= 1),
                CHECK (btrim(tag) <> '')
            )
            """
        )

        cur.execute(
            """
            COMMENT ON TABLE pair_tags IS
                'Registry of multi-entity (directed binary) relation types. The vocabulary for entity_pair_tags. Analog of `tags` for edges between entities.';
            """
        )
        cur.execute(
            "COMMENT ON COLUMN pair_tags.tag IS "
            "'Relation name (snake_case). May embed a level via the colon convention, e.g. `status:senior`.'"
        )
        cur.execute(
            "COMMENT ON COLUMN pair_tags.subject_kinds IS "
            "'Allowed entity_kind values for the subject (source) of this relation. Polymorphism (e.g. character|faction) is expressed via array membership.'"
        )
        cur.execute(
            "COMMENT ON COLUMN pair_tags.object_kinds IS "
            "'Allowed entity_kind values for the object (target) of this relation.'"
        )
        cur.execute(
            "COMMENT ON COLUMN pair_tags.is_ephemeral IS "
            "'TRUE for relations that get cleared by world events (e.g., `pursuing`); FALSE for durable relations.'"
        )

        # Application table — actual edges between entities
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_pair_tags (
                id                    bigserial PRIMARY KEY,
                subject_entity_id     bigint NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                object_entity_id      bigint NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                pair_tag_id           bigint NOT NULL REFERENCES pair_tags(id),
                applied_at            timestamptz NOT NULL DEFAULT now(),
                applied_at_world_time timestamptz,
                source_kind           entity_tag_source_kind NOT NULL,
                cleared_at            timestamptz,
                clear_on_override     jsonb,
                template_id           text,
                CHECK (subject_entity_id <> object_entity_id),
                CONSTRAINT entity_pair_tags_unique_event UNIQUE
                    (subject_entity_id, object_entity_id, pair_tag_id, applied_at)
            )
            """
        )

        cur.execute(
            """
            COMMENT ON TABLE entity_pair_tags IS
                'Directed binary tag (relation) edge from subject to object. The application table for multi-entity tags; analog of entity_tags.';
            """
        )
        cur.execute(
            "COMMENT ON COLUMN entity_pair_tags.subject_entity_id IS "
            "'The source endpoint of the directed relation (FK entities).'"
        )
        cur.execute(
            "COMMENT ON COLUMN entity_pair_tags.object_entity_id IS "
            "'The target endpoint of the directed relation (FK entities). Must differ from subject_entity_id.'"
        )
        cur.execute(
            "COMMENT ON COLUMN entity_pair_tags.pair_tag_id IS "
            "'FK to pair_tags — the relation type.'"
        )
        cur.execute(
            "COMMENT ON COLUMN entity_pair_tags.cleared_at IS "
            "'When set, the relation is no longer active (analogous to entity_tags.cleared_at).'"
        )

        # Indexes
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ix_entity_pair_tags_current
                ON entity_pair_tags (subject_entity_id, object_entity_id, pair_tag_id)
                WHERE cleared_at IS NULL
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_entity_pair_tags_subject_current
                ON entity_pair_tags (subject_entity_id, pair_tag_id)
                WHERE cleared_at IS NULL
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_entity_pair_tags_object_current
                ON entity_pair_tags (object_entity_id, pair_tag_id)
                WHERE cleared_at IS NULL
            """
        )

        # Seed the 12 settled multi-entity relations
        for tag, subject_kinds, object_kinds, is_ephemeral, description in PAIR_TAG_SEED:
            clearance_kind = "semantic" if is_ephemeral else None
            cur.execute(
                """
                INSERT INTO pair_tags (
                    tag, subject_kinds, object_kinds,
                    is_ephemeral, clearance_kind, description
                ) VALUES (
                    %s, %s, %s, %s, %s::entity_tag_clearance_kind, %s
                )
                ON CONFLICT (tag) DO UPDATE SET
                    subject_kinds = EXCLUDED.subject_kinds,
                    object_kinds  = EXCLUDED.object_kinds,
                    is_ephemeral  = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    description   = EXCLUDED.description
                """,
                (
                    tag,
                    subject_kinds,
                    object_kinds,
                    is_ephemeral,
                    clearance_kind,
                    description,
                ),
            )

    conn.commit()
