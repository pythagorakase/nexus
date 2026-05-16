"""Seed vocabulary for the Orrery package-library expansion.

Adds the tags, event_types, and relationship_type enum values referenced by
the EXTRACT_VENGEANCE, PROTECT_KIN, and CULTIVATE_INFORMANT templates appended
to nexus/agents/orrery/templates.py in the same change. Migration 023 created
the empty registries; this migration seeds them with the minimum vocabulary
needed for the new templates to fire without violating the Vocabulary Growth
Contract (resolver-sourced unknowns fail loudly — templates must register
their vocabulary before use).

Scope is intentionally narrow: only the vocabulary the three new templates
reference. The existing built-in templates (EVADE_PURSUERS, HONOR_DEBT,
PURSUE_GHOST_LEAD, MAINTAIN_COVER) reference further tags and event_types
that are still unseeded; those become PR 3's seeding task because PR 3
(CommitOrreryTick) is the first slice that actually attempts canonical
writes against the registries.
"""

from __future__ import annotations

from typing import Sequence

from psycopg2 import sql


NEW_RELATIONSHIP_TYPES: Sequence[str] = (
    "chosen_kin",
    "comrade",
    "handler",
    "asset",
)


# (tag, category, description)
DURABLE_TAGS: Sequence[tuple[str, str, str]] = (
    (
        "vendetta_holder",
        "disposition",
        "Identity tag — characters whose narrative arc includes "
        "pursuing grievances. Priority hint for EXTRACT_VENGEANCE.",
    ),
    (
        "informant_handler",
        "profession_lite",
        "Identity tag — characters who run informant networks. "
        "Eligibility filter for CULTIVATE_INFORMANT.",
    ),
    (
        "violent_history",
        "disposition",
        "Identity tag — characters with a track record of physical "
        "violence. Branch condition for EXTRACT_VENGEANCE's direct-strike "
        "branch.",
    ),
)


# (tag, category, clearance_kind, clear_on_json, description)
EPHEMERAL_TAGS: Sequence[tuple[str, str, str, str | None, str]] = (
    (
        "grudge_active",
        "state",
        "event",
        '{"event_types": ["retaliation_executed"]}',
        "Ephemeral — actor was the target of a wronging event significant "
        "enough to produce a vendetta. Cleared by retaliation_executed.",
    ),
    (
        "wounded",
        "state",
        "semantic",
        None,
        "Ephemeral — entity has a recent physical injury. Cleared by "
        "post-commit semantic evaluation of narrative recovery indicators.",
    ),
    (
        "recently_violent",
        "state",
        "semantic",
        None,
        "Ephemeral — actor has executed violence in the recent past. "
        "Cleared by semantic decay (narrative distance from the event).",
    ),
    (
        "recently_protective",
        "state",
        "semantic",
        None,
        "Ephemeral — actor has intervened protectively on a kin's behalf "
        "in the recent past. Cleared by semantic decay.",
    ),
    (
        "reputation_compromised",
        "state",
        "semantic",
        None,
        "Ephemeral — target has been the subject of a recent reputation "
        "attack. Cleared by semantic evaluation of restoration efforts or "
        "narrative distance.",
    ),
    (
        "distressed",
        "state",
        "semantic",
        None,
        "Ephemeral — actor is in acute emotional distress, typically "
        "from inability to act on behalf of endangered kin. Cleared by "
        "semantic evaluation of resolution.",
    ),
    (
        "intelligence_asset_active",
        "state",
        "semantic",
        None,
        "Ephemeral — actor is actively running an intelligence asset who "
        "is producing material intel. Cleared by semantic evaluation of "
        "asset burn-out, reassignment, or termination.",
    ),
)


# (event_type, category, severity, description)
NEW_EVENT_TYPES: Sequence[tuple[str, str, str, str]] = (
    (
        "retaliation_executed",
        "interpersonal",
        "major",
        "Actor moved against a grudge target with intent to harm. "
        "Clears grudge_active.",
    ),
    (
        "retaliation_attempted",
        "interpersonal",
        "moderate",
        "Actor attempted retaliation against a grudge target but did not "
        "complete or escalate (surveillance, reputation attack, abort). "
        "Grudge remains active.",
    ),
    (
        "protective_intervention",
        "interpersonal",
        "moderate",
        "Actor moved to shield a relational kin from active threat or " "ongoing harm.",
    ),
    (
        "informant_contact",
        "intelligence",
        "minor",
        "Routine handler/asset meeting, intelligence trade-craft "
        "maintenance. Resets cultivation cooldown.",
    ),
    (
        "intel_acquired",
        "intelligence",
        "moderate",
        "Material intelligence obtained from a cultivated informant " "source.",
    ),
    (
        "threat_issued",
        "interpersonal",
        "moderate",
        "An explicit threat was directed at the target entity. Surfacing "
        "signal for protective behavior in those who hold relational ties "
        "to the target.",
    ),
)


def run(conn) -> None:
    """Apply the package-library vocabulary migration."""

    _extend_relationship_type_enum(conn)
    _seed_durable_tags(conn)
    _seed_ephemeral_tags(conn)
    _seed_event_types(conn)


def _enum_value_exists(conn, type_name: str, value: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM pg_enum
            WHERE enumtypid = %s::regtype
              AND enumlabel = %s
            """,
            (type_name, value),
        )
        return cur.fetchone() is not None


def _extend_relationship_type_enum(conn) -> None:
    """Add relationship_type enum values needed by the new templates.

    ALTER TYPE ... ADD VALUE cannot run inside a multi-statement transaction
    block on PostgreSQL prior to 12. Even on 12+, the new value is only
    usable after the transaction commits. We commit after each ADD VALUE
    so the migration's later statements can reference them safely if needed.
    """

    for value in NEW_RELATIONSHIP_TYPES:
        if _enum_value_exists(conn, "relationship_type", value):
            continue
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER TYPE relationship_type ADD VALUE {}").format(
                    sql.Literal(value)
                )
            )
        conn.commit()


def _seed_durable_tags(conn) -> None:
    """Insert durable identity tags. Idempotent via ON CONFLICT (tag)."""

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
                ON CONFLICT (tag) DO NOTHING
                """,
                (tag, category, description),
            )
    conn.commit()


def _seed_ephemeral_tags(conn) -> None:
    """Insert ephemeral state tags with clearance kinds. Idempotent."""

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
                ON CONFLICT (tag) DO NOTHING
                """,
                (tag, category, clearance_kind, clear_on_json, description),
            )
    conn.commit()


def _seed_event_types(conn) -> None:
    """Insert new event_types referenced by the new templates. Idempotent."""

    with conn.cursor() as cur:
        for event_type, category, severity, description in NEW_EVENT_TYPES:
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
