"""Rearm grammar weight report for issue 781 (work order 781-S1).

The script builds throwaway wire variants that add one ``rearm`` field to the
Orrery adjudication. These tests prove that its baseline reproduces the
production wire bytes, that every variant keeps the strict schema rules, and
that the registry variants reuse the registry's shared enum definitions.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest
from pydantic import BaseModel, ValidationError

from nexus.agents.logon.skald_wire import (
    skald_gaia_lenient_schema,
    skald_gaia_prompt_guide,
    skald_gaia_strict_text_format,
    skald_wire_lenient_schema,
    skald_wire_prompt_guide,
    skald_wire_strict_text_format,
)
from nexus.api.native_structured_output import strict_json_schema
from scripts.qa_shift.rearm_grammar_weight import (
    STATIC_SEATS,
    VARIANTS,
    StaticSeat,
    build_variants,
    compact_json,
    registry_rows,
    registry_variants,
    static_rows,
    surfaces,
)
from tests.pg_fixtures import disposable_slot_database, route_slot_to_disposable

REARM_PAYLOADS: dict[str, Any] = {
    "typed_fields": {"kind": "after_hours", "hours": 6},
    "minimal_typed": {"kind": "after_hours", "argument": "6"},
    "compact_string": "after 6h",
    "package_default": "after 6h",
}


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    """Yield every mapping node of one JSON Schema."""

    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _object_nodes(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every object node of one schema."""

    return [
        node
        for node in _walk(schema)
        if node.get("type") == "object" or isinstance(node.get("properties"), dict)
    ]


def _assert_strict_rules(schema: dict[str, Any]) -> None:
    """Every object is closed and requires all its properties; refs resolve."""

    definitions = schema.get("$defs", {})
    objects = _object_nodes(schema)
    assert objects
    for node in objects:
        assert node.get("additionalProperties") is False, node
        assert node.get("required") == list(node["properties"]), node
    for node in _walk(schema):
        ref = node.get("$ref")
        if isinstance(ref, str):
            assert ref.startswith("#/$defs/"), ref
            assert ref[len("#/$defs/") :] in definitions, ref


def _enum_value_count(schema: dict[str, Any]) -> int:
    """Count every enum value and const of one schema."""

    count = 0
    for node in _walk(schema):
        values = node.get("enum")
        if isinstance(values, list):
            count += len(values)
        elif "const" in node:
            count += 1
    return count


def _refs(node: dict[str, Any]) -> set[str]:
    """Return every ``$ref`` beneath one schema node."""

    return {
        str(nested["$ref"])
        for nested in _walk(node)
        if isinstance(nested, dict) and "$ref" in nested
    }


def _strict_schema(model: type[BaseModel], seat: str) -> dict[str, Any]:
    """Return the strict schema of one variant in its declared key order.

    The measured text sorts keys, so the schema is rebuilt here to compare
    ``required`` against the property order; the two must serialize alike.
    """

    schema = strict_json_schema(model)
    assert compact_json(schema) == surfaces(model, seat)["strict"]
    return schema


def test_baseline_construction_reproduces_production_bytes() -> None:
    """The baseline variant measures exactly the shipped wire surfaces."""

    production: dict[StaticSeat, tuple[dict[str, Any], dict[str, Any], str]] = {
        "gaia": (
            skald_gaia_strict_text_format()["schema"],
            skald_gaia_lenient_schema(),
            skald_gaia_prompt_guide(),
        ),
        "single_pass": (
            skald_wire_strict_text_format()["schema"],
            skald_wire_lenient_schema(),
            skald_wire_prompt_guide(),
        ),
    }
    for seat, (strict, lenient, guide) in production.items():
        measured = surfaces(build_variants(seat)["baseline"], seat)
        assert measured["strict"] == compact_json(strict), seat
        assert measured["lenient"] == compact_json(lenient), seat
        assert measured["guide"] == guide, seat


@pytest.mark.parametrize("seat", STATIC_SEATS)
def test_every_variant_satisfies_strict_schema_rules(seat: StaticSeat) -> None:
    """Each variant keeps strict closure, resolves refs and renders a guide."""

    variants = build_variants(seat)
    assert tuple(variants) == VARIANTS
    for variant, model in variants.items():
        measured = surfaces(model, seat)
        _assert_strict_rules(_strict_schema(model, seat))
        lenient = json.loads(measured["lenient"])
        for node in _object_nodes(lenient):
            assert node.get("additionalProperties") is False, (variant, node)
        rearm_lines = [
            line
            for line in measured["guide"].splitlines()
            if line.startswith("rearm?:")
        ]
        if variant == "baseline":
            assert rearm_lines == []
        else:
            assert len(rearm_lines) == 1, (variant, rearm_lines)


def test_variants_accept_a_defer_with_rearm() -> None:
    """Each rearm variant validates a defer with its rearm; baseline rejects it."""

    variants = build_variants("gaia")
    for variant, rearm in REARM_PAYLOADS.items():
        payload = {
            "letter": "Hold the courier until the storm breaks.",
            "orrery_adjudications": [
                {"proposal_id": "p1", "action": "defer", "rearm": rearm}
            ],
        }
        wire = variants[variant].model_validate(payload)
        adjudication = getattr(wire, "orrery_adjudications")[0]
        assert getattr(adjudication, "rearm") is not None
        with pytest.raises(ValidationError):
            variants["baseline"].model_validate(payload)


def test_rows_and_deltas_are_deterministic() -> None:
    """Static rows cover two seats, three surfaces and five variants."""

    rows = static_rows()
    assert len(rows) == 30
    for row in rows:
        if row.variant == "baseline":
            assert (row.delta_bytes, row.delta_tokens, row.delta_bytes_pct) == (
                0,
                0,
                0.0,
            )
        else:
            assert row.delta_bytes > 0, row
    assert static_rows() == rows


@pytest.mark.requires_postgres
def test_registry_variants_reuse_shared_enums(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registry variants stay strict and type event_type by the shared enum."""

    with disposable_slot_database("qa640_781s1") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        spec, variants = registry_variants(dbname)
        assert tuple(variants) == VARIANTS
        schemas = {
            variant: _strict_schema(model, "gaia_registry")
            for variant, model in variants.items()
        }
        assert (
            schemas["baseline"] == skald_gaia_strict_text_format(spec.model)["schema"]
        )
        baseline_enums = _enum_value_count(schemas["baseline"])
        expected_growth = {
            "baseline": 0,
            "typed_fields": 4,
            "minimal_typed": 4,
            "compact_string": 0,
            "package_default": 0,
        }
        for variant, schema in schemas.items():
            _assert_strict_rules(schema)
            assert (
                _enum_value_count(schema) == baseline_enums + expected_growth[variant]
            ), variant

        definitions = schemas["typed_fields"]["$defs"]
        adjudication = definitions["OrreryAdjudicationRegistry"]["properties"]
        rearm = definitions["OrreryRearm"]["properties"]
        replacement_refs = _refs(adjudication["replacement_event_type"])
        assert replacement_refs == {"#/$defs/EventTypeName"}
        assert _refs(rearm["event_type"]) == replacement_refs
        assert "$ref" not in json.dumps(rearm["tag"])

        digest, rows = registry_rows(dbname)
        assert digest == spec.registry_digest
        assert len(rows) == 5
        assert {row.surface for row in rows} == {"strict"}
        baseline = next(row for row in rows if row.variant == "baseline")
        assert (baseline.delta_bytes, baseline.delta_tokens) == (0, 0)
