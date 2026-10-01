"""Offline checks for the 840-Q4 place-coordinate cost report."""

from __future__ import annotations

import copy
import json
from typing import Any, Callable

import pytest
from pydantic import BaseModel, ValidationError

from nexus.agents.orrery.retrograde_expansion import RetrogradeExpansionWireResponse
from nexus.api.native_structured_output import (
    anthropic_json_schema,
    strict_json_schema,
)
from nexus.api.trait_input_derivation import (
    _DERIVABLE_TRAITS,
    selected_trait_compile_inputs_model,
)
from nexus.config import load_settings
from nexus.telemetry.prompt_window import local_text_counter
from scripts.measure_place_coordinate_costs import grammar_pairs, grammar_weights

FORMS: dict[str, Callable[[type[BaseModel]], dict[str, Any]]] = {
    "strict_json_schema": strict_json_schema,
    "anthropic_json_schema": anthropic_json_schema,
}
POINT = {"lat": 47.6062, "lon": -122.3321}


@pytest.fixture(scope="module")
def count() -> Callable[[str], int]:
    """Count tokens with the report's default model tokenizer."""

    settings = load_settings()
    assert settings.orrery is not None
    model_ref = settings.orrery.retrograde.maturation.model_ref
    assert model_ref is not None
    model = settings.resolve_model_ref(model_ref)
    return local_text_counter(settings.model_entry(model))


def _independent_weight(
    model: type[BaseModel], form: str, count: Callable[[str], int]
) -> dict[str, int]:
    text = json.dumps(
        FORMS[form](model), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {"bytes": len(text.encode("utf-8")), "tokens": count(text)}


def test_baseline_weights_match_the_wire_schemas(
    count: Callable[[str], int],
) -> None:
    """Each baseline is the product model's wire schema, compactly serialized."""

    products: dict[str, type[BaseModel]] = {
        "expansion": RetrogradeExpansionWireResponse,
        "derivation_domain": selected_trait_compile_inputs_model(["domain"]),
        "derivation_all_derivable_traits": selected_trait_compile_inputs_model(
            list(_DERIVABLE_TRAITS)
        ),
    }
    report = grammar_weights(count)

    assert set(report) == set(products)
    for key, product in products.items():
        assert report[key]["baseline_model"] == product.__name__
        for form in FORMS:
            assert report[key]["forms"][form]["baseline"] == _independent_weight(
                product, form, count
            ), (key, form)

    expansion = next(pair for pair in grammar_pairs() if pair.key == "expansion")
    assert expansion.baseline is RetrogradeExpansionWireResponse
    for form in FORMS:
        assert set(FORMS[form](expansion.baseline)["properties"]) == {
            "event_plan",
            "mechanical_plan",
            "project_plan",
            "thread_plan",
            "coverage_notes",
            "coordinates",
        }


def _strip_added_point(
    variant: dict[str, Any], baseline: dict[str, Any], key: str
) -> dict[str, Any]:
    stripped = copy.deepcopy(variant)
    if key == "expansion":
        owner, name = stripped, "new_place_points"
    else:
        owner, name = stripped["$defs"]["DomainTraitInput"], "coordinates"
    assert name in owner["properties"]
    del owner["properties"][name]
    owner["required"].remove(name)
    added_defs = set(stripped["$defs"]) - set(baseline["$defs"])
    assert added_defs, "the variant adds no $defs entry"
    for def_name in added_defs:
        del stripped["$defs"][def_name]
    return stripped


def test_variants_differ_only_by_the_point() -> None:
    """Removing the added point from each variant yields its baseline exactly."""

    pairs = grammar_pairs()
    assert [pair.key for pair in pairs] == [
        "expansion",
        "derivation_domain",
        "derivation_all_derivable_traits",
    ]
    for pair in pairs:
        assert pair.variant.__name__ == pair.baseline.__name__
        assert pair.variant.__doc__ == pair.baseline.__doc__
        assert pair.variant.model_config == pair.baseline.model_config
        for form, build in FORMS.items():
            baseline = build(pair.baseline)
            variant = build(pair.variant)
            assert variant != baseline, (pair.key, form)
            assert _strip_added_point(variant, baseline, pair.key) == baseline, (
                pair.key,
                form,
            )


def test_variants_require_the_point() -> None:
    """Each variant refuses a new place or domain without coordinates."""

    pairs = {pair.key: pair for pair in grammar_pairs()}

    expansion = pairs["expansion"].variant
    with pytest.raises(ValidationError, match="coordinates"):
        expansion.model_validate({"new_place_points": [{"place_ref": "Cinder Vault"}]})
    with pytest.raises(ValidationError, match="new_place_points"):
        expansion.model_validate({})
    accepted = expansion.model_validate(
        {"new_place_points": [{"place_ref": "Cinder Vault", "coordinates": POINT}]}
    )
    assert accepted.model_dump()["new_place_points"] == [
        {"place_ref": "Cinder Vault", "coordinates": POINT}
    ]
    assert (
        expansion.model_validate({"new_place_points": []}).model_dump()[
            "new_place_points"
        ]
        == []
    )

    for key in ("derivation_domain", "derivation_all_derivable_traits"):
        variant = pairs[key].variant
        with pytest.raises(ValidationError, match="coordinates"):
            variant.model_validate({"domain": {"name": "Cinder Vault"}})
        accepted = variant.model_validate(
            {"domain": {"name": "Cinder Vault", "coordinates": POINT}}
        )
        assert accepted.model_dump()["domain"] == {
            "place_id": None,
            "place_entity_id": None,
            "name": "Cinder Vault",
            "coordinates": POINT,
        }
        baseline = pairs[key].baseline
        assert baseline.model_validate({"domain": {"name": "Cinder Vault"}})
