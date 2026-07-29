"""Shared Retrograde project-start dependency validation."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, TypedDict

from nexus.agents.logon.apex_enums import EmotionalValence
from nexus.agents.orrery.retrograde_vocabulary import (
    normalize_entity_ref,
    relationship_type_default_emotional_valence,
)


class ProjectStartRelationship(TypedDict):
    """One directed relationship fact available to an R6 project start."""

    subject_ref: str
    object_ref: str
    emotional_valence: str


_VALENCE_RUNG_BY_LITERAL = {
    valence.value: int(valence.value.split("|", maxsplit=1)[0])
    for valence in EmotionalValence
}
_WARY_RUNG = _VALENCE_RUNG_BY_LITERAL[EmotionalValence.WARY.value]


def is_wary_or_worse(value: str) -> bool:
    """Return whether a canonical authored valence is wary or worse."""

    try:
        rung = _VALENCE_RUNG_BY_LITERAL[str(value)]
    except KeyError as exc:
        raise ValueError(
            "Unrecognized emotional valence "
            f"{value!r}; expected a canonical EmotionalValence ladder literal"
        ) from exc
    return rung <= _WARY_RUNG


def coerce_project_start_relationships(
    value: Any,
) -> list[ProjectStartRelationship]:
    """Validate packet relationship facts used by project-start checks."""

    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("packet.project_start_relationships must be a list")

    facts: list[ProjectStartRelationship] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ValueError(
                "packet.project_start_relationships" f"[{index}] must be a mapping"
            )
        expected = {"subject_ref", "object_ref", "emotional_valence"}
        if set(raw) != expected:
            raise ValueError(
                "packet.project_start_relationships"
                f"[{index}] must contain exactly {sorted(expected)!r}"
            )
        subject_ref = str(raw["subject_ref"]).strip()
        object_ref = str(raw["object_ref"]).strip()
        emotional_valence = str(raw["emotional_valence"]).strip()
        if not subject_ref or not object_ref:
            raise ValueError(
                "packet.project_start_relationships"
                f"[{index}] requires non-empty endpoint refs"
            )
        is_wary_or_worse(emotional_valence)
        facts.append(
            {
                "subject_ref": subject_ref,
                "object_ref": object_ref,
                "emotional_valence": emotional_valence,
            }
        )
    return facts


def planned_project_start_relationships(
    relationship_plans: Iterable[Any],
) -> list[ProjectStartRelationship]:
    """Project R6 relationship rows into directed dependency facts."""

    facts: list[ProjectStartRelationship] = []
    for plan in relationship_plans:
        relationship_type = str(_field(plan, "relationship_type"))
        facts.append(
            {
                "subject_ref": str(_field(plan, "subject_ref")),
                "object_ref": str(_field(plan, "object_ref")),
                "emotional_valence": relationship_type_default_emotional_valence(
                    relationship_type
                ),
            }
        )
    return facts


def dry_run_project_start_relationships(
    relationship_rows: Iterable[Mapping[str, Any]],
) -> list[ProjectStartRelationship]:
    """Project only relationship rows that persistence would materialize."""

    facts: list[ProjectStartRelationship] = []
    for row in relationship_rows:
        status = str(row.get("status"))
        if status == "already_present":
            existing = row.get("existing")
            if not isinstance(existing, Mapping):
                raise AssertionError(
                    "already_present relationship row is missing stored state"
                )
            emotional_valence = str(existing["emotional_valence"])
        elif status == "would_insert":
            emotional_valence = relationship_type_default_emotional_valence(
                str(row["relationship_type"])
            )
        else:
            continue
        facts.append(
            {
                "subject_ref": str(row["subject_ref"]),
                "object_ref": str(row["object_ref"]),
                "emotional_valence": emotional_valence,
            }
        )
    return facts


def seek_redemption_dependency_issue(
    *,
    seed_id: str,
    project_type: str,
    actor_ref: str,
    target_ref: Optional[str],
    relationships: Iterable[Mapping[str, Any]],
) -> Optional[str]:
    """Return the shared seek-redemption prerequisite issue, if any."""

    if project_type != "seek_redemption":
        return None
    if target_ref is None:
        raise AssertionError("seek_redemption target shape was not validated")

    actor_key = normalize_entity_ref(actor_ref)
    target_key = normalize_entity_ref(target_ref)
    for relationship in relationships:
        if (
            normalize_entity_ref(str(relationship["subject_ref"])) == target_key
            and normalize_entity_ref(str(relationship["object_ref"])) == actor_key
            and is_wary_or_worse(str(relationship["emotional_valence"]))
        ):
            return None
    return (
        f"Retrograde project seed {seed_id!r} seek_redemption requires a "
        "TARGET->ACTOR wary-or-worse relationship"
    )


def load_project_start_relationships(
    cur: Any,
    *,
    object_entity_id: Optional[int] = None,
) -> list[ProjectStartRelationship]:
    """Load qualifying directed character relationships for R6 validation."""

    where = ""
    params: tuple[Any, ...] = ()
    if object_entity_id is not None:
        where = "WHERE object_character.entity_id = %s"
        params = (object_entity_id,)
    cur.execute(
        f"""
        /* orrery:retrograde:project_start_relationships */
        SELECT subject_character.name AS subject_ref,
               object_character.name AS object_ref,
               relationship.emotional_valence::text AS emotional_valence
        FROM character_relationships relationship
        JOIN characters subject_character
          ON subject_character.id = relationship.character1_id
        JOIN characters object_character
          ON object_character.id = relationship.character2_id
        {where}
        ORDER BY subject_character.id, object_character.id
        """,
        params,
    )
    facts = coerce_project_start_relationships(
        [
            {
                "subject_ref": _row_value(row, "subject_ref", 0),
                "object_ref": _row_value(row, "object_ref", 1),
                "emotional_valence": _row_value(row, "emotional_valence", 2),
            }
            for row in cur.fetchall()
        ]
    )
    return [fact for fact in facts if is_wary_or_worse(fact["emotional_valence"])]


def _field(value: Any, field: str) -> Any:
    if isinstance(value, Mapping):
        return value[field]
    return getattr(value, field)


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]
