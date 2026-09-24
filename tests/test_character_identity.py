"""Pure catalog resolution and collision-free alias policy proofs."""

import pytest

from nexus.config import load_settings
from nexus.presence.identity import generated_aliases, resolve_character_declaration
from nexus.presence.roster import IdentityIndex, RosterEntry


def catalog(*names, aliases=()):
    return IdentityIndex(
        [
            RosterEntry(kind="character", id=i, name=name)
            for i, name in enumerate(names, 1)
        ],
        aliases,
    )


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Silas Wren", "resolved"),
        ("Fox", "resolved"),
        ("Silas Wrenn", "ambiguous"),
        ("Juniper Moss", "novel"),
    ],
)
def test_identity_exact_alias_fuzzy_novel(name, expected):
    index = catalog("Silas Wren", aliases=[{"character_id": 1, "alias": "Fox"}])
    result = resolve_character_declaration({"name": name}, index)
    assert result.status == expected
    if expected == "resolved":
        assert result.existing_id == 1


@pytest.mark.parametrize(
    "names,alias,name",
    [
        (("Silas Wren", "Ada Wren"), None, "Wren"),
        (("Silas", "SILAS"), None, "Silas"),
        (("Silas Wren", "Fox"), "Fox", "Fox"),
    ],
)
def test_identity_collisions_never_choose(names, alias, name):
    index = catalog(
        *names, aliases=[{"character_id": 1, "alias": alias}] if alias else []
    )
    result = resolve_character_declaration(
        {"name": name}, index, descriptors="Only one lives here", scene_location="Hall"
    )
    assert result.status == "ambiguous"
    assert {entry.id for entry in result.candidates} == {1, 2}


def test_identity_generated_aliases_withheld_for_family_and_authored_names():
    index = catalog(
        "Dr. Silas Wren",
        "Ada Wren",
        "Silas",
        aliases=[{"character_id": 3, "alias": "Ada"}],
    )
    aliases = generated_aliases(index)
    assert (1, "Dr. Wren") in aliases
    assert not any(alias in {"Wren", "Silas", "Ada"} for _, alias in aliases)


def test_identity_case_folding_configuration():
    cfg = load_settings().character_identity.model_copy(update={"case_folding": False})
    index = catalog("Silas Wren")
    assert (
        resolve_character_declaration(
            {"name": "Silas Wren"}, index, settings=cfg
        ).status
        == "resolved"
    )
    assert (
        resolve_character_declaration(
            {"name": "SILAS WREN"}, index, settings=cfg
        ).status
        != "resolved"
    )


def test_identity_evidence_narrows_but_never_resolves_collision():
    index = IdentityIndex(
        [
            RosterEntry(kind="character", id=1, name="Silas Wren"),
            RosterEntry(kind="character", id=2, name="Ada Wren"),
        ],
        evidence={
            ("character", 1): {"role": "medic", "current_location": "Hall"},
            ("character", 2): {"role": "pilot", "current_location": "Garden"},
        },
    )
    result = resolve_character_declaration({"name": "Wren", "role": "medic"}, index)
    assert result.status == "ambiguous"
    assert [candidate.id for candidate in result.candidates] == [1]
    result = resolve_character_declaration(
        {"name": "Silas Wren"}, index, scene_location="Garden"
    )
    assert result.status == "ambiguous"
    assert result.reason.startswith("location conflict")


def test_identity_same_name_different_kind_needs_review():
    index = IdentityIndex([RosterEntry(kind="faction", id=1, name="The Bell")])
    assert (
        resolve_character_declaration(
            {"kind": "character", "name": "The Bell"}, index
        ).status
        == "ambiguous"
    )


@pytest.mark.parametrize(
    "catalog_name,declared", [("Ada", "Lady Ada"), ("Lady Ada", "Ada")]
)
def test_identity_title_normalization_is_symmetric(catalog_name, declared):
    result = resolve_character_declaration({"name": declared}, catalog(catalog_name))
    assert result.status == "ambiguous"
    assert result.candidates[0].name == catalog_name


def test_identity_title_alias_and_diacritic_normalization():
    cfg = load_settings().character_identity.model_copy(
        update={"strip_diacritics": True}
    )
    index = catalog("Ada Lovelace", aliases=[{"character_id": 1, "alias": "Áda"}])
    assert (
        resolve_character_declaration({"name": "Lady Ada"}, index, settings=cfg).status
        == "ambiguous"
    )
    cfg = cfg.model_copy(update={"strip_titles": False})
    assert (
        resolve_character_declaration({"name": "Lady Ada"}, index, settings=cfg).status
        == "novel"
    )
