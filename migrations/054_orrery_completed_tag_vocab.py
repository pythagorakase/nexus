"""Seed completed Orrery state and place tag vocabulary anchors."""

from __future__ import annotations

import json
from typing import Any, Sequence

from psycopg2.extensions import connection


# (tag, category, description)
PLACE_DURABLE_TAGS: Sequence[tuple[str, str, str]] = (
    ("commerce", "place_function", "Place supports ordinary buying and selling."),
    ("dwelling", "place_function", "Place supports shelter or domestic routines."),
    ("place_medical", "place_function", "Place supports care, triage, or healing."),
    ("transit", "place_function", "Place supports route movement or transfers."),
    ("archive", "place_function", "Place stores records, memory, or evidence."),
    ("fortification", "place_function", "Place is defensible or fortified."),
    ("haven", "place_function", "Place can shelter or hide someone safely."),
    ("sacred", "place_function", "Place supports ritual, taboo, or worship."),
    ("meeting", "place_function", "Place can host gatherings or negotiations."),
    ("tomb", "place_function", "Place supports burial or remembrance."),
    ("confinement", "place_function", "Place can hold or restrain occupants."),
    ("learning", "place_function", "Place supports instruction or study."),
    ("craft", "place_function", "Place supports making, repair, or workshop labor."),
    ("military", "place_function", "Place supports armed, policing, or command work."),
    ("production", "place_function", "Place supports extraction or throughput."),
    (
        "administration",
        "place_function",
        "Place supports bureaucratic, judicial, or institutional paperwork.",
    ),
    ("water_source", "place_function", "Place has routine or urgent water access."),
    ("entertainment", "place_function", "Place supports leisure or performance."),
    (
        "place_known",
        "place_visibility",
        "Place is broadly discoverable without special knowledge.",
    ),
    (
        "place_hidden",
        "place_visibility",
        "Place is secret, concealed, unmapped, or otherwise hard to find.",
    ),
    (
        "place_open",
        "place_access",
        "Place can be entered or used without special permission.",
    ),
    (
        "place_restricted",
        "place_access",
        "Place requires permission, status, cover, force, or a key to enter.",
    ),
    ("urban_dense", "place_environment", "Dense built environment."),
    ("urban_sparse", "place_environment", "Low-density built environment."),
    ("rural", "place_environment", "Cultivated or settled countryside."),
    ("wilderness", "place_environment", "Uncultivated or minimally settled terrain."),
    ("subterranean", "place_environment", "Underground or buried environment."),
    ("underwater", "place_environment", "Submerged or aquatic environment."),
    ("aerial", "place_environment", "Airborne, elevated, or height-dominant place."),
    ("mountainous", "place_environment", "Steep, high-altitude, or cliff terrain."),
    ("forest", "place_environment", "Dense tree or vegetation cover."),
    ("desert", "place_environment", "Arid terrain with water/exposure pressure."),
    ("polar", "place_environment", "Extreme cold, ice, or snow environment."),
    ("marshland", "place_environment", "Wetland, swamp, bog, or unstable wet ground."),
    ("coastal", "place_environment", "Shore, tide, port, beach, or sea access."),
)

# (tag, category, clear_on_json, description)
PLACE_EPHEMERAL_TAGS: Sequence[tuple[str, str, str, str]] = (
    (
        "place_safe",
        "place_threat",
        '{"description": "replace when danger posture changes"}',
        "Place is currently low-risk enough for rest or routine activity.",
    ),
    (
        "place_contested",
        "place_threat",
        '{"description": "replace when contestation resolves or worsens"}',
        "Place is under active dispute, occupation, siege, or pressure.",
    ),
    (
        "place_dangerous",
        "place_threat",
        '{"description": "replace when danger is removed or transformed"}',
        "Place currently presents immediate or predictable harm.",
    ),
)

# (tag, clear_on_json, reapplication_policy, description)
STATE_EVENT_TAGS: Sequence[tuple[str, str, str, str]] = (
    (
        "wounded",
        '{"event_types": ["tended_wound", "wound_healed"]}',
        "replace",
        "Character is injured; physical scenes and travel are impeded.",
    ),
    (
        "sick",
        '{"event_types": ["recovered_from_illness", "cured"]}',
        "replace",
        "Character is ill or diseased.",
    ),
    (
        "restrained",
        '{"event_types": ["captivity_ended", "escaped"]}',
        "replace",
        "Character is physically bound, pinned, or immobilized this scene.",
    ),
    (
        "enraged",
        '{"event_types": ["retaliation_executed", "confrontation_resolved"]}',
        "replace",
        "Character is in acute anger overriding normal judgment.",
    ),
    (
        "afraid",
        '{"event_types": ["threat_removed"]}',
        "replace",
        "Character is in acute fear and biased toward flight or avoidance.",
    ),
    (
        "grieving",
        '{"event_types": ["mourning_completed"]}',
        "extend_expiry",
        "Character is grieving a consequential loss.",
    ),
    (
        "despairing",
        '{"event_types": ["circumstance_reversed"]}',
        "replace",
        "Character is in acute hopelessness or withdrawal pressure.",
    ),
    (
        "imprisoned",
        '{"event_types": ["captivity_ended", "escaped"]}',
        "replace",
        "Character is held captive across chunks.",
    ),
    (
        "concealed",
        '{"event_types": ["revealed", "discovered"]}',
        "replace",
        "Character is currently unseen or hidden.",
    ),
    (
        "disguised",
        '{"event_types": ["unmasked", "exposed"]}',
        "replace",
        "Character is seen but misidentified.",
    ),
)

# (tag, reapplication_policy, description)
STATE_TIME_TAGS: Sequence[tuple[str, str, str]] = (
    (
        "intoxicated:stimulant",
        "extend_expiry",
        "Character is wired or activated by a stimulant.",
    ),
    (
        "intoxicated:depressant",
        "extend_expiry",
        "Character is sedated or impaired by a depressant.",
    ),
    (
        "intoxicated:hallucinogen",
        "extend_expiry",
        "Character has perceptual distortion from a hallucinogen.",
    ),
    (
        "intoxicated:dissociative",
        "extend_expiry",
        "Character is detached or depersonalized by a dissociative.",
    ),
)

ALLOWED_CATEGORY_REWRITES: dict[str, frozenset[str]] = {
    # Legacy place-affordance row with the same mechanical meaning.
    "wilderness": frozenset({"place_affordance"}),
}


def run(conn: connection) -> None:
    """Seed completed vocabulary rows idempotently."""

    expected = _expected_rows()
    with conn.cursor() as cur:
        _assert_no_unexpected_category_conflicts(cur, expected)
        for tag, category, description in PLACE_DURABLE_TAGS:
            _upsert_tag(
                cur,
                tag=tag,
                category=category,
                is_ephemeral=False,
                clearance_kind=None,
                reapplication_policy=None,
                clear_on_json=None,
                description=description,
            )

        for tag, category, clear_on_json, description in PLACE_EPHEMERAL_TAGS:
            _upsert_tag(
                cur,
                tag=tag,
                category=category,
                is_ephemeral=True,
                clearance_kind="semantic",
                reapplication_policy="replace",
                clear_on_json=clear_on_json,
                description=description,
            )

        for tag, clear_on_json, reapplication_policy, description in STATE_EVENT_TAGS:
            _upsert_tag(
                cur,
                tag=tag,
                category="state",
                is_ephemeral=True,
                clearance_kind="event",
                reapplication_policy=reapplication_policy,
                clear_on_json=clear_on_json,
                description=description,
            )

        for tag, reapplication_policy, description in STATE_TIME_TAGS:
            _upsert_tag(
                cur,
                tag=tag,
                category="state",
                is_ephemeral=True,
                clearance_kind="time",
                reapplication_policy=reapplication_policy,
                clear_on_json=None,
                description=description,
            )

        _assert_seeded_tags(cur, expected)
    conn.commit()


def _upsert_tag(
    cur: Any,
    *,
    tag: str,
    category: str,
    is_ephemeral: bool,
    clearance_kind: str | None,
    reapplication_policy: str | None,
    clear_on_json: str | None,
    description: str,
) -> None:
    cur.execute(
        """
        INSERT INTO tags (
            tag, category, is_ephemeral,
            clearance_kind, reapplication_policy, clear_on,
            synonym_for, deprecated, description
        ) VALUES (
            %s, %s, %s,
            %s::entity_tag_clearance_kind,
            %s::entity_tag_reapplication_policy,
            %s::jsonb,
            NULL, FALSE, %s
        )
        ON CONFLICT (tag) DO UPDATE SET
            category = EXCLUDED.category,
            is_ephemeral = EXCLUDED.is_ephemeral,
            clearance_kind = EXCLUDED.clearance_kind,
            reapplication_policy = EXCLUDED.reapplication_policy,
            clear_on = EXCLUDED.clear_on,
            synonym_for = NULL,
            deprecated = FALSE,
            description = EXCLUDED.description
        """,
        (
            tag,
            category,
            is_ephemeral,
            clearance_kind,
            reapplication_policy,
            clear_on_json,
            description,
        ),
    )


def _assert_no_unexpected_category_conflicts(
    cur: Any,
    expected: dict[str, tuple[Any, ...]],
) -> None:
    expected_categories = {tag: row[0] for tag, row in expected.items()}
    cur.execute(
        """
        SELECT tag, category
        FROM tags
        WHERE tag = ANY(%s)
        ORDER BY tag
        """,
        (list(expected_categories),),
    )
    conflicts: dict[str, tuple[str, str]] = {}
    for tag, actual_category in cur.fetchall():
        expected_category = expected_categories[tag]
        if actual_category == expected_category:
            continue
        if actual_category in ALLOWED_CATEGORY_REWRITES.get(tag, frozenset()):
            continue
        conflicts[tag] = (actual_category, expected_category)

    if conflicts:
        detail = ", ".join(
            f"{tag}={actual} (expected {expected})"
            for tag, (actual, expected) in conflicts.items()
        )
        raise RuntimeError(f"Completed vocabulary tag name collisions: {detail}")


def _assert_seeded_tags(cur: Any, expected: dict[str, tuple[Any, ...]]) -> None:
    cur.execute(
        """
        SELECT tag,
               category,
               is_ephemeral,
               clearance_kind::text,
               reapplication_policy::text,
               clear_on,
               deprecated,
               description
        FROM tags
        WHERE tag = ANY(%s)
        ORDER BY tag
        """,
        (list(expected),),
    )
    actual = {}
    for (
        tag,
        category,
        is_ephemeral,
        clearance_kind,
        reapplication_policy,
        clear_on,
        deprecated,
        description,
    ) in cur.fetchall():
        actual[tag] = (
            category,
            is_ephemeral,
            clearance_kind,
            reapplication_policy,
            _normalize_clear_on(clear_on),
            deprecated,
            description,
        )

    missing = sorted(set(expected) - set(actual))
    mismatched = sorted(
        f"{tag}: expected={expected[tag]!r}, got={actual[tag]!r}"
        for tag in set(expected) & set(actual)
        if actual[tag] != expected[tag]
    )
    if missing or mismatched:
        message = "Completed Orrery vocabulary seed mismatch"
        if missing:
            message += f"; missing={missing}"
        if mismatched:
            message += f"; mismatched={mismatched}"
        raise RuntimeError(message)


def _expected_rows() -> dict[str, tuple[Any, ...]]:
    expected: dict[str, tuple[Any, ...]] = {
        tag: (category, False, None, None, None, False, description)
        for tag, category, description in PLACE_DURABLE_TAGS
    }
    expected.update(
        {
            tag: (
                category,
                True,
                "semantic",
                "replace",
                _normalize_clear_on(clear_on_json),
                False,
                description,
            )
            for tag, category, clear_on_json, description in PLACE_EPHEMERAL_TAGS
        }
    )
    expected.update(
        {
            tag: (
                "state",
                True,
                "event",
                reapplication_policy,
                _normalize_clear_on(clear_on_json),
                False,
                description,
            )
            for (
                tag,
                clear_on_json,
                reapplication_policy,
                description,
            ) in STATE_EVENT_TAGS
        }
    )
    expected.update(
        {
            tag: ("state", True, "time", reapplication_policy, None, False, description)
            for tag, reapplication_policy, description in STATE_TIME_TAGS
        }
    )
    return expected


def _normalize_clear_on(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value
