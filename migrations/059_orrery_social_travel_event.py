"""Register scoped event vocabulary for social travel departures."""

from __future__ import annotations

from typing import Sequence


EVENT_TYPES: Sequence[tuple[str, str, str, str]] = (
    (
        "social_travel_departed",
        "social",
        "minor",
        "A character begins travel specifically to seek social company.",
    ),
)


def run(conn) -> None:
    """Seed social travel event types idempotently."""

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
