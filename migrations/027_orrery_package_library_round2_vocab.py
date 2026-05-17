"""Seed vocabulary for the Orrery package-library round 2 expansion.

Adds the tags, event_types, and relationship_type enum values referenced
by the eight new templates appended to nexus/agents/orrery/templates.py
in the same change:

  - Section A (universal care): TEND_WOUNDED, MOURN_LOSS, KEEP_VIGIL
  - Section B (maintenance of self): TEND_CRAFT
  - Section C (contact quartet): WARN_ALLY, CHECK_ON_DEPENDENT,
    REACH_OUT_TO_KIN, CONSULT_RIVAL

Vocabulary is intentionally broad — particularly TEND_CRAFT's role tags
(combat / arcane / engineering / performing / athletic / commerce /
domestic / scholarly archetypes). ChatClaude's contribution flagged that
many role tags are nominally distinct but functionally identical for
gate-discrimination purposes (engineer / mechanic / tinkerer / hacker /
artificer all fire the same TEND_CRAFT branch via has_any_tag). I kept
the full set so storyteller-side tagging stays expressive; collapsing
to canonical names is a follow-up consideration if observed vocabulary
volume becomes unwieldy.

Two ephemerals seeded with `clear_on` pointing at events that don't
yet have a resolver-side emitter — `dying` clears on `wound_healed` or
`death_recorded`; `unconscious` clears on `regained_consciousness` or
`death_recorded`. These external events are "probably authored externally"
per ChatClaude's note; the ephemerals are seeded with proper clearance
predicates so when those events eventually fire (from CommitOrreryTick
or future world-state systems), the framework honors the clearance.

`captive` is seeded as ephemeral rather than durable: being captive is
a condition that changes (escape, freed, death) rather than an identity.
Diverges from ChatClaude's table listing; KEEP_VIGIL's gate is updated
to use has_ephemeral instead of has_tag accordingly.
"""

from __future__ import annotations

from typing import Sequence

from psycopg2 import sql


# Relationship-type enum extensions. The asymmetric pair captor↔captive
# captures the gaoler/prisoner dynamic KEEP_VIGIL models; ward↔guardian
# captures formal caretaking; mentor and patron are common dependent-
# relationship roles for CHECK_ON_DEPENDENT.
NEW_RELATIONSHIP_TYPES: Sequence[str] = (
    "ward",
    "guardian",
    "captor",
    "mentor",
    "patron",
)


# (tag, category, description)
DURABLE_TAGS: Sequence[tuple[str, str, str]] = (
    # Healing capacities (TEND_WOUNDED branches)
    (
        "magical_healing",
        "capacity",
        "Can channel restorative power. Highest-magnitude TEND_WOUNDED branch.",
    ),
    (
        "surgical_training",
        "capacity",
        "Has formal training in surgery. Mid-magnitude TEND_WOUNDED branch.",
    ),
    (
        "medical_skill",
        "capacity",
        "Has general medical skill. Mid-magnitude TEND_WOUNDED branch.",
    ),
    (
        "first_aid_trained",
        "capacity",
        "Knows first-aid basics. Low-magnitude TEND_WOUNDED branch.",
    ),
    # Dispositions (KEEP_VIGIL contemplative branch)
    (
        "devout",
        "disposition",
        "Holds active religious or spiritual practice.",
    ),
    (
        "contemplative",
        "disposition",
        "Inclined toward meditative or reflective practice.",
    ),
    # Roles for KEEP_VIGIL contemplative branch, also MOURN_LOSS
    (
        "ritual_practitioner",
        "role",
        "Performs structured ritual work in any tradition.",
    ),
    # Combat roles (TEND_CRAFT weapon-maintenance branch)
    (
        "combat_trained",
        "capacity",
        "General combat training. Used by TEND_CRAFT weapon branch.",
    ),
    (
        "soldier",
        "role",
        "Military or paramilitary role.",
    ),
    (
        "warrior",
        "role",
        "Combatant identity outside formal military structures.",
    ),
    (
        "fighter",
        "role",
        "Combatant identity, generic.",
    ),
    # Arcane roles (TEND_CRAFT arcane branch, MOURN_LOSS)
    (
        "arcane_caster",
        "capacity",
        "Practices magic of any tradition.",
    ),
    # Engineering / tinkering roles (TEND_CRAFT equipment branch)
    (
        "engineer",
        "role",
        "Designs and builds technical systems.",
    ),
    (
        "mechanic",
        "role",
        "Repairs and maintains mechanical or vehicular systems.",
    ),
    (
        "tinkerer",
        "role",
        "Inventive hands-on craft work without formal training.",
    ),
    (
        "hacker",
        "role",
        "Manipulates information systems.",
    ),
    (
        "artificer",
        "role",
        "Craft work that fuses technical and arcane domains.",
    ),
    # Creative roles (TEND_CRAFT practice branch, MOURN_LOSS)
    (
        "musician",
        "role",
        "Practices musical performance or composition.",
    ),
    (
        "dancer",
        "role",
        "Practices dance as discipline.",
    ),
    (
        "performer",
        "role",
        "Stage or street performance, generic.",
    ),
    (
        "artist",
        "role",
        "Visual or plastic art practice.",
    ),
    (
        "writer",
        "role",
        "Practices writing.",
    ),
    (
        "artisan",
        "role",
        "Skilled handcraft, generic.",
    ),
    # Athletic / physical roles (TEND_CRAFT conditioning branch)
    (
        "athlete",
        "role",
        "Practices physical conditioning as discipline.",
    ),
    (
        "martial_artist",
        "role",
        "Trains in a codified martial art.",
    ),
    (
        "ranger",
        "role",
        "Operates in wild or border terrain.",
    ),
    (
        "scout",
        "role",
        "Reconnaissance and pathfinding role.",
    ),
    (
        "monk",
        "role",
        "Religious or martial monastic discipline.",
    ),
    # Commerce roles (TEND_CRAFT shop branch)
    (
        "keeps_shop",
        "role",
        "Runs a small storefront or stall.",
    ),
    (
        "merchant",
        "role",
        "Trades goods, generic.",
    ),
    (
        "innkeeper",
        "role",
        "Runs lodging and hospitality.",
    ),
    (
        "trader",
        "role",
        "Brokerages and exchange-focused commerce.",
    ),
    # Domestic roles (TEND_CRAFT household branch, MOURN_LOSS)
    (
        "domestic_role",
        "role",
        "Identifies with the work of holding a household together.",
    ),
    (
        "cares_for_household",
        "role",
        "Primary caretaker role within a household.",
    ),
    (
        "matriarch",
        "role",
        "Senior maternal household authority.",
    ),
    (
        "patriarch",
        "role",
        "Senior paternal household authority.",
    ),
    # Study roles (TEND_CRAFT study branch)
    (
        "scholar",
        "role",
        "Practices systematic study.",
    ),
    (
        "researcher",
        "role",
        "Investigative or experimental study role.",
    ),
    (
        "academic",
        "role",
        "Institutional scholarly role.",
    ),
    (
        "loremaster",
        "role",
        "Keeper of specialized knowledge tradition.",
    ),
)


# (tag, category, clearance_kind, clear_on_json, description)
EPHEMERAL_TAGS: Sequence[tuple[str, str, str, str | None, str]] = (
    (
        "bereaved",
        "state",
        "event",
        '{"event_types": ["mourning_completed"]}',
        "Actor has lost someone close. Long-lived; gates MOURN_LOSS; "
        "cleared by an external mourning_completed event (closure ritual, "
        "passage of time-in-world, new significant relationship — author "
        "via CommitOrreryTick or external system).",
    ),
    (
        "dying",
        "state",
        "event",
        '{"event_types": ["wound_healed", "death_recorded"]}',
        "Critical state. Gates KEEP_VIGIL. Cleared by wound_healed "
        "(recovery) or death_recorded (resolution by mortality). "
        "death_recorded is authored externally.",
    ),
    (
        "unconscious",
        "state",
        "event",
        '{"event_types": ["regained_consciousness", "death_recorded"]}',
        "Not currently responsive. Gates KEEP_VIGIL. Cleared by "
        "regained_consciousness or death_recorded — both authored "
        "externally today.",
    ),
    (
        "captive",
        "state",
        "event",
        '{"event_types": ["captivity_ended"]}',
        "Held against will. Diverges from ChatClaude's listing: classified "
        "ephemeral (not durable) because captivity is a condition that "
        "ends (escape / freed / death). KEEP_VIGIL gate updated to use "
        "has_ephemeral accordingly.",
    ),
    (
        "recently_drained",
        "state",
        "semantic",
        None,
        "Actor recently expended substantial restorative power. Cleared "
        "by semantic decay.",
    ),
    (
        "recently_tended",
        "state",
        "semantic",
        None,
        "Target has recently received care. Cleared by semantic decay.",
    ),
    (
        "recently_tended_craft",
        "state",
        "semantic",
        None,
        "Actor recently tended their craft. Marks recent activity for "
        "future cooldown / co-presence predicates.",
    ),
    (
        "at_vigil",
        "state",
        "semantic",
        None,
        "Actor is committed to a vigil. Future templates may read this "
        "to avoid pulling vigil-keepers into routine activity.",
    ),
    (
        "forewarned",
        "state",
        "semantic",
        None,
        "Target has been warned by an ally about an imminent threat.",
    ),
    (
        "under_truce",
        "state",
        "semantic",
        None,
        "Actor is in a brokered truce with a rival. Future templates "
        "(e.g., BREAK_TRUCE) can gate on this state.",
    ),
)


# (event_type, category, severity, description)
NEW_EVENT_TYPES: Sequence[tuple[str, str, str, str]] = (
    # Care
    (
        "tended_wound",
        "care",
        "minor",
        "A non-curative tending action. Preserves wounded ephemeral on target.",
    ),
    (
        "wound_healed",
        "care",
        "moderate",
        "Curative resolution. Clears wounded and dying ephemerals on target.",
    ),
    (
        "vigil_held",
        "care",
        "minor",
        "One tick of vigil activity.",
    ),
    # Emotional
    (
        "mourning_act",
        "emotional",
        "minor",
        "Single small mourning action; accumulates over time.",
    ),
    (
        "mourning_completed",
        "emotional",
        "moderate",
        "Closure ritual or equivalent. Clears bereaved. Authored externally; "
        "MOURN_LOSS itself never emits this — only acknowledges its trigger.",
    ),
    # Routine
    (
        "craft_tended",
        "routine",
        "minor",
        "One tick of craft maintenance.",
    ),
    # Interpersonal
    (
        "contact_made",
        "interpersonal",
        "minor",
        "Baseline contact event emitted by all contact-quartet templates.",
    ),
    (
        "kin_visit",
        "interpersonal",
        "moderate",
        "In-person kin contact; differentiated from contact_made for cooldown.",
    ),
    (
        "welfare_check",
        "interpersonal",
        "minor",
        "In-person dependent welfare check; differentiated for cooldown.",
    ),
    (
        "warning_delivered",
        "interpersonal",
        "moderate",
        "Successful urgent warning to an ally.",
    ),
    (
        "rival_consulted",
        "interpersonal",
        "moderate",
        "Contact between hostile parties under shared pressure.",
    ),
    # State-change events (authored externally; seeded for reference + future use)
    (
        "regained_consciousness",
        "state_change",
        "moderate",
        "Clears unconscious ephemeral. Authored externally.",
    ),
    (
        "death_recorded",
        "state_change",
        "major",
        "Canonical death event. Triggers bereaved across related entities; "
        "clears dying, unconscious, and wounded. Authored externally.",
    ),
    (
        "captivity_ended",
        "state_change",
        "moderate",
        "Resolution of captive state (escape, release, death). Authored " "externally.",
    ),
    (
        "faction_realignment",
        "political",
        "moderate",
        "Significant shift in faction allegiance or structure. Used as "
        "shared-pressure trigger in CONSULT_RIVAL.",
    ),
)


def run(conn) -> None:
    """Apply the package-library round-2 vocabulary migration."""

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
    """Add relationship_type enum values needed by round-2 templates.

    Commits after each ADD VALUE for the same Postgres-version-compat
    reason migration 025 cited (ALTER TYPE ... ADD VALUE has subtle
    transaction semantics; one commit per value is the safe pattern).
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
        for (
            tag,
            category,
            clearance_kind,
            clear_on_json,
            description,
        ) in EPHEMERAL_TAGS:
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
    """Insert new event_types referenced by round-2 templates. Idempotent."""

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
