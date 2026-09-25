"""Acceptance validates supplied IDs before applying a character name reveal."""

from copy import deepcopy

import pytest

from nexus.presence.name_reveals import (
    CharacterNameRevealConflict,
    bind_staged_name_reveal_identities,
)
from tests.test_name_reveal_tag_validation import NEW, NARRATIVE, OLD, catalog, output


SITES = ("reference", "departure", "state", "relationship1", "relationship2")


def staged_data(site, identifier, name):
    """Construct the persisted API shapes without involving a provider or DB."""
    data = {
        "storyteller_text": NARRATIVE,
        "new_entities": [item.model_dump() for item in output().new_entities],
        "reference_updates": {"characters": [], "departures": []},
        "entity_updates": {"characters": [], "relationships": []},
    }
    if site in {"reference", "departure", "state"}:
        collection = {
            "reference": data["reference_updates"]["characters"],
            "departure": data["reference_updates"]["departures"],
            "state": data["entity_updates"]["characters"],
        }[site]
        collection.append({"character_id": identifier, "character_name": name})
    else:
        endpoint = int(site[-1])
        other = 3 - endpoint
        data["entity_updates"]["relationships"].append(
            {
                f"character{endpoint}_id": identifier,
                f"character{endpoint}_name": name,
                f"character{other}_id": 4,
                f"character{other}_name": "Someone Else",
                "dynamic": "Shares testimony.",
            }
        )
    return data


def binding(data, site):
    """Read the identity under test from any of the staged collection shapes."""
    if site.startswith("relationship"):
        reference = data["entity_updates"]["relationships"][0]
        prefix = f"character{site[-1]}"
    else:
        reference = {
            "reference": data["reference_updates"].get("characters", []),
            "departure": data["reference_updates"].get("departures", []),
            "state": data["entity_updates"].get("characters", []),
        }[site][0]
        prefix = "character"
    return reference[f"{prefix}_id"], reference[f"{prefix}_name"]


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("name", [OLD, NEW, "Anika"])
@pytest.mark.parametrize("identifier", [None, 3])
def test_staged_old_new_and_unique_aliases_bind_to_same_id(site, name, identifier):
    data = staged_data(site, identifier, name)
    before = deepcopy(data)
    result = bind_staged_name_reveal_identities(data, catalog())
    assert binding(result, site) == (3, name)
    assert data == before


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize(
    "identifier,name", [(4, NEW), (3, "Someone Else"), (3, "Unknown Person")]
)
def test_staged_conflicting_identity_rejected_without_mutation(site, identifier, name):
    data = staged_data(site, identifier, name)
    before = deepcopy(data)
    with pytest.raises(CharacterNameRevealConflict):
        bind_staged_name_reveal_identities(data, catalog())
    assert data == before


@pytest.mark.parametrize("site", [site for site in SITES if site != "state"])
def test_staged_id_only_reference_to_revealed_person_remains_valid(site):
    data = staged_data(site, 3, None)
    assert binding(bind_staged_name_reveal_identities(data, catalog()), site) == (
        3,
        None,
    )


def test_staged_reveal_binding_requires_verified_narrative():
    data = staged_data("reference", None, NEW)
    data["storyteller_text"] = "The witness remains silent."
    with pytest.raises(CharacterNameRevealConflict, match="evidence"):
        bind_staged_name_reveal_identities(data, catalog())


def test_staged_ambiguous_alias_is_not_resolved_by_supplied_id():
    index = catalog()
    for identifier in (3, 4):
        index.labels.append(("character", "Witness", ("character", identifier)))
    with pytest.raises(CharacterNameRevealConflict, match="ambiguous"):
        bind_staged_name_reveal_identities(staged_data("state", 3, "Witness"), index)


def test_staged_unrelated_identity_behavior_is_unchanged():
    data = staged_data("state", 4, "Unknown Person")
    result = bind_staged_name_reveal_identities(data, catalog())
    assert binding(result, "state") == (4, "Unknown Person")
    data["new_entities"] = []
    assert bind_staged_name_reveal_identities(data, catalog()) == data
