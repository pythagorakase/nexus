"""Canonical built-in pair-tag registry rows shared by migrations and readers."""

from __future__ import annotations

from typing import Sequence


PairTagSeedRow = tuple[str, list[str], list[str], bool, str]


# (tag, subject_kinds, object_kinds, is_ephemeral, description)
PAIR_TAG_SEED: Sequence[PairTagSeedRow] = (
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
        "Subject has permission to enter the place "
        "(direct individual or group-mediated).",
    ),
    (
        "claims",
        ["faction"],
        ["place"],
        False,
        "Subject (faction) asserts a territorial claim on the place; "
        "contestation emerges from row cardinality.",
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
        "Faction's operational base. Distinct from `claims` — claim is "
        "territorial, operates_from is functional.",
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
        "Subject is actively hunting the target. Ephemeral; also confers "
        "narrow targeted detection sensitivity for that target (see issue #282).",
    ),
    (
        "handles",
        ["character"],
        ["character"],
        False,
        "Subject is the operational handler of the target "
        "(covert / espionage / criminal flavor).",
    ),
    (
        "obligation",
        ["character", "faction"],
        ["character", "faction"],
        False,
        "Subject owes a debt / oath / loyalty to the target. Kind inferable "
        "from establishing event.",
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
