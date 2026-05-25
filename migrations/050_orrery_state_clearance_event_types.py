"""Register clearance event types for the drafted Orrery state vocabulary."""

from __future__ import annotations

from typing import Sequence


EVENT_TYPES: Sequence[tuple[str, str, str, str]] = (
    (
        "recovered_from_illness",
        "care",
        "moderate",
        "A character recovers from sickness without implying a specific cure.",
    ),
    (
        "cured",
        "care",
        "moderate",
        "A sickness state is actively cured by treatment, magic, or intervention.",
    ),
    (
        "escaped",
        "movement",
        "moderate",
        "A character escapes restraint or imprisonment through their own agency.",
    ),
    (
        "revealed",
        "revelation",
        "moderate",
        "A concealed character or fact becomes visible to relevant observers.",
    ),
    (
        "discovered",
        "revelation",
        "moderate",
        "An observer discovers a previously concealed character or fact.",
    ),
    (
        "unmasked",
        "revelation",
        "moderate",
        "A disguised character is recognized as other than their presented identity.",
    ),
    (
        "exposed",
        "revelation",
        "moderate",
        "A disguise, cover, or hidden condition is exposed.",
    ),
    (
        "threat_removed",
        "threat",
        "moderate",
        "The immediate threat sustaining fear is removed or neutralized.",
    ),
    (
        "confrontation_resolved",
        "interpersonal",
        "moderate",
        "A confrontation resolves without requiring retaliation as the clearing beat.",
    ),
    (
        "circumstance_reversed",
        "circumstance",
        "moderate",
        "The circumstance sustaining despair is reversed or materially transformed.",
    ),
)


def run(conn) -> None:
    """Seed state-clearance event types idempotently."""

    with conn.cursor() as cur:
        for event_type, category, severity, description in EVENT_TYPES:
            cur.execute(
                """
                INSERT INTO event_types (
                    type, category, severity, description,
                    deprecated, synonym_for
                ) VALUES (
                    %s, %s, %s::event_severity_kind, %s,
                    FALSE, NULL
                )
                ON CONFLICT (type) DO UPDATE SET
                    category = EXCLUDED.category,
                    severity = EXCLUDED.severity,
                    description = EXCLUDED.description,
                    deprecated = FALSE,
                    synonym_for = NULL
                """,
                (event_type, category, severity, description),
            )

    conn.commit()
