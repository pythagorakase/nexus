"""Explicit revelations preserve identity before any acceptance writes."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from nexus.agents.logon.apex_schema import NewEntityDeclaration
from nexus.agents.logon.skald_wire import (
    CharacterRef,
    PresenceBaseline,
    PresenceDelta,
    SkaldTurnWire,
    hydrate_skald_turn,
)
from nexus.api.presence_reconciliation import (
    CharacterRosterRows,
    reconcile_prose_mentions,
)
from nexus.presence.identity import identity_index, validate_character_batch
from nexus.presence.name_reveals import (
    CharacterNameRevealConflict,
    project_name_reveals,
)
from nexus.presence.roster import RosterEntry


OLD = "Unnamed former CP-9 crew member"
NEW = "Anika Sayegh"
QUOTE = "“Anika Sayegh. Test instrumentation. Retired, apparently.”"
NARRATIVE = f"The older witness looks up. {QUOTE} She keeps her timing sheet."


def declaration():
    """Use the QA name-reveal shape with an explicit canonical binding."""
    return {
        "kind": "character",
        "name": NEW,
        "summary": "A timing-sheet witness.",
        "same_as": {"character_id": 3, "previous_name": OLD, "evidence": QUOTE},
    }


def catalog(extra=(), aliases=()):
    """Return a small identity catalog without any database connection."""
    return identity_index(
        [{"id": 3, "entity_id": 9, "name": OLD, "summary": "A witness."}, *extra],
        list(aliases),
    )


def test_reveal_projects_both_names_to_one_id_without_mutating_catalog():
    index = catalog()
    before = deepcopy(index.__dict__)
    projected, reveals = project_name_reveals(
        [declaration()], index, narrative=NARRATIVE
    )
    for name in (OLD, NEW, "Anika", "Sayegh"):
        resolved = projected.resolve(RosterEntry(kind="character", name=name))
        assert (resolved.id, resolved.entity_id, resolved.name) == (3, 9, NEW)
    assert reveals[0].target.name == OLD
    assert index.__dict__ == before
    validate_character_batch([declaration()], index, narrative=NARRATIVE)


@pytest.mark.parametrize("name", [OLD, NEW, "Anika", "Sayegh"])
def test_reveal_cannot_also_declare_the_same_person_for_maturation(name):
    with pytest.raises(CharacterNameRevealConflict, match="also declare"):
        validate_character_batch(
            [
                declaration(),
                {
                    "kind": "character",
                    "name": name,
                    "summary": "Duplicate",
                    "tag_hints": ["human"],
                },
            ],
            catalog(),
            narrative=NARRATIVE,
        )


def test_reveal_does_not_create_colliding_short_alias():
    projected, _ = project_name_reveals(
        [declaration()],
        catalog([{"id": 4, "name": "Anika Stone"}]),
        narrative=NARRATIVE,
    )
    assert not projected.matching_keys("Anika", "character")


@pytest.mark.asyncio
async def test_direct_stub_and_maturation_paths_cannot_bypass_ruling_persistence():
    from nexus.api.db_converters import create_declared_entity_stubs
    from nexus.agents.orrery.retrograde_maturation import (
        enqueue_declared_entity_maturations,
    )

    with pytest.raises(CharacterNameRevealConflict):
        await create_declared_entity_stubs([declaration()], object())
    with pytest.raises(CharacterNameRevealConflict):
        enqueue_declared_entity_maturations(
            object(),
            declarations=[declaration()],
            chunk_id=4,
            raw_text=NARRATIVE,
        )


@pytest.mark.parametrize(
    "case",
    ["missing_id", "stale_name", "choice_only", "no_name", "duplicate", "unchanged"],
)
def test_unsupported_reveal_fails_before_projection(case):
    item = declaration()
    prose = NARRATIVE
    if case == "missing_id":
        item["same_as"]["character_id"] = 99
    elif case == "stale_name":
        item["same_as"]["previous_name"] = "A different witness"
    elif case == "choice_only":
        prose = "She says nothing."
    elif case == "no_name":
        item["same_as"]["evidence"] = "She keeps her timing sheet."
    elif case == "unchanged":
        item["name"] = OLD
        item["same_as"]["evidence"] = prose = OLD
    items = [item, item] if case == "duplicate" else [item]
    with pytest.raises(CharacterNameRevealConflict):
        project_name_reveals(items, catalog(), narrative=prose)


@pytest.mark.parametrize(
    "kind,name,aliases",
    [
        ("character", NEW, ()),
        ("character", "Anika Sayeghh", ()),
        ("character", "A different person", ({"character_id": 4, "alias": NEW},)),
        ("place", NEW, ()),
    ],
)
def test_reveal_never_merges_or_collides_with_another_identity(kind, name, aliases):
    index = catalog([{"id": 4, "kind": kind, "name": name}], aliases)
    with pytest.raises(CharacterNameRevealConflict, match="collides"):
        project_name_reveals([declaration()], index, narrative=NARRATIVE)


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "place"},
        {"tag_hints": ["human"]},
        {"same_as": {"character_id": 0, "previous_name": OLD, "evidence": QUOTE}},
        {"same_as": {"character_id": True, "previous_name": OLD, "evidence": QUOTE}},
        {
            "same_as": {
                "character_id": 3,
                "previous_name": OLD,
                "evidence": QUOTE,
                "guess": True,
            }
        },
    ],
)
def test_ruling_schema_is_closed_character_only_and_identity_only(change):
    with pytest.raises(ValidationError):
        NewEntityDeclaration.model_validate({**declaration(), **change})


def test_name_reveal_reconciles_before_hydration_without_two_people():
    baseline = PresenceBaseline(
        present=[CharacterRef(kind="character", id=3, name=OLD)]
    )
    wire = SkaldTurnWire(
        narrative=NARRATIVE,
        choices=["Stay.", "Leave."],
        letter="Keep her history.",
        new_entities=[NewEntityDeclaration.model_validate(declaration())],
        presence=PresenceDelta(mentions=[CharacterRef(kind="character", name=NEW)]),
    )
    rows = CharacterRosterRows(
        characters=[{"id": 3, "name": OLD, "summary": "A witness."}], aliases=[]
    )
    reconcile_prose_mentions(wire, presence_baseline=baseline, roster_rows=rows)
    response = hydrate_skald_turn(wire, presence_baseline=baseline)
    refs = response.referenced_entities.characters
    assert {ref.character_id for ref in refs} == {3}
    assert {ref.character_name for ref in refs} == {NEW}
    assert rows.characters == [{"id": 3, "name": OLD, "summary": "A witness."}]


def test_choices_cannot_supply_reveal_evidence():
    wire = SkaldTurnWire(
        narrative="The witness remains silent.",
        choices=[QUOTE, "Leave."],
        letter=QUOTE,
        new_entities=[NewEntityDeclaration.model_validate(declaration())],
    )
    with pytest.raises(CharacterNameRevealConflict):
        reconcile_prose_mentions(
            wire,
            presence_baseline=PresenceBaseline(),
            roster_rows=CharacterRosterRows(
                characters=[{"id": 3, "name": OLD, "summary": "A witness."}], aliases=[]
            ),
        )
