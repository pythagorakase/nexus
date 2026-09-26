"""Name revelations must validate updates against the existing person's state."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from nexus.agents.logon.orrery_tag_validation import (
    StorytellerVocabulary,
    name_reveal_update_validation,
    normalize_extend_expiry_reasserts,
)
from nexus.agents.logon.gaia_registry_schema import (
    GaiaRegistryVocabulary,
    coerce_gaia_registry_wire,
    gaia_registry_wire_model,
)
from nexus.agents.logon.skald_wire import SkaldGaiaWire, SkaldTurnWire
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.presence.identity import identity_index
from nexus.presence.name_reveals import CharacterNameRevealConflict


OLD = "Unnamed former CP-9 crew member"
NEW = "Anika Sayegh"
NARRATIVE = 'The witness says, "I am Anika Sayegh."'
TAG = "dying"


def catalog():
    """Return only identities relevant to the no-database validation proof."""
    return identity_index(
        [
            {"id": 3, "entity_id": 9, "name": OLD},
            {"id": 4, "entity_id": 10, "name": "Someone Else"},
        ],
        [],
    )


def output(*, character_id=None, name=NEW):
    """Pair a valid reveal with a tag update using the revealed name."""
    return SkaldGaiaWire.model_validate(
        {
            "new_entities": [
                {
                    "kind": "character",
                    "name": NEW,
                    "summary": "A witness.",
                    "same_as": {
                        "character_id": 3,
                        "previous_name": OLD,
                        "evidence": NARRATIVE,
                    },
                }
            ],
            "updates": {
                "characters": [
                    {
                        "id": character_id,
                        "name": name,
                        "activity": "Holding the timing sheet.",
                        "tags_add": [TAG],
                    }
                ],
                "places": [],
                "factions": [],
                "relationships": [],
            },
            "letter": "Keep her identity and history.",
        }
    )


def vocabulary():
    """Expose a real extend-expiry policy without reading the registry."""
    return StorytellerVocabulary(
        tag_names_by_kind={"character": frozenset({TAG})},
        pair_tag_names=frozenset(),
        event_types=frozenset(),
        tag_reapplication_policies_by_kind={"character": {TAG: "extend_expiry"}},
        tag_clearance_kinds_by_kind={"character": {TAG: "event"}},
    )


class ExistingIdentityCursor:
    """Answer the actual lookup according to its supplied ID/name parameters."""

    def execute(self, _query, params):
        self.params = params

    def fetchall(self):
        _, _, ids, names, *_ = self.params
        id_match = ids[0] == 3
        name_match = names[0] == OLD
        matched = id_match or name_match
        return [
            (
                0,
                9 if id_match else None,
                OLD if id_match else None,
                name_match,
                9 if name_match else None,
                OLD if name_match else None,
                9 if matched else None,
                100 if matched else None,
                None,
                matched,
            )
        ]


@pytest.mark.parametrize("character_id", [None, 3])
@pytest.mark.parametrize("name", [OLD, NEW, "Anika"])
def test_reveal_active_tag_is_noop_on_existing_identity(character_id, name):
    response = output(character_id=character_id, name=name)
    cur = ExistingIdentityCursor()
    issues = []
    with name_reveal_update_validation(response, catalog(), narrative=NARRATIVE):
        normalized = normalize_extend_expiry_reasserts(
            response,
            cur,
            vocabulary=vocabulary(),
            allow_same_turn_declarations=True,
            boundary_issues=issues,
        )
    update = response.updates.characters[0]
    assert cur.params[2:4] == ([3], [OLD])
    assert normalized == 1
    assert issues == []
    assert (update.id, update.name, update.tags_add) == (3, NEW, None)
    assert update.activity == "Holding the timing sheet."


@pytest.mark.parametrize(
    "character_id,name",
    [(4, NEW), (99, NEW), (3, "Someone Else"), (3, "Unknown Person")],
)
def test_reveal_update_rejects_conflicting_ids_without_mutating(character_id, name):
    response = output(character_id=character_id, name=name)
    before = response.model_dump()
    with pytest.raises(CharacterNameRevealConflict):
        with name_reveal_update_validation(response, catalog(), narrative=NARRATIVE):
            pytest.fail("Conflicting identity reached registry validation")
    assert response.model_dump() == before


def test_reveal_update_requires_literal_evidence_before_binding():
    response = output()
    before = response.model_dump()
    with pytest.raises(CharacterNameRevealConflict, match="evidence"):
        with name_reveal_update_validation(response, catalog(), narrative="Silence."):
            pytest.fail("Unverified ruling reached registry validation")
    assert response.model_dump() == before


def test_registry_retry_restores_original_identity():
    response = output(name="Anika")
    before = response.model_dump()
    with pytest.raises(ModelRetry):
        with name_reveal_update_validation(response, catalog(), narrative=NARRATIVE):
            assert response.updates.characters[0].name == OLD
            raise ModelRetry("Retry a different field")
    assert response.model_dump() == before


def test_standalone_validator_does_not_defer_unverified_reveal_as_new_person():
    response = output()
    issues = []
    assert (
        normalize_extend_expiry_reasserts(
            response,
            ExistingIdentityCursor(),
            vocabulary=vocabulary(),
            allow_same_turn_declarations=True,
            boundary_issues=issues,
        )
        == 0
    )
    assert len(issues) == 1
    assert "identity-miss" in issues[0]
    assert response.updates.characters[0].tags_add == [TAG]


@pytest.mark.asyncio
@pytest.mark.parametrize("gaia", [False, True])
@pytest.mark.parametrize("copy_result", [False, True])
async def test_production_guard_binds_before_delegate_and_restores_after(
    monkeypatch, gaia, copy_result
):
    response = output()
    if gaia:
        schema = gaia_registry_wire_model(
            registry_digest="name-reveal-test",
            vocabulary=GaiaRegistryVocabulary(
                character_tags=(TAG,),
                place_tags=("haven",),
                faction_tags=("loyalist",),
                pair_tags=("protects",),
                event_types=("slept",),
            ),
        )
        response = schema.model_validate(response.model_dump())
    else:
        response = SkaldTurnWire(
            **response.model_dump(),
            narrative=NARRATIVE,
            choices=["Stay.", "Leave."],
            presence={
                "scene_reset": {
                    "place": {"kind": "place", "name": "Hall", "id": 1},
                    "present": [{"kind": "character", "name": OLD, "id": 3}],
                },
                "enter": [{"kind": "character", "name": "Anika"}],
            },
        )
    utility = LogonUtility.__new__(LogonUtility)
    utility._window_payload = {}
    utility._validation_dbname = "private-offline-proof"
    utility._active_anchor_chunk_id = None
    monkeypatch.setattr("nexus.api.db_pool.get_connection", lambda _: nullcontext(None))
    monkeypatch.setattr(
        "nexus.presence.identity.read_identity_index", lambda _: catalog()
    )
    seen = []

    async def delegate(_ctx, value):
        if not gaia:
            assert [
                (ref.id, ref.name) for ref in value.presence.scene_reset.present
            ] == [(3, NEW)]
        update = value.updates.characters[0]
        seen.append((update.id, update.name))
        issues = []
        normalize_extend_expiry_reasserts(
            value,
            ExistingIdentityCursor(),
            vocabulary=vocabulary(),
            allow_same_turn_declarations=True,
            boundary_issues=issues,
        )
        assert issues == []
        return value.model_copy(deep=True) if copy_result else value

    provider = SimpleNamespace(output_validator=delegate)
    utility._attach_prompt_window_guard(
        provider,
        "unused request",
        seat="gaia" if gaia else "writer",
        window=32768,
        narrative=NARRATIVE if gaia else None,
    )
    accepted = await provider.output_validator(None, response)
    if gaia:
        accepted = coerce_gaia_registry_wire(accepted)
    assert seen == [(3, OLD)]
    update = accepted.updates.characters[0]
    assert (update.id, update.name, update.tags_add) == (3, NEW, None)
