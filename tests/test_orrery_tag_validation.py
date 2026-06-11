"""Offline tests for generation-time storyteller Orrery tag validation."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from nexus.agents.logon.apex_schema import (
    CharacterReference,
    CharacterStateUpdate,
    LocationStateUpdate,
    NewCharacter,
    ReferencedEntities,
    ReferenceType,
    StateUpdates,
)
from nexus.agents.logon.orrery_tag_validation import (
    build_storyteller_tag_validator,
    collect_orrery_tag_issues,
)
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal


class FakeRegistryCursor:
    """Cursor stand-in serving a tiny in-memory tag registry."""

    def __init__(self) -> None:
        # tag -> (id, category, is_ephemeral, reapplication_policy)
        self.tags = {
            "human": (1, "bodyform", False, None),
            "perceptive": (2, "disposition", False, None),
            "haven": (3, "place_class", False, None),
        }
        self.categories_by_kind = {
            "character": {"bodyform", "disposition"},
            "place": {"place_class"},
            "faction": {"ideology"},
        }
        self._result: List[Tuple[Any, ...]] = []
        self._one: Optional[Tuple[Any, ...]] = None

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> None:
        if "tag_category_registry" in sql:
            kind = params[0]
            self._result = [
                (category,) for category in sorted(self.categories_by_kind[kind])
            ]
            self._one = None
        elif "FROM tags" in sql:
            row = self.tags.get(params[0])
            self._one = row
            self._result = [row] if row else []
        else:
            raise AssertionError(f"Unexpected query: {sql}")

    def fetchall(self) -> List[Tuple[Any, ...]]:
        return self._result

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        return self._one


def _response(**kwargs: Any) -> Any:
    class _FakeResponse:
        referenced_entities = kwargs.get("referenced_entities")
        state_updates = kwargs.get("state_updates")

    return _FakeResponse()


def test_valid_bestowals_produce_no_issues() -> None:
    response = _response(
        referenced_entities=ReferencedEntities(
            characters=[
                CharacterReference(
                    reference_type=ReferenceType.PRESENT,
                    new_character=NewCharacter(
                        name="Joryn Peale",
                        summary="A frightened junior copyist.",
                        orrery_tags=OrreryTagBestowal(
                            applied_tags=["human", "perceptive"]
                        ),
                    ),
                )
            ]
        ),
    )
    assert collect_orrery_tag_issues(response, FakeRegistryCursor()) == []


def test_composite_tag_names_are_flagged_with_paths() -> None:
    response = _response(
        state_updates=StateUpdates(
            characters=[
                CharacterStateUpdate(
                    character_id=1,
                    character_name="Brena Tideloft",
                    orrery_tags=OrreryTagBestowal(
                        applied_tags=["role.resources:comfortable"]
                    ),
                )
            ],
            locations=[
                LocationStateUpdate(
                    place_id=4,
                    orrery_tags=OrreryTagBestowal(
                        applied_tags=["place_affordance:neutral_ground"]
                    ),
                )
            ],
        ),
    )
    issues = collect_orrery_tag_issues(response, FakeRegistryCursor())
    assert len(issues) == 2
    assert any(issue.startswith("state_updates.characters[0]") for issue in issues)
    assert any(issue.startswith("state_updates.locations[0]") for issue in issues)
    assert all("Unknown or deprecated" in issue for issue in issues)


def test_kind_incompatible_tags_are_flagged() -> None:
    # 'haven' is a place tag; bestowing it on a character must fail.
    response = _response(
        state_updates=StateUpdates(
            characters=[
                CharacterStateUpdate(
                    character_id=1,
                    character_name="Brena Tideloft",
                    orrery_tags=OrreryTagBestowal(applied_tags=["haven"]),
                )
            ],
        ),
    )
    issues = collect_orrery_tag_issues(response, FakeRegistryCursor())
    assert len(issues) == 1
    assert "haven" in issues[0]


def test_validator_skipped_without_slot_database() -> None:
    assert build_storyteller_tag_validator(None) is None
    assert build_storyteller_tag_validator("") is None
    assert build_storyteller_tag_validator("save_05") is not None
