"""Pydantic models for Orrery tag bestowal in Skald's structured output.

These models are embedded in:

- ``nexus.api.new_story_schemas``: ``WildcardTrait`` and ``PlaceProfile``
  (wizard phase tagging of the protagonist and starting location).
- ``nexus.agents.logon.apex_schema``: ``CharacterStateUpdate`` /
  ``LocationStateUpdate`` / ``FactionStateUpdate`` (per-chunk entity update).

Skald fills these as part of normal entity updates or wizard registration. The
per-chunk commit handler and the wizard persistence layer feed them into
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
        description="Registered tag names to apply to this entity.",
    )
    tags_to_clear: List[str] = Field(
        default_factory=list,
        description="Registered tag names to clear from this entity.",
    )
