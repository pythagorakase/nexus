"""Seed Orrery concealment, surveillance, and contact-risk vocabulary."""

from __future__ import annotations

from typing import Sequence

from psycopg2.extensions import connection


# (tag, category, description)
DURABLE_TAGS: Sequence[tuple[str, str, str]] = (
    (
        "cover_identity",
        "orrery_cover",
        "Character maintains a specific cover identity that needs routine upkeep.",
    ),
    (
        "undercover",
        "orrery_cover",
        "Character is operating under an assumed role or hidden affiliation.",
    ),
    (
        "deep_cover",
        "orrery_cover",
        "Character's assumed identity is load-bearing enough that direct contact "
        "can become a major story beat.",
    ),
    (
        "public_role",
        "orrery_cover",
        "Character has a visible public role whose routine can sustain cover.",
    ),
    (
        "operative",
        "profession_lite",
        "Character performs covert, paramilitary, intelligence, or field work.",
    ),
    (
        "presumed_dead",
        "orrery_concealment",
        "Character is broadly believed dead or unavailable in a way that makes "
        "direct contact dramatically loaded.",
    ),
    (
        "presumed_dead_by_some",
        "orrery_concealment",
        "Some important parties believe the character is dead or gone.",
    ),
    (
        "long_hidden",
        "orrery_concealment",
        "Character has remained hidden for a long stretch of narrative time.",
    ),
    (
        "long_absent",
        "orrery_concealment",
        "Character has been away long enough that contact carries accumulated "
        "dramatic weight.",
    ),
    (
        "long_estranged",
        "relationship_risk",
        "A relationship has been estranged long enough that ordinary warmth is "
        "not safe to infer from the relationship type.",
    ),
    (
        "hidden_identity",
        "orrery_concealment",
        "Character's current identity or survival depends on staying unrevealed.",
    ),
    (
        "wanted",
        "orrery_concealment",
        "Character is sought by authorities, enemies, or other organized forces.",
    ),
    (
        "signal_operator",
        "capacity",
        "Character can monitor, intercept, or manipulate communication signals.",
    ),
    (
        "surveillance_capable",
        "capacity",
        "Character can perform competent observation, tailing, or remote watching.",
    ),
    (
        "safehouse_operator",
        "profession_lite",
        "Character knows how to provision, sanitize, or rotate safe locations.",
    ),
)


# (tag, category, clearance_kind, clear_on_json, description)
EPHEMERAL_TAGS: Sequence[tuple[str, str, str, str | None, str]] = (
    (
        "contained",
        "state",
        "semantic",
        '{"description": "cleared when the containment condition ends"}',
        "Entity is physically, socially, or operationally contained.",
    ),
    (
        "immobile",
        "state",
        "semantic",
        '{"description": "cleared when the entity regains meaningful mobility"}',
        "Entity cannot currently move enough for public-flow packages to apply.",
    ),
)


# (tag, description)
PLACE_AFFORDANCE_TAGS: Sequence[tuple[str, str]] = (
    (
        "street",
        "Place supports ordinary public movement through streets, roads, or paths.",
    ),
)


# (event_type, category, severity, description)
EVENT_TYPES: Sequence[tuple[str, str, str, str]] = (
    (
        "hideout_maintained",
        "concealment",
        "minor",
        "Actor preserves a steady-state hidden life, safehouse, or route.",
    ),
    (
        "signal_exposure_reduced",
        "concealment",
        "minor",
        "Actor reduces their observable communications or digital footprint.",
    ),
    (
        "counter_surveillance_sweep",
        "concealment",
        "minor",
        "Actor checks whether their hiding pattern has become visible.",
    ),
    (
        "surveillance_performed",
        "intelligence",
        "minor",
        "Actor watches, monitors, or keeps tabs on a target without contact.",
    ),
    (
        "intel_reviewed",
        "intelligence",
        "minor",
        "Actor reviews accumulated intelligence instead of gathering new contact.",
    ),
    (
        "contact_deferred",
        "interpersonal",
        "minor",
        "Actor considers relational contact but deliberately withholds it.",
    ),
)


def run(conn: connection) -> None:
    """Apply concealment/surveillance package vocabulary."""

    _seed_durable_tags(conn)
    _seed_ephemeral_tags(conn)
    _seed_place_affordance_tags(conn)
    _seed_event_types(conn)


def _seed_durable_tags(conn: connection) -> None:
    with conn.cursor() as cur:
        for tag, category, description in DURABLE_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, description
                ) VALUES (
                    %s, %s, FALSE,
                    NULL, NULL,
                    NULL, %s
                )
                ON CONFLICT (tag) DO UPDATE SET
                    category = EXCLUDED.category,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    reapplication_policy = EXCLUDED.reapplication_policy,
                    clear_on = EXCLUDED.clear_on,
                    description = EXCLUDED.description
                """,
                (tag, category, description),
            )
    conn.commit()


def _seed_ephemeral_tags(conn: connection) -> None:
    with conn.cursor() as cur:
        for tag, category, clearance_kind, clear_on_json, description in EPHEMERAL_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, description
                ) VALUES (
                    %s, %s, TRUE,
                    %s::entity_tag_clearance_kind,
                    'extend_expiry'::entity_tag_reapplication_policy,
                    %s::jsonb, %s
                )
                ON CONFLICT (tag) DO UPDATE SET
                    category = EXCLUDED.category,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    reapplication_policy = EXCLUDED.reapplication_policy,
                    clear_on = EXCLUDED.clear_on,
                    description = EXCLUDED.description
                """,
                (tag, category, clearance_kind, clear_on_json, description),
            )
    conn.commit()


def _seed_place_affordance_tags(conn: connection) -> None:
    with conn.cursor() as cur:
        for tag, description in PLACE_AFFORDANCE_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, description
                ) VALUES (
                    %s, 'place_affordance', FALSE,
                    NULL, NULL,
                    NULL, %s
                )
                ON CONFLICT (tag) DO UPDATE SET
                    category = EXCLUDED.category,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    reapplication_policy = EXCLUDED.reapplication_policy,
                    clear_on = EXCLUDED.clear_on,
                    description = EXCLUDED.description
                """,
                (tag, description),
            )
    conn.commit()


def _seed_event_types(conn: connection) -> None:
    with conn.cursor() as cur:
        for event_type, category, severity, description in EVENT_TYPES:
            cur.execute(
                """
                INSERT INTO event_types (
                    type, category, severity, description
                ) VALUES (
                    %s, %s, %s::event_severity_kind, %s
                )
                ON CONFLICT (type) DO NOTHING
                """,
                (event_type, category, severity, description),
            )
    conn.commit()
