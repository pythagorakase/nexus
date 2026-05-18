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
``entity_tags`` (and ``tags`` when proposing new vocabulary).
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class NewTagProposal(BaseModel):
    """A tag Skald wants to add to the registered vocabulary.

    Auto-inserted into ``tags`` on apply (decision: max-contrast genre tests
    need the vocab to grow in real time so package gates can match in the same
    session). The corresponding ``entity_tags`` row is stamped with the
    ``skald_inline`` source kind for audit.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    tag: str = Field(
        ...,
        min_length=2,
        max_length=64,
        description=(
            "snake_case tag name (e.g., bodyform:elf, sworn_liege, "
            "scrying_target). Lowercase, no spaces."
        ),
    )
    category: str = Field(
        ...,
        min_length=2,
        max_length=64,
        description=(
            "Tag category. Reuse an existing one when possible (bodyform, "
            "capacity, disposition, role, state, place_affordance, ideology_axis, "
            "etc.). New namespaces are permitted when the existing ones do not fit."
        ),
    )
    scope: Literal["durable", "ephemeral"] = Field(
        ...,
        description=(
            "durable = stable property of the entity (bodyform, role, ideology). "
            "ephemeral = a state that can clear (cursed, in_transit, scrying_target)."
        ),
    )
    evidence: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description=(
            "One-sentence rationale plus a short near-quote from the structured "
            "prose you are filling in. Without evidence, the proposal is noise."
        ),
    )


class OrreryTagBestowal(BaseModel):
    """Tags Skald bestows on an entity during registration or update.

    Embedded as an optional ``orrery_tags`` field on entity schemas. The DB
    writer ``apply_tag_bestowal`` consumes this model and writes ``entity_tags``
    rows (plus ``tags`` rows for proposals).

    ``tags_to_clear`` is only meaningful in update contexts
    (``CharacterStateUpdate`` etc.) — it is silently ignored when an entity is
    first introduced.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    applied_tags: List[str] = Field(
        default_factory=list,
        description=(
            "Registered tag names to apply to this entity. Lookups happen "
            "against the live `tags` table; unknown names are silently skipped, "
            "category-incompatible names are silently skipped."
        ),
    )
    new_tag_proposals: List[NewTagProposal] = Field(
        default_factory=list,
        description=(
            "Tag proposals not yet in the registered vocabulary. Auto-inserted "
            "into `tags` on apply, then applied to this entity."
        ),
    )
    tags_to_clear: List[str] = Field(
        default_factory=list,
        description=(
            "Registered tag names whose open `entity_tags` row should be "
            "cleared (cleared_at = now()) for this entity. Meaningful only in "
            "update contexts."
        ),
    )
