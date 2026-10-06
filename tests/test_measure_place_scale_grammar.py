"""Offline checks of the issue 788 place-scale grammar measurement.

The measured schemas must be the live builders' output, and each variant may
change only what its form adds. Tokens come from the TEST registry entry; no
database connection is opened here.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

import pytest

from nexus.agents.logon import apex_schema, gaia_registry_schema, skald_wire
from nexus.agents.logon.gaia_registry_schema import (
    GaiaRegistryVocabulary,
    gaia_registry_wire_model,
)
from nexus.agents.logon.skald_wire import (
    SkaldTurnWire,
    skald_gaia_strict_text_format,
    skald_wire_strict_text_format,
)
from nexus.agents.orrery.tag_library import _registry_digest
from nexus.api.native_structured_output import openai_response_text_format
from nexus.api.new_story_generator import SetDesignerOutput
from nexus.telemetry.prompt_window import estimator_for
from scripts.measure_place_scale_grammar import (
    SCALE_TAG_NAMES,
    EntryPointMeasurement,
    entry_point_report,
    measure_gaia,
    measure_skald,
    measure_wizard,
)


@pytest.fixture(scope="module")
def count() -> Callable[[str], int]:
    """Return the TEST entry's local token counter."""

    return estimator_for("TEST")


def _without_scale(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove every ``scale`` property, its required entry and ``PlaceScale``."""

    stripped = copy.deepcopy(schema)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict) and "scale" in properties:
                del properties["scale"]
                value["required"] = [
                    name for name in value.get("required", []) if name != "scale"
                ]
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(stripped)
    stripped["$defs"].pop("PlaceScale")
    return stripped


def _scale_owners(value: Any, path: str = "") -> dict[str, dict[str, Any]]:
    """Map the JSON path of each object whose ``properties`` has ``scale``."""

    owners: dict[str, dict[str, Any]] = {}
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict) and "scale" in properties:
            owners[path] = value
        for key, nested in value.items():
            owners.update(_scale_owners(nested, f"{path}/{key}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            owners.update(_scale_owners(nested, f"{path}/{index}"))
    return owners


def _assert_scale_required(owners: dict[str, dict[str, Any]]) -> None:
    for path, owner in owners.items():
        assert "scale" in owner["required"], path


def _schemas(measurement: EntryPointMeasurement) -> dict[str, dict[str, Any]]:
    return {name: form.schema for name, form in measurement.forms.items()}


def test_baselines_are_the_live_formats(count: Callable[[str], int]) -> None:
    assert (
        measure_skald(count).forms["baseline"].schema
        == skald_wire_strict_text_format()["schema"]
    )
    assert (
        measure_wizard(count).forms["baseline"].schema
        == openai_response_text_format(SetDesignerOutput)["schema"]
    )


def test_tag_form_leaves_free_string_wires_unchanged(
    count: Callable[[str], int],
) -> None:
    for measurement in (measure_skald(count), measure_wizard(count)):
        schemas = _schemas(measurement)
        assert schemas["tag_form"] == schemas["baseline"]
        report = entry_point_report(measurement, "TEST")
        assert report["tag_form"]["delta_bytes"] == 0
        assert report["tag_form"]["delta_tokens"] == 0
        assert report["tag_form_changes_grammar"] is False


def test_column_form_is_additive_only(count: Callable[[str], int]) -> None:
    skald = _schemas(measure_skald(count))
    wizard = _schemas(measure_wizard(count))

    assert _without_scale(skald["column_form"]) == skald["baseline"]
    assert _without_scale(wizard["column_form"]) == wizard["baseline"]

    skald_owners = _scale_owners(skald["column_form"])
    assert list(skald_owners) == ["/$defs/NewEntityDeclaration"]
    _assert_scale_required(skald_owners)

    wizard_owners = _scale_owners(wizard["column_form"])
    assert sorted(wizard_owners) == ["/$defs/PlaceProfile", "/properties/location"]
    _assert_scale_required(wizard_owners)

    assert skald["column_form"]["$defs"]["PlaceScale"]["description"] == (
        "Canonical place scale."
    )
    assert not _scale_owners(skald["baseline"])
    assert not _scale_owners(wizard["baseline"])
    assert skald_wire.SkaldTurnWire is SkaldTurnWire
    assert skald_wire_strict_text_format()["schema"] == skald["baseline"]


def test_gaia_forms_on_a_fixed_vocabulary(count: Callable[[str], int]) -> None:
    vocabulary = GaiaRegistryVocabulary(
        character_tags=("guarded", "wounded"),
        place_tags=("haven", "market", "transit"),
        faction_tags=("embattled",),
        pair_tags=("obligation", "protects"),
        event_types=("arrival", "departure"),
    )
    digest = _registry_digest(
        tag_names=[
            *vocabulary.character_tags,
            *vocabulary.place_tags,
            *vocabulary.faction_tags,
        ],
        pair_tag_names=vocabulary.pair_tags,
        event_types=vocabulary.event_types,
    )

    measurement = measure_gaia(vocabulary, digest, count)
    schemas = _schemas(measurement)
    baseline = schemas["baseline"]

    base_enum = baseline["$defs"]["PlaceTagName"]["enum"]
    tag_enum = schemas["tag_form"]["$defs"]["PlaceTagName"]["enum"]
    assert sorted(base_enum) == ["haven", "market", "transit"]
    assert sorted(tag_enum) == sorted([*base_enum, *SCALE_TAG_NAMES])
    restored = copy.deepcopy(schemas["tag_form"])
    restored["$defs"]["PlaceTagName"]["enum"] = base_enum
    assert restored == baseline
    assert measurement.forms["tag_form"].enum_values == (
        measurement.forms["baseline"].enum_values + len(SCALE_TAG_NAMES)
    )

    column = schemas["column_form"]
    assert _without_scale(column) == baseline
    owners = _scale_owners(column)
    assert sorted(owners) == [
        "/$defs/CharacterNewEntityDeclarationRegistry",
        "/$defs/FactionNewEntityDeclarationRegistry",
        "/$defs/PlaceNewEntityDeclarationRegistry",
    ]
    _assert_scale_required(owners)

    assert gaia_registry_schema.NewEntityDeclaration is apex_schema.NewEntityDeclaration
    served = gaia_registry_wire_model(registry_digest=digest, vocabulary=vocabulary)
    assert skald_gaia_strict_text_format(served)["schema"] == baseline
