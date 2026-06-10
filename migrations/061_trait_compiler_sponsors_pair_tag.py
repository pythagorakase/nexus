"""Register the ``sponsors`` pair-tag for the Patron trait compiler (M5).

M5 finishes the trait compiler: Domain, Patron, Dependents, and Obligations
join Resources, Fame, Status, and Contacts as deterministic compilers. This
migration is the complete design-time vocabulary delta for those four
compilers; it is compatible with the #293 runtime vocabulary lockdown, which
froze runtime growth paths, not authored migrations.

Vocabulary audit per compiler:

- ``Domain`` -> ``claims(character -> place)``. Already registered: migration
  042 seeded ``claims`` and migration 045 extended its subject kinds to
  ``{character, faction}`` explicitly so the registry could accept future
  Domain trait bestowals. No new rows needed.
- ``Dependents`` -> ``protects(character -> dependent)`` plus an affective
  ``character_relationships`` row. ``protects`` was seeded by migration 042
  with subject kinds ``{character, faction}`` / object ``{character}``. No
  new rows needed.
- ``Obligations`` -> ``obligation(character -> creditor)`` where the creditor
  is a character or faction. ``obligation`` was seeded by migration 042 with
  full ``{character, faction}`` polymorphism on both endpoints. No new rows
  needed.
- ``Patron`` -> one ``character_relationships`` row by default (per the #305
  resolution patron is NOT decomposed into a default AND-bundle of edges).
  User-affirmed patron functions selectively add functional pair-tags:
  ``mentors``, ``protects``, and ``authority_over`` are already registered,
  but economic/positional backing -- the "sponsors gap" documented in issue
  #305 -- has no registered edge. This migration adds it.

``sponsors`` subject kinds include ``faction`` to mirror the polymorphism of
its siblings ``protects`` and ``authority_over`` (institutional sponsorship is
a normal world fact); the trait compiler itself only writes the
``character -> character`` form. The tag is durable: sponsorship ends via an
explicit clearance write, not an ephemeral decay rule.

``character_relationships.relationship_type`` is free text (varchar) with no
registry table, so the new ``patron`` / ``dependent`` / ``obligation``
relationship-type strings used by the compilers require no registry rows.
"""

from __future__ import annotations

from typing import Sequence


PAIR_TAGS: Sequence[tuple[str, list[str], list[str], bool, str]] = (
    (
        "sponsors",
        ["character", "faction"],
        ["character"],
        False,
        (
            "Provides economic or positional backing for the object character "
            "without implied command or instruction. Fills the Patron trait "
            "sponsors gap (#305); written only for user-affirmed patron "
            "functions, never as a default bundle."
        ),
    ),
)


def run(conn) -> None:
    """Register trait-compiler pair-tag vocabulary for the Patron trait."""

    with conn.cursor() as cur:
        for tag, subject_kinds, object_kinds, is_ephemeral, description in PAIR_TAGS:
            cur.execute(
                """
                INSERT INTO pair_tags (
                    tag, subject_kinds, object_kinds,
                    is_ephemeral, clearance_kind, description, deprecated
                ) VALUES (
                    %s, %s, %s,
                    %s, NULL, %s, FALSE
                )
                ON CONFLICT (tag) DO UPDATE SET
                    subject_kinds = EXCLUDED.subject_kinds,
                    object_kinds = EXCLUDED.object_kinds,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    description = EXCLUDED.description,
                    deprecated = FALSE
                """,
                (tag, subject_kinds, object_kinds, is_ephemeral, description),
            )

    conn.commit()
