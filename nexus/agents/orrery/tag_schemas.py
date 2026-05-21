"""Pydantic models for Orrery tag bestowal in Skald's structured output.

These models are embedded in:

- ``nexus.api.new_story_schemas``: ``WildcardTrait`` and ``PlaceProfile``
  (wizard phase tagging of the protagonist and starting location).
- ``nexus.agents.logon.apex_schema``: ``NewCharacter`` / ``NewPlace`` /
  ``NewFaction`` (per-chunk entity introduction) and ``CharacterStateUpdate`` /
  ``LocationStateUpdate`` / ``FactionStateUpdate`` (per-chunk entity update).

Skald fills these as part of normal entity emission. The per-chunk commit
handler and the wizard persistence layer feed them into
``nexus.agents.orrery.tag_writer.apply_tag_bestowal`` to insert into
``entity_tags``. The vocabulary is closed: Skald may only apply registered tag
names.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class OrreryTagBestowal(BaseModel):
    """Tags Skald bestows on an entity during registration or update.

    Embedded as an optional ``orrery_tags`` field on entity schemas. The DB
    writer ``apply_tag_bestowal`` consumes this model and writes ``entity_tags``
    rows for registered tags.

    ``tags_to_clear`` is only meaningful in update contexts
    (``CharacterStateUpdate`` etc.) — it is silently ignored when an entity is
    first introduced.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    applied_tags: List[str] = Field(
        default_factory=list,
        description=(
            "Registered tag names to apply to this entity. Lookups happen "
            "against the live `tags` table; unknown names and "
            "category-incompatible names are hard errors."
        ),
    )
    tags_to_clear: List[str] = Field(
        default_factory=list,
        description=(
            "Registered tag names whose open `entity_tags` row should be "
            "cleared (cleared_at = now()) for this entity. Meaningful only in "
            "update contexts. Clear targets are validated against the live, "
            "non-deprecated registry just like applied tags; unknown, "
            "deprecated, or category-incompatible names are hard errors."
        ),
    )
