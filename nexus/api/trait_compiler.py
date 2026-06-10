"""Compile new-story character traits into deterministic Orrery writes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from nexus.agents.orrery.status_family import (
    normalize_status_level,
    status_tag_for_level,
)
from nexus.agents.orrery.substrate import CONTACT_PAIR_TAGS, contact_pair_tag_for_kind
from nexus.agents.orrery.tag_writer import (
    apply_exclusive_tag_bestowal,
    apply_pair_tag_bestowal,
    apply_status_pair_tag_bestowal,
)
from nexus.api.new_story_schemas import CharacterSheet
from nexus.api.trait_compiler_schemas import (
    AppliedPairTag,
    AppliedTag,
    CreatedEntity,
    CreatedRelationship,
    DependentsTraitInput,
    DependentTargetInput,
    DomainTraitInput,
    ObligationsTraitInput,
    ObligationTargetInput,
    PatronTraitInput,
    RelationshipTargetInput,
    SingleEntityTraitInput,
    StatusTraitInput,
    TraitCompileCounters,
    TraitCompileInputs,
    TraitCompileReasonCode,
    TraitCompileResult,
    TraitRelationshipDrift,
    UnresolvedTrait,
    canonical_trait_name,
)


RESOURCE_TAGS = frozenset({"destitute", "poor", "comfortable", "wealthy", "magnate"})
FAME_TAGS = frozenset({"obscure", "known", "renowned", "legendary"})

RELATIONSHIP_DEFAULTS = {
    "allies": {
        "relationship_type": "ally",
        "emotional_valence": "+3|trusting",
        "pair_tag": "ally",
    },
    "contacts": {
        "relationship_type": "contact",
        "emotional_valence": "+1|favorable",
        "pair_tag": "contact",
    },
    "enemies": {
        "relationship_type": "enemy",
        "emotional_valence": "-4|hostile",
        "pair_tag": "hostile_to",
    },
}

DOMAIN_PAIR_TAG = "claims"
DEPENDENT_PAIR_TAG = "protects"
OBLIGATION_PAIR_TAG = "obligation"

PATRON_RELATIONSHIP_TYPE = "patron"
PATRON_DEFAULT_VALENCE = "+2|deferential"
DEPENDENT_RELATIONSHIP_TYPE = "dependent"
DEPENDENT_DEFAULT_VALENCE = "+3|devoted"
OBLIGATION_RELATIONSHIP_TYPE = "obligation"
OBLIGATION_DEFAULT_VALENCE = "-1|beholden"

TRAIT_COMPILER_SOURCE = "trait_compiler"
TRAIT_STUB_KIND = "trait_compiler_target_ref"


@dataclass(frozen=True)
class _ResolvedTarget:
    """A trait target resolved to canonical ids or a pending dry-run stub."""

    row_id: Optional[int]
    entity_id: Optional[int]
    name: Optional[str]
    pending_stub: bool = False


PAIR_TAG_RELATIONSHIP_TYPES = frozenset({"ally", "hostile_to"}) | frozenset(
    CONTACT_PAIR_TAGS.values()
)
CONTACT_KIND_BY_PAIR_TAG = {tag: kind for kind, tag in CONTACT_PAIR_TAGS.items()}


def compile_character_traits(
    cur: Any,
    *,
    character: CharacterSheet,
    character_id: int,
    character_entity_id: int,
    trait_compile_inputs: Optional[TraitCompileInputs | dict[str, Any]] = None,
    dry_run: bool = True,
) -> TraitCompileResult:
    """Compile selected character traits without owning commits.

    Every selected trait produces either deterministic mechanical output or a
    structured prose-only remainder. ``dry_run=True`` validates registry rows
    and reports what would be written without mutating the database.
    """

    inputs = _coerce_inputs(trait_compile_inputs or character.trait_compile_inputs)
    result = TraitCompileResult(
        character_id=character_id,
        character_entity_id=character_entity_id,
        dry_run=dry_run,
    )

    for trait in character.get_trait_entries():
        trait_name = str(trait.name)
        canonical_trait = canonical_trait_name(trait_name)
        if canonical_trait == "resources":
            _compile_single_entity_level(
                cur,
                result=result,
                trait=trait_name,
                entity_id=character_entity_id,
                entity_kind="character",
                typed_input=inputs.resources,
                category="role.resources",
                allowed_levels=RESOURCE_TAGS,
                dry_run=dry_run,
            )
        elif canonical_trait == "fame":
            _compile_single_entity_level(
                cur,
                result=result,
                trait=trait_name,
                entity_id=character_entity_id,
                entity_kind="character",
                typed_input=inputs.fame or inputs.reputation,
                category="role.fame",
                allowed_levels=FAME_TAGS,
                dry_run=dry_run,
            )
        elif canonical_trait == "status":
            _compile_status(
                cur,
                result=result,
                trait=trait_name,
                character_entity_id=character_entity_id,
                typed_input=inputs.status,
                dry_run=dry_run,
            )
        elif canonical_trait in RELATIONSHIP_DEFAULTS:
            _compile_relationship_trait(
                cur,
                result=result,
                trait=trait_name,
                canonical_trait=canonical_trait,
                character_id=character_id,
                character_entity_id=character_entity_id,
                typed_input=getattr(inputs, canonical_trait),
                dry_run=dry_run,
            )
        elif canonical_trait == "domain":
            _compile_domain(
                cur,
                result=result,
                trait=trait_name,
                character_entity_id=character_entity_id,
                typed_input=inputs.domain,
                dry_run=dry_run,
            )
        elif canonical_trait == "patron":
            _compile_patron(
                cur,
                result=result,
                trait=trait_name,
                character_id=character_id,
                character_entity_id=character_entity_id,
                typed_input=inputs.patron,
                dry_run=dry_run,
            )
        elif canonical_trait == "dependents":
            _compile_dependents(
                cur,
                result=result,
                trait=trait_name,
                character_id=character_id,
                character_entity_id=character_entity_id,
                typed_input=inputs.dependents,
                dry_run=dry_run,
            )
        elif canonical_trait == "obligations":
            _compile_obligations(
                cur,
                result=result,
                trait=trait_name,
                character_id=character_id,
                character_entity_id=character_entity_id,
                typed_input=inputs.obligations,
                dry_run=dry_run,
            )
        else:
            _add_remainder(
                result,
                trait=trait_name,
                reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
                message=(
                    "This trait has no typed compiler input in the current MVP; "
                    "its prose remains in character.extra_data."
                ),
            )

    _refresh_counters(result)
    return result


def apply_character_trait_compilation(
    cur: Any,
    *,
    character: CharacterSheet,
    character_id: int,
    character_entity_id: int,
    trait_compile_inputs: Optional[TraitCompileInputs | dict[str, Any]] = None,
) -> TraitCompileResult:
    """Apply trait compilation inside a savepoint owned by the caller transaction."""

    cur.execute("SAVEPOINT trait_compile_apply")
    try:
        result = compile_character_traits(
            cur,
            character=character,
            character_id=character_id,
            character_entity_id=character_entity_id,
            trait_compile_inputs=trait_compile_inputs,
            dry_run=False,
        )
        cur.execute("RELEASE SAVEPOINT trait_compile_apply")
        return result
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT trait_compile_apply")
        cur.execute("RELEASE SAVEPOINT trait_compile_apply")
        raise


def persist_trait_compile_result(
    cur: Any, *, character_id: int, result: TraitCompileResult
) -> None:
    """Persist compile output to durable character extra_data and wizard cache."""

    payload = result.model_dump(mode="json")
    cur.execute(
        """
        UPDATE characters
        SET extra_data = COALESCE(extra_data, '{}'::jsonb) || %s::jsonb
        WHERE id = %s
        """,
        (json.dumps({"trait_compile_result": payload}), character_id),
    )
    if getattr(cur, "rowcount", None) == 0:
        raise RuntimeError(f"Character {character_id} was not updated.")
    cur.execute(
        """
        UPDATE assets.new_story_creator
        SET trait_compile_result = %s::jsonb,
            updated_at = NOW()
        WHERE id = TRUE
        """,
        (json.dumps(payload),),
    )
    if getattr(cur, "rowcount", None) == 0:
        raise RuntimeError("assets.new_story_creator row was not updated.")


def reconcile_trait_relationship_pair_tags(cur: Any) -> list[TraitRelationshipDrift]:
    """Report drift for pair-tags that carry intrinsic relationship meaning."""

    drift: list[TraitRelationshipDrift] = []
    cur.execute(
        """
        SELECT ept.subject_entity_id,
               ept.object_entity_id,
               pt.tag,
               c1.id AS character1_id,
               c2.id AS character2_id
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        LEFT JOIN characters c1 ON c1.entity_id = ept.subject_entity_id
        LEFT JOIN characters c2 ON c2.entity_id = ept.object_entity_id
        LEFT JOIN character_relationships cr
               ON (
                   cr.character1_id = c1.id
                   AND cr.character2_id = c2.id
               )
               OR (
                   cr.character1_id = c2.id
                   AND cr.character2_id = c1.id
               )
        WHERE ept.cleared_at IS NULL
          AND NOT pt.deprecated
          AND pt.tag = ANY(%s)
          AND cr.character1_id IS NULL
        ORDER BY ept.subject_entity_id, ept.object_entity_id, pt.tag
        """,
        (sorted(PAIR_TAG_RELATIONSHIP_TYPES),),
    )
    for row in cur.fetchall():
        drift.append(
            TraitRelationshipDrift(
                drift_kind="missing_relationship",
                subject_entity_id=_row_value(row, "subject_entity_id", 0),
                object_entity_id=_row_value(row, "object_entity_id", 1),
                pair_tag=_row_value(row, "tag", 2),
                character1_id=_row_value(row, "character1_id", 3),
                character2_id=_row_value(row, "character2_id", 4),
            )
        )

    cur.execute(
        """
        SELECT c1.entity_id AS subject_entity_id,
               c2.entity_id AS object_entity_id,
               cr.extra_data->>'trait_compiler_pair_tag' AS pair_tag,
               cr.character1_id,
               cr.character2_id
        FROM character_relationships cr
        JOIN characters c1 ON c1.id = cr.character1_id
        JOIN characters c2 ON c2.id = cr.character2_id
        WHERE cr.extra_data->>'trait_compiler_pair_tag' = ANY(%s)
          AND NOT EXISTS (
              SELECT 1
              FROM entity_pair_tags ept
              JOIN pair_tags pt ON pt.id = ept.pair_tag_id
              WHERE ept.cleared_at IS NULL
                AND NOT pt.deprecated
                AND pt.tag = cr.extra_data->>'trait_compiler_pair_tag'
                AND (
                    (
                        COALESCE(
                            cr.extra_data->>'trait_compiler_pair_tag_direction',
                            'protagonist_to_target'
                        ) = 'protagonist_to_target'
                        AND ept.subject_entity_id = c1.entity_id
                        AND ept.object_entity_id = c2.entity_id
                    )
                    OR (
                        cr.extra_data->>'trait_compiler_pair_tag_direction'
                            = 'target_to_protagonist'
                        AND ept.subject_entity_id = c2.entity_id
                        AND ept.object_entity_id = c1.entity_id
                    )
                )
          )
        ORDER BY c1.entity_id, c2.entity_id, pair_tag
        """,
        (sorted(PAIR_TAG_RELATIONSHIP_TYPES),),
    )
    for row in cur.fetchall():
        drift.append(
            TraitRelationshipDrift(
                drift_kind="missing_pair_tag",
                subject_entity_id=_row_value(row, "subject_entity_id", 0),
                object_entity_id=_row_value(row, "object_entity_id", 1),
                pair_tag=_row_value(row, "pair_tag", 2),
                character1_id=_row_value(row, "character1_id", 3),
                character2_id=_row_value(row, "character2_id", 4),
            )
        )

    return drift


def _compile_single_entity_level(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    entity_id: int,
    entity_kind: str,
    typed_input: Optional[SingleEntityTraitInput],
    category: str,
    allowed_levels: Iterable[str],
    dry_run: bool,
) -> None:
    if typed_input is None:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message="Trait has no structured level input.",
        )
        return

    tag = typed_input.level
    if tag not in set(allowed_levels) or not _registered_tag_exists(cur, tag, category):
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.REGISTRY_MISSING_TAG,
            message=f"No active registered tag for {category}:{tag}.",
            details={"tag": tag, "category": category},
        )
        return

    inserted: Optional[bool] = None
    if not dry_run:
        inserted = apply_exclusive_tag_bestowal(
            cur,
            entity_id=entity_id,
            entity_kind=entity_kind,
            tag=tag,
            source_kind="skald_inline",
        )
    result.applied_single_entity_tags.append(
        AppliedTag(
            trait=trait,
            entity_id=entity_id,
            tag=tag,
            category=category,
            inserted=inserted,
            dry_run=dry_run,
        )
    )


def _compile_status(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    character_entity_id: int,
    typed_input: Optional[StatusTraitInput],
    dry_run: bool,
) -> None:
    if typed_input is None:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message="Status has no structured scope faction and level input.",
        )
        return
    try:
        level = normalize_status_level(typed_input.level)
    except ValueError:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.UNKNOWN_STATUS_LEVEL,
            message=f"Unknown status level {typed_input.level!r}.",
            details={"level": typed_input.level},
        )
        return

    scope_faction_entity_id = typed_input.scope_faction_entity_id
    if scope_faction_entity_id is None and typed_input.scope_faction_name:
        scope_faction_entity_id = _lookup_faction_entity_id(
            cur, typed_input.scope_faction_name
        )
        if scope_faction_entity_id is None:
            _add_remainder(
                result,
                trait=trait,
                reason_code=TraitCompileReasonCode.UNKNOWN_SCOPE_FACTION,
                message=f"Unknown scope faction {typed_input.scope_faction_name!r}.",
                details={"scope_faction_name": typed_input.scope_faction_name},
            )
            return
    if scope_faction_entity_id is None:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.AMBIGUOUS_TARGET,
            message="Status requires a scope faction entity id or name.",
        )
        return

    tag = status_tag_for_level(level)
    if not _registered_pair_tag_exists(cur, tag):
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.REGISTRY_MISSING_PAIR_TAG,
            message=f"No active registered pair_tag for {tag}.",
            details={"pair_tag": tag},
        )
        return

    inserted: Optional[bool] = None
    if not dry_run:
        inserted = apply_status_pair_tag_bestowal(
            cur,
            subject_entity_id=character_entity_id,
            scope_faction_entity_id=scope_faction_entity_id,
            subject_kind="character",
            level=level,
            source_kind="skald_inline",
        )
    result.applied_pair_tags.append(
        AppliedPairTag(
            trait=trait,
            subject_entity_id=character_entity_id,
            object_entity_id=scope_faction_entity_id,
            tag=tag,
            inserted=inserted,
            dry_run=dry_run,
        )
    )


def _compile_relationship_trait(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    canonical_trait: str,
    character_id: int,
    character_entity_id: int,
    typed_input: Any,
    dry_run: bool,
) -> None:
    if typed_input is None or not typed_input.targets:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message="Relationship trait has no structured targets.",
        )
        return

    for target in typed_input.targets:
        _compile_relationship_target(
            cur,
            result=result,
            trait=trait,
            canonical_trait=canonical_trait,
            character_id=character_id,
            character_entity_id=character_entity_id,
            target=target,
            dry_run=dry_run,
        )


def _compile_relationship_target(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    canonical_trait: str,
    character_id: int,
    character_entity_id: int,
    target: RelationshipTargetInput,
    dry_run: bool,
) -> None:
    if target.character_id is None:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.AMBIGUOUS_TARGET,
            message="Relationship target requires an existing character_id.",
            details={"name": target.name},
        )
        return

    defaults = RELATIONSHIP_DEFAULTS[canonical_trait]
    relationship_type = target.relationship_type or defaults["relationship_type"]
    emotional_valence = target.emotional_valence or defaults["emotional_valence"]
    pair_tag = target.pair_tag or defaults["pair_tag"]

    contact_kind = target.contact_kind if canonical_trait == "contacts" else None
    if target.apply_pair_tag and canonical_trait == "contacts":
        resolved_contact = _resolve_contact_pair_tag(
            result,
            trait=trait,
            target=target,
        )
        if resolved_contact is None:
            return
        pair_tag, contact_kind = resolved_contact

    if target.apply_pair_tag and target.character_entity_id is None:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.AMBIGUOUS_TARGET,
            message="Pair-tagged relationship target requires character_entity_id.",
            details={"name": target.name, "pair_tag": pair_tag},
        )
        return
    if target.apply_pair_tag and not _registered_pair_tag_exists(cur, pair_tag):
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.REGISTRY_MISSING_PAIR_TAG,
            message=f"No active registered pair_tag for {pair_tag}.",
            details={"pair_tag": pair_tag},
        )
        return

    inserted_pair_tag: Optional[bool] = None
    if target.apply_pair_tag:
        target_entity_id = target.character_entity_id
        if target_entity_id is None:
            raise AssertionError("pair-tag target entity id was validated above")
        pair_subject_entity_id = character_entity_id
        pair_object_entity_id = target_entity_id
        if target.pair_tag_direction == "target_to_protagonist":
            pair_subject_entity_id = target_entity_id
            pair_object_entity_id = character_entity_id

        if not dry_run:
            inserted_pair_tag = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=pair_subject_entity_id,
                object_entity_id=pair_object_entity_id,
                subject_kind="character",
                object_kind="character",
                tag=pair_tag,
                source_kind="skald_inline",
            )
        result.applied_pair_tags.append(
            AppliedPairTag(
                trait=trait,
                subject_entity_id=pair_subject_entity_id,
                object_entity_id=pair_object_entity_id,
                tag=pair_tag,
                inserted=inserted_pair_tag,
                dry_run=dry_run,
            )
        )

    if not dry_run:
        _upsert_character_relationship(
            cur,
            character1_id=character_id,
            character2_id=target.character_id,
            relationship_type=relationship_type,
            emotional_valence=emotional_valence,
            dynamic=target.dynamic,
            recent_events=target.recent_events,
            history=target.history,
            trait=trait,
            pair_tag=pair_tag if target.apply_pair_tag else None,
            pair_tag_direction=(
                target.pair_tag_direction if target.apply_pair_tag else None
            ),
            contact_kind=contact_kind,
        )
    result.created_relationships.append(
        CreatedRelationship(
            trait=trait,
            character1_id=character_id,
            character2_id=target.character_id,
            relationship_type=relationship_type,
            emotional_valence=emotional_valence,
            pair_tag=pair_tag if target.apply_pair_tag else None,
            contact_kind=contact_kind,
            dry_run=dry_run,
        )
    )


def _resolve_contact_pair_tag(
    result: TraitCompileResult,
    *,
    trait: str,
    target: RelationshipTargetInput,
) -> Optional[tuple[str, str]]:
    if target.contact_kind is not None:
        kind_pair_tag = contact_pair_tag_for_kind(target.contact_kind)
        if target.pair_tag is not None and target.pair_tag != kind_pair_tag:
            _add_remainder(
                result,
                trait=trait,
                reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
                message=(
                    "Contacts pair-tag input must not disagree with contact_kind."
                ),
                details={
                    "name": target.name,
                    "contact_kind": target.contact_kind,
                    "pair_tag": target.pair_tag,
                    "expected_pair_tag": kind_pair_tag,
                },
            )
            return None
        return kind_pair_tag, target.contact_kind

    if target.pair_tag is not None and target.pair_tag in CONTACT_KIND_BY_PAIR_TAG:
        return target.pair_tag, CONTACT_KIND_BY_PAIR_TAG[target.pair_tag]

    if target.pair_tag is not None and target.pair_tag.startswith("contact:"):
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message=(
                "Contacts pair-tag input must use a registered contact kind "
                "(lodging, social, intimate)."
            ),
            details={"name": target.name, "pair_tag": target.pair_tag},
        )
        return None

    _add_remainder(
        result,
        trait=trait,
        reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
        message=(
            "Contacts pair-tag input requires contact_kind "
            "(lodging, social, intimate) or an explicit contact:<kind> pair_tag."
        ),
        details={"name": target.name, "pair_tag": target.pair_tag or "contact"},
    )
    return None


def _compile_domain(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    character_entity_id: int,
    typed_input: Optional[DomainTraitInput],
    dry_run: bool,
) -> None:
    """Compile Domain to ``claims(protagonist -> place)`` per the design target."""

    if typed_input is None:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message="Domain has no structured place input.",
        )
        return
    if not _registered_pair_tag_exists(cur, DOMAIN_PAIR_TAG):
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.REGISTRY_MISSING_PAIR_TAG,
            message=f"No active registered pair_tag for {DOMAIN_PAIR_TAG}.",
            details={"pair_tag": DOMAIN_PAIR_TAG},
        )
        return

    resolved = _resolve_place_target(
        cur,
        result=result,
        trait=trait,
        place_id=typed_input.place_id,
        place_entity_id=typed_input.place_entity_id,
        name=typed_input.name,
        dry_run=dry_run,
    )
    if resolved is None:
        return

    inserted: Optional[bool] = None
    if not dry_run:
        if resolved.entity_id is None:
            raise AssertionError("apply-mode place target must have an entity id")
        inserted = apply_pair_tag_bestowal(
            cur,
            subject_entity_id=character_entity_id,
            object_entity_id=resolved.entity_id,
            subject_kind="character",
            object_kind="place",
            tag=DOMAIN_PAIR_TAG,
            source_kind="skald_inline",
        )
    result.applied_pair_tags.append(
        AppliedPairTag(
            trait=trait,
            subject_entity_id=character_entity_id,
            object_entity_id=resolved.entity_id,
            object_name=resolved.name if resolved.pending_stub else None,
            tag=DOMAIN_PAIR_TAG,
            inserted=inserted,
            dry_run=dry_run,
        )
    )


def _compile_patron(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    character_id: int,
    character_entity_id: int,
    typed_input: Optional[PatronTraitInput],
    dry_run: bool,
) -> None:
    """Compile Patron per #305: relationship row plus user-affirmed functions."""

    if typed_input is None:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message="Patron has no structured target input.",
        )
        return

    functions = list(dict.fromkeys(typed_input.functions))
    for function in functions:
        if not _registered_pair_tag_exists(cur, function):
            _add_remainder(
                result,
                trait=trait,
                reason_code=TraitCompileReasonCode.REGISTRY_MISSING_PAIR_TAG,
                message=f"No active registered pair_tag for {function}.",
                details={"pair_tag": function},
            )
            return

    resolved = _resolve_character_target(
        cur,
        result=result,
        trait=trait,
        role="patron",
        target_character_id=typed_input.character_id,
        target_character_entity_id=typed_input.character_entity_id,
        name=typed_input.name,
        protagonist_character_id=character_id,
        dry_run=dry_run,
    )
    if resolved is None:
        return

    for function in functions:
        inserted: Optional[bool] = None
        if not dry_run:
            if resolved.entity_id is None:
                raise AssertionError("apply-mode patron must have an entity id")
            inserted = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=resolved.entity_id,
                object_entity_id=character_entity_id,
                subject_kind="character",
                object_kind="character",
                tag=function,
                source_kind="skald_inline",
            )
        result.applied_pair_tags.append(
            AppliedPairTag(
                trait=trait,
                subject_entity_id=resolved.entity_id,
                subject_name=resolved.name if resolved.pending_stub else None,
                object_entity_id=character_entity_id,
                tag=function,
                inserted=inserted,
                dry_run=dry_run,
            )
        )

    emotional_valence = typed_input.emotional_valence or PATRON_DEFAULT_VALENCE
    additional_extra_data: dict[str, Any] = {}
    if functions:
        additional_extra_data["trait_compiler_patron_functions"] = functions
    _write_trait_relationship(
        cur,
        result=result,
        trait=trait,
        character1_id=character_id,
        target=resolved,
        relationship_type=PATRON_RELATIONSHIP_TYPE,
        emotional_valence=emotional_valence,
        dynamic=typed_input.dynamic,
        recent_events=typed_input.recent_events,
        history=typed_input.history,
        additional_extra_data=additional_extra_data,
        dry_run=dry_run,
    )


def _compile_dependents(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    character_id: int,
    character_entity_id: int,
    typed_input: Optional[DependentsTraitInput],
    dry_run: bool,
) -> None:
    """Compile Dependents per the settled target: protects edge + bond row."""

    if typed_input is None or not typed_input.targets:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message="Dependents has no structured targets.",
        )
        return
    if not _registered_pair_tag_exists(cur, DEPENDENT_PAIR_TAG):
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.REGISTRY_MISSING_PAIR_TAG,
            message=f"No active registered pair_tag for {DEPENDENT_PAIR_TAG}.",
            details={"pair_tag": DEPENDENT_PAIR_TAG},
        )
        return

    for target in typed_input.targets:
        _compile_dependent_target(
            cur,
            result=result,
            trait=trait,
            character_id=character_id,
            character_entity_id=character_entity_id,
            target=target,
            dry_run=dry_run,
        )


def _compile_dependent_target(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    character_id: int,
    character_entity_id: int,
    target: DependentTargetInput,
    dry_run: bool,
) -> None:
    resolved = _resolve_character_target(
        cur,
        result=result,
        trait=trait,
        role="dependent",
        target_character_id=target.character_id,
        target_character_entity_id=target.character_entity_id,
        name=target.name,
        protagonist_character_id=character_id,
        dry_run=dry_run,
    )
    if resolved is None:
        return

    inserted: Optional[bool] = None
    if not dry_run:
        if resolved.entity_id is None:
            raise AssertionError("apply-mode dependent must have an entity id")
        inserted = apply_pair_tag_bestowal(
            cur,
            subject_entity_id=character_entity_id,
            object_entity_id=resolved.entity_id,
            subject_kind="character",
            object_kind="character",
            tag=DEPENDENT_PAIR_TAG,
            source_kind="skald_inline",
        )
    result.applied_pair_tags.append(
        AppliedPairTag(
            trait=trait,
            subject_entity_id=character_entity_id,
            object_entity_id=resolved.entity_id,
            object_name=resolved.name if resolved.pending_stub else None,
            tag=DEPENDENT_PAIR_TAG,
            inserted=inserted,
            dry_run=dry_run,
        )
    )

    _write_trait_relationship(
        cur,
        result=result,
        trait=trait,
        character1_id=character_id,
        target=resolved,
        relationship_type=DEPENDENT_RELATIONSHIP_TYPE,
        emotional_valence=target.emotional_valence or DEPENDENT_DEFAULT_VALENCE,
        dynamic=target.dynamic,
        recent_events=target.recent_events,
        history=target.history,
        additional_extra_data={
            "trait_compiler_functional_pair_tag": DEPENDENT_PAIR_TAG
        },
        dry_run=dry_run,
    )


def _compile_obligations(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    character_id: int,
    character_entity_id: int,
    typed_input: Optional[ObligationsTraitInput],
    dry_run: bool,
) -> None:
    """Compile Obligations to ``obligation(protagonist -> counterparty)``."""

    if typed_input is None or not typed_input.targets:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message="Obligations has no structured targets.",
        )
        return
    if not _registered_pair_tag_exists(cur, OBLIGATION_PAIR_TAG):
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.REGISTRY_MISSING_PAIR_TAG,
            message=f"No active registered pair_tag for {OBLIGATION_PAIR_TAG}.",
            details={"pair_tag": OBLIGATION_PAIR_TAG},
        )
        return

    for target in typed_input.targets:
        _compile_obligation_target(
            cur,
            result=result,
            trait=trait,
            character_id=character_id,
            character_entity_id=character_entity_id,
            target=target,
            dry_run=dry_run,
        )


def _compile_obligation_target(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    character_id: int,
    character_entity_id: int,
    target: ObligationTargetInput,
    dry_run: bool,
) -> None:
    if target.counterparty_kind == "character":
        resolved = _resolve_character_target(
            cur,
            result=result,
            trait=trait,
            role="obligation_counterparty",
            target_character_id=target.counterparty_id,
            target_character_entity_id=target.counterparty_entity_id,
            name=target.name,
            protagonist_character_id=character_id,
            dry_run=dry_run,
        )
    else:
        resolved = _resolve_faction_target(
            cur,
            result=result,
            trait=trait,
            faction_id=target.counterparty_id,
            faction_entity_id=target.counterparty_entity_id,
            name=target.name,
            dry_run=dry_run,
        )
    if resolved is None:
        return

    inserted: Optional[bool] = None
    if not dry_run:
        if resolved.entity_id is None:
            raise AssertionError("apply-mode counterparty must have an entity id")
        inserted = apply_pair_tag_bestowal(
            cur,
            subject_entity_id=character_entity_id,
            object_entity_id=resolved.entity_id,
            subject_kind="character",
            object_kind=target.counterparty_kind,
            tag=OBLIGATION_PAIR_TAG,
            source_kind="skald_inline",
        )
    result.applied_pair_tags.append(
        AppliedPairTag(
            trait=trait,
            subject_entity_id=character_entity_id,
            object_entity_id=resolved.entity_id,
            object_name=resolved.name if resolved.pending_stub else None,
            tag=OBLIGATION_PAIR_TAG,
            inserted=inserted,
            dry_run=dry_run,
        )
    )

    if target.counterparty_kind == "character":
        _write_trait_relationship(
            cur,
            result=result,
            trait=trait,
            character1_id=character_id,
            target=resolved,
            relationship_type=OBLIGATION_RELATIONSHIP_TYPE,
            emotional_valence=target.emotional_valence or OBLIGATION_DEFAULT_VALENCE,
            dynamic=target.dynamic,
            recent_events=target.recent_events,
            history=target.history,
            additional_extra_data={
                "trait_compiler_functional_pair_tag": OBLIGATION_PAIR_TAG
            },
            dry_run=dry_run,
        )


def _write_trait_relationship(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    character1_id: int,
    target: _ResolvedTarget,
    relationship_type: str,
    emotional_valence: str,
    dynamic: str,
    recent_events: str,
    history: str,
    additional_extra_data: Optional[dict[str, Any]],
    dry_run: bool,
) -> None:
    """Record (and on apply, upsert) a compiler-authored relationship row."""

    if not dry_run:
        if target.row_id is None:
            raise AssertionError("apply-mode relationship target must have a row id")
        _upsert_character_relationship(
            cur,
            character1_id=character1_id,
            character2_id=target.row_id,
            relationship_type=relationship_type,
            emotional_valence=emotional_valence,
            dynamic=dynamic,
            recent_events=recent_events,
            history=history,
            trait=trait,
            pair_tag=None,
            pair_tag_direction=None,
            contact_kind=None,
            additional_extra_data=additional_extra_data,
        )
    result.created_relationships.append(
        CreatedRelationship(
            trait=trait,
            character1_id=character1_id,
            character2_id=target.row_id,
            character2_name=target.name if target.pending_stub else None,
            relationship_type=relationship_type,
            emotional_valence=emotional_valence,
            dry_run=dry_run,
        )
    )


def _resolve_character_target(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    role: str,
    target_character_id: Optional[int],
    target_character_entity_id: Optional[int],
    name: Optional[str],
    protagonist_character_id: int,
    dry_run: bool,
) -> Optional[_ResolvedTarget]:
    """Resolve a character target by id, entity id, or exact name (stub-creatable)."""

    if target_character_id is not None:
        cur.execute(
            "SELECT id, entity_id, name FROM characters WHERE id = %s",
            (target_character_id,),
        )
        rows = cur.fetchall()
    elif target_character_entity_id is not None:
        cur.execute(
            "SELECT id, entity_id, name FROM characters WHERE entity_id = %s",
            (target_character_entity_id,),
        )
        rows = cur.fetchall()
    elif name:
        cur.execute(
            "SELECT id, entity_id, name FROM characters WHERE name = %s ORDER BY id",
            (name,),
        )
        rows = cur.fetchall()
        if not rows:
            return _create_target_stub(
                cur,
                result=result,
                trait=trait,
                entity_kind="character",
                name=name,
                role=role,
                dry_run=dry_run,
            )
    else:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message=f"{trait} target requires a character id, entity id, or name.",
        )
        return None

    resolved = _single_row_target(
        result,
        trait=trait,
        rows=rows,
        lookup={
            "character_id": target_character_id,
            "character_entity_id": target_character_entity_id,
            "name": name,
        },
    )
    if resolved is None:
        return None
    if resolved.row_id == protagonist_character_id:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.AMBIGUOUS_TARGET,
            message=f"{trait} target resolves to the protagonist.",
            details={"character_id": resolved.row_id},
        )
        return None
    return resolved


def _resolve_place_target(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    place_id: Optional[int],
    place_entity_id: Optional[int],
    name: Optional[str],
    dry_run: bool,
) -> Optional[_ResolvedTarget]:
    """Resolve a place target by id, entity id, or exact name (stub-creatable)."""

    if place_id is not None:
        cur.execute(
            "SELECT id, entity_id, name FROM places WHERE id = %s",
            (place_id,),
        )
        rows = cur.fetchall()
    elif place_entity_id is not None:
        cur.execute(
            "SELECT id, entity_id, name FROM places WHERE entity_id = %s",
            (place_entity_id,),
        )
        rows = cur.fetchall()
    elif name:
        cur.execute(
            "SELECT id, entity_id, name FROM places WHERE name = %s ORDER BY id",
            (name,),
        )
        rows = cur.fetchall()
        if not rows:
            return _create_target_stub(
                cur,
                result=result,
                trait=trait,
                entity_kind="place",
                name=name,
                role="domain",
                dry_run=dry_run,
            )
    else:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message=f"{trait} requires a place id, entity id, or name.",
        )
        return None

    return _single_row_target(
        result,
        trait=trait,
        rows=rows,
        lookup={
            "place_id": place_id,
            "place_entity_id": place_entity_id,
            "name": name,
        },
    )


def _resolve_faction_target(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    faction_id: Optional[int],
    faction_entity_id: Optional[int],
    name: Optional[str],
    dry_run: bool,
) -> Optional[_ResolvedTarget]:
    """Resolve a faction target by id, entity id, or exact name (stub-creatable)."""

    if faction_id is not None:
        cur.execute(
            "SELECT id, entity_id, name FROM factions WHERE id = %s",
            (faction_id,),
        )
        rows = cur.fetchall()
    elif faction_entity_id is not None:
        cur.execute(
            "SELECT id, entity_id, name FROM factions WHERE entity_id = %s",
            (faction_entity_id,),
        )
        rows = cur.fetchall()
    elif name:
        cur.execute(
            "SELECT id, entity_id, name FROM factions WHERE name = %s ORDER BY id",
            (name,),
        )
        rows = cur.fetchall()
        if not rows:
            return _create_target_stub(
                cur,
                result=result,
                trait=trait,
                entity_kind="faction",
                name=name,
                role="obligation_counterparty",
                dry_run=dry_run,
            )
    else:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.MISSING_STRUCTURED_TRAIT_INPUT,
            message=f"{trait} requires a faction id, entity id, or name.",
        )
        return None

    return _single_row_target(
        result,
        trait=trait,
        rows=rows,
        lookup={
            "faction_id": faction_id,
            "faction_entity_id": faction_entity_id,
            "name": name,
        },
    )


def _single_row_target(
    result: TraitCompileResult,
    *,
    trait: str,
    rows: list[Any],
    lookup: dict[str, Any],
) -> Optional[_ResolvedTarget]:
    details = {key: value for key, value in lookup.items() if value is not None}
    if not rows:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.AMBIGUOUS_TARGET,
            message=f"{trait} target was not found.",
            details=details,
        )
        return None
    if len(rows) > 1:
        _add_remainder(
            result,
            trait=trait,
            reason_code=TraitCompileReasonCode.AMBIGUOUS_TARGET,
            message=f"{trait} target name matches multiple rows.",
            details={**details, "match_count": len(rows)},
        )
        return None
    row = rows[0]
    return _ResolvedTarget(
        row_id=_row_value(row, "id", 0),
        entity_id=_row_value(row, "entity_id", 1),
        name=_row_value(row, "name", 2),
    )


def _create_target_stub(
    cur: Any,
    *,
    result: TraitCompileResult,
    trait: str,
    entity_kind: str,
    name: str,
    role: str,
    dry_run: bool,
) -> _ResolvedTarget:
    """Create (or, on dry-run, plan) a minimum-viable stub for a trait target.

    Stub rows follow the Retrograde persistence conventions: intentionally
    sparse columns plus ``extra_data`` provenance, so wizard-time Retrograde
    Phase A can mature them into history. Nothing is generated recursively
    for stubs.
    """

    if dry_run:
        result.created_entities.append(
            CreatedEntity(
                trait=trait,
                entity_kind=entity_kind,
                entity_id=None,
                row_id=None,
                name=name,
                dry_run=True,
            )
        )
        return _ResolvedTarget(
            row_id=None,
            entity_id=None,
            name=name,
            pending_stub=True,
        )

    if entity_kind == "character":
        row_id, entity_id = _insert_character_stub(
            cur, name=name, trait=trait, role=role
        )
    elif entity_kind == "place":
        row_id, entity_id = _insert_place_stub(cur, name=name, trait=trait, role=role)
    elif entity_kind == "faction":
        row_id, entity_id = _insert_faction_stub(cur, name=name, trait=trait, role=role)
    else:
        raise ValueError(f"Unsupported trait stub entity kind {entity_kind!r}")
    result.created_entities.append(
        CreatedEntity(
            trait=trait,
            entity_kind=entity_kind,
            entity_id=entity_id,
            row_id=row_id,
            name=name,
            dry_run=False,
        )
    )
    return _ResolvedTarget(row_id=row_id, entity_id=entity_id, name=name)


def _insert_character_stub(
    cur: Any, *, name: str, trait: str, role: str
) -> tuple[int, int]:
    cur.execute(
        """
        /* trait_compiler:insert_character_stub */
        INSERT INTO characters (
            name, summary, background, current_activity, extra_data
        )
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING id, entity_id
        """,
        (
            name,
            _stub_summary(name, "character"),
            "Trait-compiler stub; details intentionally sparse until play.",
            "latent in compiled trait backstory",
            json.dumps(_stub_extra_data(trait=trait, role=role)),
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Character stub insert for {name!r} returned no row.")
    return _row_value(row, "id", 0), _row_value(row, "entity_id", 1)


def _insert_place_stub(
    cur: Any, *, name: str, trait: str, role: str
) -> tuple[int, int]:
    cur.execute(
        """
        /* trait_compiler:insert_place_stub */
        INSERT INTO places (
            name, type, summary, current_status, extra_data
        )
        VALUES (%s, 'other'::place_type, %s, %s, %s::jsonb)
        RETURNING id, entity_id
        """,
        (
            name,
            _stub_summary(name, "place"),
            "latent in compiled trait backstory",
            json.dumps(_stub_extra_data(trait=trait, role=role)),
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Place stub insert for {name!r} returned no row.")
    return _row_value(row, "id", 0), _row_value(row, "entity_id", 1)


def _insert_faction_stub(
    cur: Any, *, name: str, trait: str, role: str
) -> tuple[int, int]:
    cur.execute("LOCK TABLE factions IN SHARE ROW EXCLUSIVE MODE")
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 AS id FROM factions")
    faction_id = int(_row_value(cur.fetchone(), "id", 0))
    cur.execute(
        """
        /* trait_compiler:insert_faction_stub */
        INSERT INTO factions (
            id, name, summary, extra_data
        )
        VALUES (%s, %s, %s, %s::jsonb)
        RETURNING entity_id
        """,
        (
            faction_id,
            name,
            _stub_summary(name, "faction"),
            json.dumps(_stub_extra_data(trait=trait, role=role)),
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Faction stub insert for {name!r} returned no row.")
    return faction_id, _row_value(row, "entity_id", 0)


def _stub_summary(name: str, entity_kind: str) -> str:
    return (
        f"Trait-compiler {entity_kind} stub for {name}. "
        "Created so wizard trait selections resolve to canonical rows."
    )


def _stub_extra_data(*, trait: str, role: str) -> dict[str, Any]:
    return {
        "source": TRAIT_COMPILER_SOURCE,
        "stub_kind": TRAIT_STUB_KIND,
        "sources": [{"plan": "trait_compile", "trait": trait, "role": role}],
    }


def _upsert_character_relationship(
    cur: Any,
    *,
    character1_id: int,
    character2_id: int,
    relationship_type: str,
    emotional_valence: str,
    dynamic: str,
    recent_events: str,
    history: str,
    trait: str,
    pair_tag: Optional[str],
    pair_tag_direction: Optional[str],
    contact_kind: Optional[str],
    additional_extra_data: Optional[dict[str, Any]] = None,
) -> None:
    extra_data: dict[str, Any] = {
        "source": "trait_compiler",
        "trait": trait,
    }
    if pair_tag is not None:
        extra_data["trait_compiler_pair_tag"] = pair_tag
    if pair_tag_direction is not None:
        extra_data["trait_compiler_pair_tag_direction"] = pair_tag_direction
    if contact_kind is not None:
        extra_data["trait_compiler_contact_kind"] = contact_kind
    if additional_extra_data:
        extra_data.update(additional_extra_data)
    cur.execute(
        """
        INSERT INTO character_relationships (
            character1_id, character2_id, relationship_type, emotional_valence,
            dynamic, recent_events, history, extra_data
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s::jsonb
        )
        ON CONFLICT (character1_id, character2_id) DO UPDATE SET
            relationship_type = EXCLUDED.relationship_type,
            emotional_valence = EXCLUDED.emotional_valence,
            dynamic = EXCLUDED.dynamic,
            recent_events = EXCLUDED.recent_events,
            history = EXCLUDED.history,
            extra_data = COALESCE(character_relationships.extra_data, '{}'::jsonb)
                         || EXCLUDED.extra_data,
            updated_at = NOW()
        """,
        (
            character1_id,
            character2_id,
            relationship_type,
            emotional_valence,
            dynamic,
            recent_events,
            history,
            json.dumps(extra_data),
        ),
    )


def _registered_tag_exists(cur: Any, tag: str, category: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM tags
        WHERE tag = %s
          AND category = %s
          AND NOT deprecated
          AND synonym_for IS NULL
        LIMIT 1
        """,
        (tag, category),
    )
    return cur.fetchone() is not None


def _registered_pair_tag_exists(cur: Any, tag: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM pair_tags
        WHERE tag = %s
          AND NOT deprecated
        LIMIT 1
        """,
        (tag,),
    )
    return cur.fetchone() is not None


def _lookup_faction_entity_id(cur: Any, faction_name: str) -> Optional[int]:
    cur.execute(
        """
        SELECT entity_id
        FROM factions
        WHERE name = %s
        ORDER BY entity_id
        LIMIT 1
        """,
        (faction_name,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_value(row, "entity_id", 0)


def _coerce_inputs(
    value: Optional[TraitCompileInputs | dict[str, Any]],
) -> TraitCompileInputs:
    if value is None:
        return TraitCompileInputs()
    if isinstance(value, TraitCompileInputs):
        return value
    return TraitCompileInputs.model_validate(value)


def _add_remainder(
    result: TraitCompileResult,
    *,
    trait: str,
    reason_code: TraitCompileReasonCode,
    message: str,
    details: Optional[dict[str, Any]] = None,
) -> None:
    result.prose_only_remainders.append(
        UnresolvedTrait(
            trait=trait,
            reason_code=reason_code,
            message=message,
            details=details or {},
        )
    )


def _refresh_counters(result: TraitCompileResult) -> None:
    result.counters = TraitCompileCounters(
        applied_single_entity_tags=len(result.applied_single_entity_tags),
        applied_pair_tags=len(result.applied_pair_tags),
        created_entities=len(result.created_entities),
        created_relationships=len(result.created_relationships),
        prose_only_remainders=len(result.prose_only_remainders),
    )


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "get"):
        return row[key]
    return row[index]
