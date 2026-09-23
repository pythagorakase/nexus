"""Pure identity algebra and closed in-scene cue contract for #798."""

import pytest

from nexus.agents.logon.skald_wire import (
    CharacterRef,
    PlaceRef,
    PresenceDelta,
    SceneReset,
)
from nexus.presence.cues import has_scene_cue, promote_in_scene_characters
from nexus.presence.roster import (
    IdentityIndex,
    PresenceRoster,
    RosterEntry,
    apply_delta,
    render_roster,
)

PLAYER = RosterEntry(kind="character", id=1, name="Mara Vey")
GUEST = RosterEntry(kind="character", id=2, name="Len Aster")
HALL = RosterEntry(kind="place", id=1, name="Hall")


def baseline() -> PresenceRoster:
    """Return a physical player and guest, plus a setting with an overlapping ID."""
    return PresenceRoster(
        present={PLAYER.key: PLAYER, GUEST.key: GUEST}, setting={HALL.key: HALL}
    )


def test_roster_keys_ids_before_names() -> None:
    roster = apply_delta(
        baseline(),
        PresenceDelta(exit=[CharacterRef(kind="character", id=2, name="Lantern Fox")]),
    )
    assert roster.present == {PLAYER.key: PLAYER}
    assert roster.setting == {HALL.key: HALL}


def test_roster_rejects_exit_of_nonpresent_identity() -> None:
    with pytest.raises(ValueError, match="Cannot exit non-present"):
        apply_delta(
            baseline(),
            PresenceDelta(
                exit=[CharacterRef(kind="character", id=3, name="Len Aster")]
            ),
        )


def test_roster_resolves_alias_before_exit() -> None:
    index = IdentityIndex(
        [PLAYER, GUEST], [{"character_id": 2, "alias": "Lantern Fox"}]
    )
    result = apply_delta(
        baseline(),
        PresenceDelta(exit=[CharacterRef(kind="character", name="Lantern Fox")]),
        resolve=index.resolve,
    )
    assert result.present == {PLAYER.key: PLAYER}


def test_roster_raises_on_genuine_alias_ambiguity() -> None:
    index = IdentityIndex(
        [PLAYER, GUEST],
        [{"character_id": 1, "alias": "Fox"}, {"character_id": 2, "alias": "Fox"}],
    )
    with pytest.raises(ValueError, match="Ambiguous character name"):
        index.resolve(RosterEntry(kind="character", name="Fox"))
    assert index.resolve(RosterEntry(kind="character", id=2, name="Fox")) == GUEST


def test_roster_silence_carries_physical_scene_not_prior_mentions() -> None:
    roster = baseline()
    absent = RosterEntry(kind="character", id=3, name="Remote Friend")
    roster.referenced[absent.key] = absent
    result = apply_delta(roster, None)
    assert result.present == roster.present
    assert result.setting == roster.setting
    assert result.referenced == {}


def test_roster_reset_replaces_scene_and_separates_transit() -> None:
    result = apply_delta(
        baseline(),
        PresenceDelta(
            scene_reset=SceneReset(
                place=PlaceRef(kind="place", id=3, name="Dock"),
                present=[CharacterRef(kind="character", id=1, name="Mara Vey")],
            ),
            transit=[PlaceRef(kind="place", id=2, name="Lane")],
        ),
    )
    assert set(result.present) == {PLAYER.key}
    assert set(result.setting) == {("place", 3)}
    assert set(result.transitioning) == {("place", 2)}


@pytest.mark.parametrize(
    "prose",
    [
        "Len Aster says, “Wait.”",
        "“Wait,” Len Aster said.",
        "“Wait,” said Len Aster.",
        "Len Aster: “Wait.”",
        "Len Aster waits beneath the balcony.",
        "Rain hits the windows while Len Aster waits beneath the balcony.",
    ],
)
def test_roster_closed_scene_cues(prose: str) -> None:
    assert has_scene_cue(prose, "Len Aster")


@pytest.mark.parametrize(
    "prose",
    [
        "They discuss Len Aster.",
        "She remembers that Len Aster stands at the gate.",
        "Len Aster might enter later.",
        "Len Aster says hello over the radio.",
        "Len Aster walks away.",
        "Nobody knows where Len Aster is.",
    ],
)
def test_roster_mentions_and_remote_or_departing_actions_do_not_promote(
    prose: str,
) -> None:
    assert not has_scene_cue(prose, "Len Aster")


def test_roster_promotion_respects_explicit_departure() -> None:
    end = PresenceRoster(present={PLAYER.key: PLAYER})
    result = promote_in_scene_characters(
        end,
        prose="Len Aster says goodbye.",
        declarations=[],
        character_rows=[GUEST.model_dump()],
        alias_rows=[],
        parent=baseline(),
    )
    assert result.present == end.present


def test_roster_declaration_cue_promotes_only_explicit_placement() -> None:
    for summary, expected in [
        ("Len Aster is present in the scene.", True),
        ("Len Aster is not present in the scene.", False),
    ]:
        result = promote_in_scene_characters(
            PresenceRoster(),
            prose="The liaison arrives.",
            declarations=[
                {"kind": "character", "name": "Len Aster", "summary": summary}
            ],
            character_rows=[GUEST.model_dump()],
            alias_rows=[],
            parent=None,
        )
        assert (GUEST.key in result.present) is expected


def test_roster_render_identifies_canonical_player() -> None:
    assert (
        render_roster(baseline(), player_character_id=1)
        == "PRESENT: Mara Vey (player), Len Aster · SETTING: Hall"
    )


@pytest.mark.parametrize("short,long", [("Ann", "Ann Marie"), ("Ann", "Annabelle")])
def test_roster_longest_name_owns_dialogue_attribution(short: str, long: str) -> None:
    result = promote_in_scene_characters(
        PresenceRoster(),
        prose=f'"Wait," says {long}.',
        declarations=[],
        character_rows=[{"id": 1, "name": short}, {"id": 2, "name": long}],
        alias_rows=[],
        parent=None,
    )
    assert result.present_character_ids == {2}


def test_roster_shared_surname_does_not_steal_full_name_attribution() -> None:
    rows = [{"id": 1, "name": "Ann Smith"}, {"id": 2, "name": "Beth Smith"}]
    aliases = [
        {"character_id": 1, "alias": "Smith"},
        {"character_id": 2, "alias": "Smith"},
    ]
    result = promote_in_scene_characters(
        PresenceRoster(),
        prose='"Wait," says Ann Smith.',
        declarations=[],
        character_rows=rows,
        alias_rows=aliases,
        parent=None,
    )
    assert result.present_character_ids == {1}
    with pytest.raises(ValueError, match="Ambiguous character name"):
        promote_in_scene_characters(
            PresenceRoster(),
            prose='"Wait," says Smith.',
            declarations=[],
            character_rows=rows,
            alias_rows=aliases,
            parent=None,
        )


@pytest.mark.parametrize("alias_collision", [False, True])
def test_roster_resolves_every_crossing_before_algebra(alias_collision: bool) -> None:
    first = RosterEntry(kind="character", id=1, name="Alex")
    second = RosterEntry(
        kind="character", id=2, name="Fox" if alias_collision else "Alex"
    )
    index = IdentityIndex(
        [first, second],
        [{"character_id": 1, "alias": "Fox"}] if alias_collision else [],
    )
    delta = PresenceDelta(
        enter=[CharacterRef(kind="character", id=1, name="Alex")],
        exit=[CharacterRef(kind="character", name=second.name)],
    )
    with pytest.raises(ValueError, match="Ambiguous character name"):
        apply_delta(
            PresenceRoster(present={second.key: second}), delta, resolve=index.resolve
        )
