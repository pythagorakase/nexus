"""Read-only routine-delta grammar weight probe for issue 783 (slice 783-S0).

The probe measures how much one candidate routine-anchor delta would add to the
structured-output grammars that the configured seats send today: the Gaia
registry strict format, the Gaia lenient format and prompt guide, and the
Retrograde strict format for the wizard and maturation seats. It renders each
grammar as it stands (placement ``before``) and with the two 783-Q2 placements
(``sub_object`` and ``top_level_list``), and counts bytes and tokens with each
seat model's registered local tokenizer.

The probe builds no provider client and makes no paid call. It reads one slot
database through sessions whose transactions are read-only by
``default_transaction_read_only=on`` and writes nothing. It reports numbers
only: no threshold, no verdict, no recommendation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import functools
import json
import logging
import os
from typing import Any, Literal, Optional, Sequence, Union, get_args, get_origin

import psycopg2
from pydantic import BaseModel, ConfigDict, Field, create_model

from nexus.agents.logon.gaia_registry_schema import load_gaia_registry_wire_spec

# _render_prompt_guide is the renderer skald_gaia_prompt_guide uses.
from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    _render_prompt_guide,
    skald_gaia_lenient_schema,
    skald_gaia_prompt_guide,
    skald_gaia_strict_text_format,
)
from nexus.agents.lore.logon_utility import (
    present_entity_refs,
    read_presence_baseline,
)
from nexus.agents.orrery.retrograde_expansion import RetrogradeExpansionWireResponse
from nexus.api.native_structured_output import (
    de_null_schema,
    openai_response_text_format,
)
from nexus.config import load_settings
from nexus.config.story_model import read_story_settings, resolve_seat
from nexus.database import connection_kwargs
from nexus.telemetry.prompt_window import estimate_request_tokens

logger = logging.getLogger(__name__)

Placement = Literal["before", "sub_object", "top_level_list"]
PLACEMENTS: tuple[Placement, ...] = ("before", "sub_object", "top_level_list")

GAIA_SEAT = "gaia"
RETROGRADE_SEATS: tuple[str, ...] = (
    "wizard",
    "orrery.retrograde.maturation.model_ref",
)
# Item-3 order: the first seat that fails the provider check is the one named.
MEASURED_SEATS: tuple[str, ...] = (*RETROGRADE_SEATS, GAIA_SEAT)

ANCHOR_TYPE_ENUM = "orrery_routine_anchor_type"
MOBILITY_POLICY_ENUM = "orrery_routine_mobility_policy"

_READ_ONLY_OPTION = "-c default_transaction_read_only=on"


@dataclass(frozen=True)
class RoutineVocabulary:
    """The routine enum labels read from one slot, in ``enumsortorder``."""

    anchor_types: tuple[str, ...]
    mobility_policies: tuple[str, ...]


@dataclass(frozen=True)
class RoutineCandidateModels:
    """The probe's candidate routine models built from one vocabulary."""

    schedule: type[BaseModel]
    body: type[BaseModel]
    delta: type[BaseModel]


@functools.lru_cache(maxsize=None)
def routine_candidate_models(vocabulary: RoutineVocabulary) -> RoutineCandidateModels:
    """Build the candidate routine models for one enum vocabulary.

    These are a measuring instrument, not the contract. ``RoutineSchedule``
    holds authored timing; ``RoutineAnchorBody`` is one anchor change without
    a character; ``RoutineAnchorDelta`` adds the character name. The models
    carry no class docstring, so the only text they add to a rendering is the
    field descriptions from work order 783-S0.
    """

    if not vocabulary.anchor_types:
        raise ValueError(f"Enum {ANCHOR_TYPE_ENUM} has no labels")
    if not vocabulary.mobility_policies:
        raise ValueError(f"Enum {MOBILITY_POLICY_ENUM} has no labels")
    anchor_type: Any = Literal.__getitem__(vocabulary.anchor_types)
    mobility_policy: Any = Literal.__getitem__(vocabulary.mobility_policies)
    forbid = ConfigDict(extra="forbid")

    schedule: type[BaseModel] = create_model(
        "RoutineSchedule",
        __config__=forbid,
        __module__=__name__,
        always=(
            bool,
            Field(description="True when the routine is due at every hour."),
        ),
        weekdays=(
            list[int],
            Field(description="Days the routine applies, 0=Monday through 6=Sunday."),
        ),
        start=(str, Field(description="Local start time, HH:MM.")),
        end=(
            str,
            Field(
                description=(
                    "Local end time, HH:MM; earlier than start for an overnight "
                    "window."
                )
            ),
        ),
    )
    body: type[BaseModel] = create_model(
        "RoutineAnchorBody",
        __config__=forbid,
        __module__=__name__,
        anchor_type=(anchor_type, Field(description="Which routine anchor changes.")),
        mobility_policy=(
            mobility_policy,
            Field(
                description=(
                    "How the routine moves the character; none records an "
                    "authored absence."
                )
            ),
        ),
        place=(
            Optional[str],
            Field(
                default=None,
                description="Canonical place name for fixed_place; null otherwise.",
            ),
        ),
        zone=(
            Optional[str],
            Field(
                default=None,
                description="Canonical zone name for zone_resolved; null otherwise.",
            ),
        ),
        schedule=(
            Optional[schedule],  # type: ignore[valid-type]
            Field(
                default=None,
                description="Authored timing; null when the timing is unknown.",
            ),
        ),
        clear=(bool, Field(default=False, description="True removes this anchor.")),
    )
    delta: type[BaseModel] = create_model(
        "RoutineAnchorDelta",
        __base__=body,
        __module__=__name__,
        character=(
            str,
            Field(min_length=1, description="Canonical character name."),
        ),
    )
    return RoutineCandidateModels(schedule=schedule, body=body, delta=delta)


def _model_arg(annotation: Any, field: str) -> type[BaseModel]:
    """Return the one model class inside a field's ``Optional`` or ``list`` type."""

    models = [
        arg
        for arg in get_args(annotation)
        if isinstance(arg, type) and issubclass(arg, BaseModel)
    ]
    if len(models) != 1:
        raise RuntimeError(
            f"Field {field!r} does not wrap exactly one model: {annotation!r}"
        )
    return models[0]


def _substitute(annotation: Any, old: type[BaseModel], new: type[BaseModel]) -> Any:
    """Rebuild an ``Optional[old]`` or ``list[old]`` annotation around ``new``."""

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Union:
        return Union.__getitem__(tuple(new if arg is old else arg for arg in args))
    if origin is list and args == (old,):
        return list[new]  # type: ignore[valid-type]
    raise RuntimeError(f"Unsupported field annotation for substitution: {annotation!r}")


def _redeclared(base: type[BaseModel], field: str, new_type: Any) -> tuple[Any, Any]:
    """Re-declare one base field with a new type, keeping description and default."""

    info = base.model_fields[field]
    if info.default_factory is not None:
        return (
            new_type,
            Field(default_factory=info.default_factory, description=info.description),
        )
    default = ... if info.is_required() else info.default
    return (new_type, Field(default, description=info.description))


def _derive(base: type[BaseModel], **fields: Any) -> type[BaseModel]:
    """Derive one class that renders as ``base`` except for ``fields``."""

    return create_model(
        base.__name__,
        __base__=base,
        __module__=base.__module__,
        __doc__=base.__doc__,
        **fields,
    )


def gaia_variant(
    model: type[SkaldGaiaWire],
    placement: Placement,
    *,
    vocabulary: Optional[RoutineVocabulary] = None,
) -> type[SkaldGaiaWire]:
    """Derive the static or registry Gaia wire with one routine placement.

    The updates class and the character-update class are found by walking
    ``model_fields`` with ``typing.get_args``. Every placement derives the
    same chain (character update, updates block, Gaia wire); ``before`` adds
    no field, ``sub_object`` adds ``routine`` to the character update, and
    ``top_level_list`` adds a required ``routines`` list to the updates block.
    ``vocabulary`` supplies the slot's enum labels and is required for every
    placement except ``before``.
    """

    if placement not in PLACEMENTS:
        raise ValueError(f"Unknown placement {placement!r}")
    if placement != "before" and vocabulary is None:
        raise ValueError(f"Placement {placement!r} requires the routine vocabulary")
    updates_annotation = model.model_fields["updates"].annotation
    updates_cls = _model_arg(updates_annotation, "updates")
    characters_annotation = updates_cls.model_fields["characters"].annotation
    character_cls = _model_arg(characters_annotation, "characters")

    character_fields: dict[str, Any] = {}
    updates_fields: dict[str, Any] = {}
    if placement == "sub_object":
        assert vocabulary is not None
        candidates = routine_candidate_models(vocabulary)
        character_fields["routine"] = (
            Optional[candidates.body],  # type: ignore[name-defined]
            Field(
                default=None,
                description="Routine anchor change for this character.",
            ),
        )
    elif placement == "top_level_list":
        assert vocabulary is not None
        candidates = routine_candidate_models(vocabulary)
        updates_fields["routines"] = (
            list[candidates.delta],  # type: ignore[name-defined]
            Field(description="Routine anchor changes."),
        )

    derived_character = _derive(character_cls, **character_fields)
    derived_updates = _derive(
        updates_cls,
        characters=_redeclared(
            updates_cls,
            "characters",
            _substitute(characters_annotation, character_cls, derived_character),
        ),
        **updates_fields,
    )
    derived_gaia = _derive(
        model,
        updates=_redeclared(
            model,
            "updates",
            _substitute(updates_annotation, updates_cls, derived_updates),
        ),
    )
    return derived_gaia  # type: ignore[return-value]


def retrograde_variant(
    placement: Placement,
    *,
    vocabulary: Optional[RoutineVocabulary] = None,
) -> type[BaseModel]:
    """Derive the Retrograde wire response with one routine placement.

    Both 783-Q2 placements add the same ``routine_plan`` list, with no
    description like its sibling lists; ``before`` adds no field.
    ``vocabulary`` is required for every placement except ``before``.
    """

    if placement not in PLACEMENTS:
        raise ValueError(f"Unknown placement {placement!r}")
    if placement == "before":
        return _derive(RetrogradeExpansionWireResponse)
    if vocabulary is None:
        raise ValueError(f"Placement {placement!r} requires the routine vocabulary")
    candidates = routine_candidate_models(vocabulary)
    return _derive(
        RetrogradeExpansionWireResponse,
        routine_plan=(
            list[candidates.delta],  # type: ignore[name-defined]
            Field(default_factory=_empty_list),
        ),
    )


def _empty_list() -> list[Any]:
    """Return a fresh empty list for a ``default_factory``."""

    return []


def _dumps(value: Any) -> str:
    """Serialize one rendering exactly as the byte count measures it."""

    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _require_same(label: str, derived: Any, production: Any) -> None:
    """Raise unless a derived rendering equals production byte for byte."""

    if _dumps(derived).encode("utf-8") != _dumps(production).encode("utf-8"):
        raise RuntimeError(
            f"Null-variant self-check failed: {label} differs from production"
        )


def _gaia_lenient_schema(model: type[SkaldGaiaWire]) -> dict[str, Any]:
    """Return the lenient Gaia schema for one derived model."""

    return de_null_schema(model.model_json_schema())  # type: ignore[no-any-return]


def gaia_lenient_format(model: type[SkaldGaiaWire]) -> dict[str, Any]:
    """Return the local-wire text format for one derived Gaia model."""

    return openai_response_text_format(model, schema=_gaia_lenient_schema(model))


def gaia_prompt_guide(model: type[SkaldGaiaWire]) -> str:
    """Return the Anthropic prompted-transport guide for one derived Gaia model."""

    return _render_prompt_guide(
        _gaia_lenient_schema(model),
        include_descriptions=False,
    )


def self_check(registry_model: type[SkaldGaiaWire]) -> None:
    """Prove that placement ``before`` reproduces every production rendering."""

    _require_same(
        "gaia_registry_strict",
        skald_gaia_strict_text_format(gaia_variant(registry_model, "before")),
        skald_gaia_strict_text_format(registry_model),
    )
    static_before = gaia_variant(SkaldGaiaWire, "before")
    _require_same(
        "gaia_lenient schema",
        _gaia_lenient_schema(static_before),
        skald_gaia_lenient_schema(),
    )
    _require_same(
        "gaia_lenient",
        gaia_lenient_format(static_before),
        openai_response_text_format(SkaldGaiaWire, schema=skald_gaia_lenient_schema()),
    )
    _require_same(
        "gaia_prompt_guide",
        gaia_prompt_guide(static_before),
        skald_gaia_prompt_guide(),
    )
    _require_same(
        "retrograde_strict",
        openai_response_text_format(retrograde_variant("before")),
        openai_response_text_format(RetrogradeExpansionWireResponse),
    )


def _read_slot_facts(
    dbname: str, anchor_chunk_id: int
) -> tuple[Any, RoutineVocabulary]:
    """Prove the session is read-only, then read migration level and enums.

    Raises ``RuntimeError`` unless ``transaction_read_only`` is ``on``, and
    ``ValueError`` when the anchor chunk does not exist.
    """

    conn = psycopg2.connect(**connection_kwargs(dbname))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('transaction_read_only')")
            row = cur.fetchone()
            read_only = row[0] if row else None
            if read_only != "on":
                raise RuntimeError(
                    f"routine_delta_grammar_probe requires a read-only session on "
                    f"{dbname!r}; transaction_read_only={read_only!r}. Set "
                    f"PGOPTIONS='{_READ_ONLY_OPTION}'."
                )
            cur.execute("SELECT max(version) FROM schema_migrations")
            migration_row = cur.fetchone()
            migration_level = migration_row[0] if migration_row else None
            labels: dict[str, tuple[str, ...]] = {}
            for enum_name in (ANCHOR_TYPE_ENUM, MOBILITY_POLICY_ENUM):
                cur.execute(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = %s ORDER BY e.enumsortorder",
                    (enum_name,),
                )
                labels[enum_name] = tuple(label for (label,) in cur.fetchall())
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM narrative_chunks WHERE id = %s)",
                (anchor_chunk_id,),
            )
            exists_row = cur.fetchone()
            if not exists_row or not exists_row[0]:
                raise ValueError(
                    f"Anchor chunk {anchor_chunk_id} does not exist in "
                    f"{dbname}.narrative_chunks"
                )
        conn.rollback()
    finally:
        conn.close()
    vocabulary = RoutineVocabulary(
        anchor_types=labels[ANCHOR_TYPE_ENUM],
        mobility_policies=labels[MOBILITY_POLICY_ENUM],
    )
    return migration_level, vocabulary


def _resolve_seats(dbname: str) -> dict[str, dict[str, str]]:
    """Resolve the measured seats; raise unless each is on OpenAI with enums."""

    settings = load_settings()
    story = read_story_settings(dbname)
    seats: dict[str, dict[str, str]] = {}
    for seat in MEASURED_SEATS:
        resolution = resolve_seat(seat, settings=settings, story=story)
        if resolution.provider != "openai":
            raise ValueError(
                f"Seat {seat!r} resolves to model {resolution.model!r} on provider "
                f"{resolution.provider!r}; the probe measures OpenAI grammars only"
            )
        seats[seat] = {
            "seat": seat,
            "model": resolution.model,
            "provider": resolution.provider,
            "source": resolution.source,
        }
    if not settings.apex.tag_library.schema_enums:
        raise ValueError(
            "[apex.tag_library] schema_enums is false: the configured Gaia "
            "grammar would not be the registry model"
        )
    return seats


def _byte_count(rendering: Any) -> int:
    """Return the UTF-8 length of one rendering."""

    return len(_dumps(rendering).encode("utf-8"))


def _row(
    surface: str,
    seat: str,
    model: str,
    placement: Placement,
    rendering: Any,
) -> dict[str, Any]:
    """Return one measured row without its deltas."""

    request: dict[str, Any] = (
        {"instructions": rendering}
        if isinstance(rendering, str)
        else {"text": {"format": rendering}}
    )
    return {
        "surface": surface,
        "seat": seat,
        "model": model,
        "placement": placement,
        "bytes": _byte_count(rendering),
        "tokens": estimate_request_tokens(model, request),
    }


def _with_deltas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add each row's difference from the ``before`` row of its surface and seat."""

    before = {
        (row["surface"], row["seat"]): row
        for row in rows
        if row["placement"] == "before"
    }
    measured: list[dict[str, Any]] = []
    for row in rows:
        base = before[(row["surface"], row["seat"])]
        measured.append(
            {
                **row,
                "delta_bytes": row["bytes"] - base["bytes"],
                "delta_tokens": row["tokens"] - base["tokens"],
            }
        )
    return measured


def measure(dbname: str, anchor_chunk_id: int) -> dict[str, Any]:
    """Measure routine-delta grammar weight on one slot at one anchor chunk.

    Raises ``RuntimeError`` unless the session is read-only or when the
    ``before`` self-check fails, and ``ValueError`` for a missing anchor chunk,
    a seat off OpenAI, or registry enums switched off.
    """

    migration_level, vocabulary = _read_slot_facts(dbname, anchor_chunk_id)
    seats = _resolve_seats(dbname)

    baseline = read_presence_baseline(dbname, anchor_chunk_id)
    spec = load_gaia_registry_wire_spec(
        dbname,
        scene_entity_refs=present_entity_refs(dbname, baseline),
        anchor_chunk_id=anchor_chunk_id,
    )
    self_check(spec.model)

    gaia_model = seats[GAIA_SEAT]["model"]
    rows: list[dict[str, Any]] = []
    for placement in PLACEMENTS:
        registry_variant = gaia_variant(spec.model, placement, vocabulary=vocabulary)
        rows.append(
            _row(
                "gaia_registry_strict",
                GAIA_SEAT,
                gaia_model,
                placement,
                skald_gaia_strict_text_format(registry_variant),
            )
        )
    static_variants = {
        placement: gaia_variant(SkaldGaiaWire, placement, vocabulary=vocabulary)
        for placement in PLACEMENTS
    }
    for placement in PLACEMENTS:
        rows.append(
            _row(
                "gaia_lenient",
                GAIA_SEAT,
                gaia_model,
                placement,
                gaia_lenient_format(static_variants[placement]),
            )
        )
    for placement in PLACEMENTS:
        rows.append(
            _row(
                "gaia_prompt_guide",
                GAIA_SEAT,
                gaia_model,
                placement,
                gaia_prompt_guide(static_variants[placement]),
            )
        )
    for seat in RETROGRADE_SEATS:
        for placement in PLACEMENTS:
            rows.append(
                _row(
                    "retrograde_strict",
                    seat,
                    seats[seat]["model"],
                    placement,
                    openai_response_text_format(
                        retrograde_variant(placement, vocabulary=vocabulary)
                    ),
                )
            )
    logger.info(
        "Measured %d rows on %s at chunk %d", len(rows), dbname, anchor_chunk_id
    )
    return {
        "dbname": dbname,
        "anchor_chunk_id": anchor_chunk_id,
        "migration_level": migration_level,
        "registry_digest": spec.registry_digest,
        "presence_baseline": baseline.model_dump(mode="json"),
        "seats": [seats[seat] for seat in MEASURED_SEATS],
        "rows": _with_deltas(rows),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render one header line and one table of the measured rows."""

    lines = [
        (
            f"Database `{report['dbname']}`, anchor chunk "
            f"{report['anchor_chunk_id']}, registry digest "
            f"`{report['registry_digest']}`, migration level "
            f"{report['migration_level']}"
        ),
        "",
        "| Surface | Seat | Model | Placement | Bytes | Tokens | Δ Bytes | Δ Tokens |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['surface']} | {row['seat']} | {row['model']} | "
            f"{row['placement']} | {row['bytes']:,} | {row['tokens']:,} | "
            f"{row['delta_bytes']:+,} | {row['delta_tokens']:+,} |"
        )
    return "\n".join(lines) + "\n"


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    """Parse the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbname", required=True, help="Slot database to read.")
    parser.add_argument(
        "--anchor-chunk",
        type=int,
        required=True,
        help="Anchor chunk id whose presence scopes the Gaia grammar.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print the Markdown table instead of JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Measure one slot and print the report to stdout."""

    os.environ["PGOPTIONS"] = (
        f"{os.environ.get('PGOPTIONS', '')} {_READ_ONLY_OPTION}".strip()
    )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args(argv)
    report = measure(args.dbname, args.anchor_chunk)
    if args.markdown:
        print(render_markdown(report), end="")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
