#!/usr/bin/env python3
"""Measure the strict-grammar weight of the two place-scale forms (issue 788).

The script builds the real OpenAI strict text formats of three entry points
(two-pass Gaia, single-pass Skald, and the wizard set designer) with their live
schema builders, then builds each one again under two stand-in renderings of a
canonical place scale: a place-tag category (five ``scale_*`` tags added to the
place-tag vocabulary) and a typed column (an optional ``scale`` enum field on
the place-bearing models). It prints one JSON document with bytes, tokens and
enum values per form. It reads one slot database through read-only sessions
and changes no product code; it decides nothing.

The scale values are report stand-ins taken from the wording of 788-R1; slice
788-S1 names the real values.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import dataclasses
import json
import logging
import os
import sys
from dataclasses import dataclass
from enum import Enum
from types import ModuleType
from typing import Any, Callable, Iterator, List, Optional, Sequence

import psycopg2
from pydantic import BaseModel, Field, create_model

from nexus.agents.logon import apex_schema, gaia_registry_schema, skald_wire
from nexus.agents.logon.apex_schema import NewEntityDeclaration
from nexus.agents.logon.gaia_registry_schema import (
    GaiaRegistryVocabulary,
    _normalize_vocabulary,
    gaia_registry_wire_model,
    load_gaia_registry_wire_spec,
)
from nexus.agents.logon.skald_wire import (
    SkaldTurnWire,
    skald_gaia_strict_text_format,
    skald_wire_strict_text_format,
)
from nexus.agents.orrery.tag_library import _registry_digest
from nexus.api.native_structured_output import openai_response_text_format
from nexus.api.new_story_generator import SetDesignerOutput
from nexus.api.new_story_schemas import PlaceProfile
from nexus.api.slot_utils import require_slot_dbname
from nexus.config import load_settings
from nexus.config.story_model import resolve_seat
from nexus.database import connection_kwargs
from nexus.telemetry.prompt_window import estimator_for

logger = logging.getLogger(__name__)

SCALE_VALUES = ("room", "building", "site", "district", "settlement")
SCALE_TAG_NAMES = tuple(f"scale_{value}" for value in SCALE_VALUES)

DECLARATION_SCALE_DESCRIPTION = "Place scale; place declarations only."
PLACE_PROFILE_SCALE_DESCRIPTION = "Place scale."
READ_ONLY_OPTION = "-c default_transaction_read_only=on"

SERIALIZATION = (
    'json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))'
)
FORM_NAMES = ("baseline", "tag_form", "column_form")

GAIA_ENTRY_POINT = "gaia_two_pass_openai"
SKALD_ENTRY_POINT = "skald_single_pass_openai"
WIZARD_ENTRY_POINT = "wizard_set_designer_openai"

GAIA_BUILDER = (
    "skald_gaia_strict_text_format(load_gaia_registry_wire_spec(dbname, ...).model)"
    " @ nexus/agents/lore/logon_utility.py:2434"
)
SKALD_BUILDER = (
    "skald_wire_strict_text_format() @ nexus/agents/lore/logon_utility.py:2302"
)
WIZARD_BUILDER = (
    "openai_response_text_format(SetDesignerOutput) @ scripts/api_openai.py:844"
    " via nexus/api/new_story_generator.py:557-560"
)

# The original classes, captured at import, for the rebinding self-check.
_ORIGINAL_NEW_ENTITY_DECLARATION = NewEntityDeclaration
_ORIGINAL_SKALD_TURN_WIRE = SkaldTurnWire


class PlaceScale(str, Enum):
    """Canonical place scale."""

    ROOM = "room"
    BUILDING = "building"
    SITE = "site"
    DISTRICT = "district"
    SETTLEMENT = "settlement"


@dataclass(frozen=True)
class FormMeasurement:
    """One strict schema as sent on the wire, with its measured weight."""

    schema: dict[str, Any]
    wire_text: str
    bytes: int
    tokens: int
    enum_values: int


@dataclass(frozen=True)
class EntryPointMeasurement:
    """One entry point's baseline, tag-form and column-form measurements."""

    name: str
    seat: str
    builder: str
    forms: dict[str, FormMeasurement]


def wire_text(text_format: dict[str, Any]) -> str:
    """Serialize a text format's schema exactly as the Gaia budget test does."""

    return json.dumps(
        text_format["schema"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _all_enum_nodes(value: Any) -> list[dict[str, Any]]:
    """Return every schema node that carries an ``enum`` list."""

    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("enum"), list):
            nodes.append(value)
        for nested in value.values():
            nodes.extend(_all_enum_nodes(nested))
    elif isinstance(value, list):
        for nested in value:
            nodes.extend(_all_enum_nodes(nested))
    return nodes


def measure_form(
    text_format: dict[str, Any], count: Callable[[str], int]
) -> FormMeasurement:
    """Measure one strict text format's schema."""

    schema = text_format["schema"]
    text = wire_text(text_format)
    return FormMeasurement(
        schema=schema,
        wire_text=text,
        bytes=len(text.encode("utf-8")),
        tokens=count(text),
        enum_values=sum(len(node["enum"]) for node in _all_enum_nodes(schema)),
    )


def _with_scale_field(base: type[BaseModel], description: str) -> type[BaseModel]:
    """Return a same-named subclass of ``base`` with an optional ``scale`` field."""

    model: type[BaseModel] = create_model(
        base.__name__,
        __base__=base,
        __module__=base.__module__,
        __doc__=base.__doc__,
        scale=(Optional[PlaceScale], Field(default=None, description=description)),
    )
    return model


def _with_field_type(
    base: type[BaseModel], field_name: str, new_type: Any
) -> type[BaseModel]:
    """Return a same-named subclass of ``base`` retyping one field in place.

    The field keeps a copy of its original ``FieldInfo``, so no description,
    default or constraint is retyped by hand.
    """

    field_definitions: dict[str, Any] = {
        field_name: (new_type, copy.copy(base.model_fields[field_name]))
    }
    model: type[BaseModel] = create_model(
        base.__name__,
        __base__=base,
        __module__=base.__module__,
        __doc__=base.__doc__,
        **field_definitions,
    )
    return model


@contextlib.contextmanager
def _rebound(module: ModuleType, name: str, value: Any) -> Iterator[None]:
    """Bind ``module.name`` to ``value`` and restore the original afterwards."""

    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


def load_gaia_inputs(dbname: str) -> tuple[GaiaRegistryVocabulary, str]:
    """Read the slot's live Gaia vocabulary and its registry digest.

    No scene references are passed, so the grammar has no clear-only enum.
    Raises when the normalized vocabulary does not reproduce the live model or
    when a stand-in scale tag name is already a tag of any kind.
    """

    spec = load_gaia_registry_wire_spec(dbname)
    normalized = _normalize_vocabulary(
        spec.vocabulary.tag_names_by_kind,
        spec.vocabulary,
        scene_clear_only={},
    )
    rebuilt = gaia_registry_wire_model(
        registry_digest=spec.registry_digest,
        vocabulary=normalized,
    )
    if rebuilt is not spec.model:
        raise RuntimeError(
            f"The normalized Gaia vocabulary of {dbname!r} does not reproduce "
            "the live registry model"
        )
    known: set[str] = set(spec.vocabulary.pair_tag_names)
    kinds = set(spec.vocabulary.tag_names_by_kind) | set(
        spec.vocabulary.clearable_tag_names_by_kind
    )
    for kind in kinds:
        known |= spec.vocabulary.clearable_tags(kind)
    collisions = sorted(known & set(SCALE_TAG_NAMES))
    if collisions:
        raise ValueError(
            f"Stand-in scale tag names are already tags in {dbname!r}: {collisions}"
        )
    return normalized, spec.registry_digest


def measure_gaia(
    vocabulary: GaiaRegistryVocabulary,
    registry_digest: str,
    count: Callable[[str], int],
) -> EntryPointMeasurement:
    """Measure the two-pass Gaia registry grammar under both scale forms."""

    baseline = skald_gaia_strict_text_format(
        gaia_registry_wire_model(
            registry_digest=registry_digest,
            vocabulary=vocabulary,
        )
    )

    tag_vocabulary = dataclasses.replace(
        vocabulary,
        place_tags=tuple(sorted(set(vocabulary.place_tags) | set(SCALE_TAG_NAMES))),
    )
    tag_digest = _registry_digest(
        tag_names=[
            *tag_vocabulary.character_tags,
            *tag_vocabulary.place_tags,
            *tag_vocabulary.faction_tags,
        ],
        pair_tag_names=tag_vocabulary.pair_tags,
        event_types=tag_vocabulary.event_types,
    )
    tag_form = skald_gaia_strict_text_format(
        gaia_registry_wire_model(
            registry_digest=tag_digest,
            vocabulary=tag_vocabulary,
        )
    )

    # The cached builder would return the baseline model for these inputs, so
    # the column form calls the uncached builder under the rebound base class.
    declaration = _with_scale_field(NewEntityDeclaration, DECLARATION_SCALE_DESCRIPTION)
    with _rebound(gaia_registry_schema, "NewEntityDeclaration", declaration):
        column_form = skald_gaia_strict_text_format(
            gaia_registry_schema._build_gaia_registry_wire_model(
                registry_digest=registry_digest,
                vocabulary=vocabulary,
            )
        )

    return EntryPointMeasurement(
        name=GAIA_ENTRY_POINT,
        seat="gaia",
        builder=GAIA_BUILDER,
        forms={
            "baseline": measure_form(baseline, count),
            "tag_form": measure_form(tag_form, count),
            "column_form": measure_form(column_form, count),
        },
    )


def measure_skald(count: Callable[[str], int]) -> EntryPointMeasurement:
    """Measure the single-pass Skald grammar under both scale forms."""

    baseline = measure_form(skald_wire_strict_text_format(), count)
    declaration: Any = _with_scale_field(
        NewEntityDeclaration, DECLARATION_SCALE_DESCRIPTION
    )
    turn_wire = _with_field_type(SkaldTurnWire, "new_entities", List[declaration])
    with _rebound(skald_wire, "SkaldTurnWire", turn_wire):
        column_form = skald_wire_strict_text_format()
    return EntryPointMeasurement(
        name=SKALD_ENTRY_POINT,
        seat="skald",
        builder=SKALD_BUILDER,
        forms={
            "baseline": baseline,
            "tag_form": baseline,
            "column_form": measure_form(column_form, count),
        },
    )


def measure_wizard(count: Callable[[str], int]) -> EntryPointMeasurement:
    """Measure the wizard set designer's grammar under both scale forms."""

    baseline = measure_form(openai_response_text_format(SetDesignerOutput), count)
    profile = _with_scale_field(PlaceProfile, PLACE_PROFILE_SCALE_DESCRIPTION)
    column_form = openai_response_text_format(
        _with_field_type(SetDesignerOutput, "location", profile)
    )
    return EntryPointMeasurement(
        name=WIZARD_ENTRY_POINT,
        seat="wizard",
        builder=WIZARD_BUILDER,
        forms={
            "baseline": baseline,
            "tag_form": baseline,
            "column_form": measure_form(column_form, count),
        },
    )


def strip_scale(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` without the column form's additions.

    Removes every ``scale`` property, its ``required`` entry, and the
    ``PlaceScale`` definition.
    """

    stripped = copy.deepcopy(schema)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict) and "scale" in properties:
                del properties["scale"]
                required = value.get("required")
                if isinstance(required, list):
                    value["required"] = [name for name in required if name != "scale"]
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(stripped)
    definitions = stripped.get("$defs")
    if isinstance(definitions, dict):
        definitions.pop("PlaceScale", None)
    return stripped


def _place_tag_enum(schema: dict[str, Any]) -> list[str]:
    return [str(value) for value in schema["$defs"]["PlaceTagName"]["enum"]]


def self_check(measurement: EntryPointMeasurement) -> None:
    """Raise unless each variant changes only what its form adds."""

    baseline = measurement.forms["baseline"].schema
    column = measurement.forms["column_form"].schema
    if strip_scale(column) != baseline:
        raise RuntimeError(
            f"{measurement.name}: the column form changes more than the scale field"
        )
    if measurement.name == GAIA_ENTRY_POINT:
        tag = measurement.forms["tag_form"].schema
        base_enum = _place_tag_enum(baseline)
        tag_enum = _place_tag_enum(tag)
        if len(tag_enum) != len(set(tag_enum)) or set(tag_enum) - set(base_enum) != set(
            SCALE_TAG_NAMES
        ):
            raise RuntimeError(
                "gaia: the tag form's PlaceTagName does not gain exactly "
                f"{SCALE_TAG_NAMES}"
            )
        if not set(base_enum) <= set(tag_enum):
            raise RuntimeError("gaia: the tag form's PlaceTagName lost a tag")
        restored = copy.deepcopy(tag)
        restored["$defs"]["PlaceTagName"]["enum"] = baseline["$defs"]["PlaceTagName"][
            "enum"
        ]
        if restored != baseline:
            raise RuntimeError(
                "gaia: the tag form differs from the baseline outside PlaceTagName"
            )


def check_rebinding_restored() -> None:
    """Raise unless every rebound module attribute holds its original class."""

    if apex_schema.NewEntityDeclaration is not _ORIGINAL_NEW_ENTITY_DECLARATION:
        raise RuntimeError("apex_schema.NewEntityDeclaration was replaced")
    if (
        gaia_registry_schema.NewEntityDeclaration
        is not apex_schema.NewEntityDeclaration
    ):
        raise RuntimeError("gaia_registry_schema.NewEntityDeclaration was not restored")
    if skald_wire.SkaldTurnWire is not _ORIGINAL_SKALD_TURN_WIRE:
        raise RuntimeError("skald_wire.SkaldTurnWire was not restored")


def _form_report(
    form: FormMeasurement, baseline: Optional[FormMeasurement]
) -> dict[str, int]:
    report = {
        "bytes": form.bytes,
        "tokens": form.tokens,
        "enum_values": form.enum_values,
    }
    if baseline is not None:
        report["delta_bytes"] = form.bytes - baseline.bytes
        report["delta_tokens"] = form.tokens - baseline.tokens
    return report


def entry_point_report(
    measurement: EntryPointMeasurement, model: str
) -> dict[str, Any]:
    """Return one entry point's JSON report, without schemas or wire text."""

    baseline = measurement.forms["baseline"]
    return {
        "name": measurement.name,
        "seat": measurement.seat,
        "model": model,
        "builder": measurement.builder,
        "tag_form_changes_grammar": (
            measurement.forms["tag_form"].schema != baseline.schema
        ),
        "baseline": _form_report(baseline, None),
        "tag_form": _form_report(measurement.forms["tag_form"], baseline),
        "column_form": _form_report(measurement.forms["column_form"], baseline),
    }


def _require_read_only_session(dbname: str) -> None:
    """Raise unless a fresh connection to ``dbname`` opens read-only."""

    connection = psycopg2.connect(**connection_kwargs(dbname))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('transaction_read_only')")
            row = cursor.fetchone()
    finally:
        connection.close()
    value = row[0] if row else None
    if value != "on":
        raise RuntimeError(
            f"Sessions on {dbname!r} are not read-only "
            f"(transaction_read_only={value!r})"
        )


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the OpenAI strict-grammar weight of the place-scale tag "
            "and column forms (issue 788). The scale values "
            f"{', '.join(SCALE_VALUES)} are report stand-ins; 788-S1 names "
            "the real values. Read-only; prints one JSON document."
        )
    )
    parser.add_argument(
        "--dbname",
        required=True,
        help="Slot database whose live vocabulary the Gaia grammar reads.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Measure the three entry points and print one JSON report to stdout."""

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr
    )
    args = _parse_args(argv)
    dbname = require_slot_dbname(dbname=args.dbname)

    existing = os.environ.get("PGOPTIONS")
    os.environ["PGOPTIONS"] = (
        f"{existing} {READ_ONLY_OPTION}" if existing else READ_ONLY_OPTION
    )
    _require_read_only_session(dbname)

    settings = load_settings()
    seats = {"gaia": "", "skald": "", "wizard": ""}
    counters: dict[str, Callable[[str], int]] = {}
    for seat in seats:
        resolution = resolve_seat(seat, settings=settings)
        if resolution.provider != "openai":
            raise ValueError(
                f"Seat {seat!r} resolves to {resolution.model!r} on provider "
                f"{resolution.provider!r}; every measured entry point is an "
                "OpenAI wire"
            )
        if not settings.model_entry(resolution.model).tokenizer_encoding:
            raise ValueError(
                f"Seat {seat!r} model {resolution.model!r} declares no "
                "tokenizer_encoding"
            )
        seats[seat] = resolution.model
        counters[seat] = estimator_for(resolution.model, settings=settings)

    vocabulary, registry_digest = load_gaia_inputs(dbname)
    measurements = [
        measure_gaia(vocabulary, registry_digest, counters["gaia"]),
        measure_skald(counters["skald"]),
        measure_wizard(counters["wizard"]),
    ]
    for measurement in measurements:
        self_check(measurement)
    check_rebinding_restored()

    report = {
        "dbname": dbname,
        "read_only_session": True,
        "scale_values": list(SCALE_VALUES),
        "scale_tag_names": list(SCALE_TAG_NAMES),
        "serialization": SERIALIZATION,
        "entry_points": [
            entry_point_report(measurement, seats[measurement.seat])
            for measurement in measurements
        ],
    }
    logger.info("Measured %d entry points on %s", len(measurements), dbname)
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
