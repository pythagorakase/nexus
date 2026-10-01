"""Measure what a required point costs for later place stubs (issue 840, 840-Q4).

The owner ruled that every later place stub must carry coordinates. This
report measures two ways to meet the ruling and recommends neither:

- extra fields in the model replies that already create the place (the
  Retrograde expansion grammar and the trait-derivation grammar), measured as
  throwaway Pydantic variants built inside this script; and
- a separate structured call per new place (``author_place_coordinates``),
  measured as its rendered prompt plus the schema form it sends.

It also counts the place rows each ``--dbname`` holds, split into genesis rows
and later rows, and attributes each later row to the turn (chunk) that made
it. Row and chunk times order the rows only; they are never story time.

The script calls no provider and changes no product code. Databases are read
through ``open_read_only_connection`` (read-only, repeatable-read sessions).
It prints one JSON document to stdout and nothing else there.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import sys
from typing import Any, Callable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, create_model

from nexus.agents.logon.apex_schema import Coordinates
from nexus.agents.orrery.geo_authoring import (
    GeoAuthoringResponse,
    render_geo_authoring_prompt,
)
from nexus.agents.orrery.retrograde_expansion import RetrogradeExpansionWireResponse
from nexus.agents.orrery.retrograde_persistence import (
    MATURATION_EVENT_REF_PATTERN,
    RETROGRADE_SOURCE_KIND,
)
from nexus.agents.orrery.retrograde_vocabulary import EntityRef
from nexus.api.native_structured_output import (
    anthropic_json_schema,
    strict_json_schema,
)
from nexus.api.trait_compiler import TRAIT_COMPILER_SOURCE
from nexus.api.trait_compiler_schemas import (
    DomainTraitInput,
    TraitCompileInputs,
    canonical_trait_name,
)
from nexus.api.trait_input_derivation import (
    _DERIVABLE_TRAITS,
    selected_trait_compile_inputs_model,
)
from nexus.config import get_openai_compatible_endpoint, load_settings
from nexus.config.settings_models import OrrerySettings, Settings
from nexus.telemetry.prompt_window import local_text_counter
from scripts.database_targets import metrics_dbname
from scripts.entity_reference_parity import open_read_only_connection

logger = logging.getLogger("scripts.measure_place_coordinate_costs")

SCHEMA_FORMS: dict[str, Callable[[type[BaseModel]], dict[str, Any]]] = {
    "strict_json_schema": strict_json_schema,
    "anthropic_json_schema": anthropic_json_schema,
}
SAMPLE_LAT = 47.6062
SAMPLE_LON = -122.3321
FIXTURE_PLACE_NAME = "Fixture Place"
SOURCE_NONE = "none"
SERIALIZATION = (
    'json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))'
)
TRANSPORT_FRAMING_NOTE = (
    "Transport framing (request envelope, message roles, response_format or "
    "tool wrappers) is not counted; figures are compact JSON schema and "
    "rendered prompt text only."
)
BATCH_CALL_NOTE = (
    "A batch call (840-Q4: 'once per new place or batch') is not measured "
    "because no batch grammar exists."
)
REQUEST_FORMULA = (
    "2 x tokens(render_geo_authoring_prompt(...)) + schema tokens of "
    "request_schema_form; the prompt is sent as both the system prompt and "
    "the user prompt"
)


class NewPlacePoint(BaseModel):
    """A new place this plan introduces, with its real-Earth point."""

    place_ref: EntityRef = Field(description="Prompt-local name of the new place.")
    coordinates: Coordinates = Field(
        description="Plausible real-Earth point for the place."
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


ExpansionWithPlacePoints: type[BaseModel] = create_model(
    "RetrogradeExpansionWireResponse",
    __base__=RetrogradeExpansionWireResponse,
    __doc__=RetrogradeExpansionWireResponse.__doc__,
    new_place_points=(
        list[NewPlacePoint],
        Field(
            description=(
                "Every place this plan names that is not a known entity, each "
                "with its real-Earth point; empty when it names none."
            )
        ),
    ),
)

DomainTraitInputWithPoint: type[BaseModel] = create_model(
    "DomainTraitInput",
    __base__=DomainTraitInput,
    __doc__=DomainTraitInput.__doc__,
    coordinates=(
        Coordinates,
        Field(description="Plausible real-Earth point for the claimed place."),
    ),
)


def selected_variant_model(selected: Sequence[str]) -> type[BaseModel]:
    """Build the selected-trait model as the product does, with a pointed Domain.

    Mirrors ``selected_trait_compile_inputs_model`` (same name, same config,
    same field order and defaults); only the ``domain`` annotation becomes
    ``Optional[DomainTraitInputWithPoint]``.
    """

    fields: dict[str, tuple[Any, None]] = {}
    for trait in selected:
        canonical = canonical_trait_name(trait)
        if canonical not in _DERIVABLE_TRAITS:
            raise ValueError(f"Cannot derive unknown trait input field: {trait!r}")
        annotation = TraitCompileInputs.model_fields[canonical].annotation
        if canonical == "domain":
            annotation = Optional[DomainTraitInputWithPoint]  # type: ignore[assignment]
        fields[canonical] = (annotation, None)

    suffix = "".join(part.title() for part in fields) or "Empty"
    model: type[BaseModel] = create_model(
        f"TraitCompileInputsSelected{suffix}",
        __config__=ConfigDict(str_strip_whitespace=True, extra="forbid"),
        **fields,  # type: ignore[call-overload]
    )
    return model


@dataclass(frozen=True)
class GrammarPair:
    """One grammar measured as a product baseline and a script variant."""

    key: str
    baseline: type[BaseModel]
    variant: type[BaseModel]
    added_field: str


def grammar_pairs() -> list[GrammarPair]:
    """Return the measured grammars in report order."""

    all_traits = list(_DERIVABLE_TRAITS)
    return [
        GrammarPair(
            key="expansion",
            baseline=RetrogradeExpansionWireResponse,
            variant=ExpansionWithPlacePoints,
            added_field="new_place_points",
        ),
        GrammarPair(
            key="derivation_domain",
            baseline=selected_trait_compile_inputs_model(["domain"]),
            variant=selected_variant_model(["domain"]),
            added_field="domain.coordinates",
        ),
        GrammarPair(
            key="derivation_all_derivable_traits",
            baseline=selected_trait_compile_inputs_model(all_traits),
            variant=selected_variant_model(all_traits),
            added_field="domain.coordinates",
        ),
    ]


def compact(value: Any) -> str:
    """Serialize a JSON value in the report's one compact form."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def weigh(text: str, count: Callable[[str], int]) -> dict[str, int]:
    """Return UTF-8 bytes and tokens of ``text``."""

    return {"bytes": len(text.encode("utf-8")), "tokens": count(text)}


def schema_weight(
    model: type[BaseModel], form: str, count: Callable[[str], int]
) -> dict[str, int]:
    """Return the weight of ``model``'s schema in one wire form."""

    return weigh(compact(SCHEMA_FORMS[form](model)), count)


def grammar_weights(count: Callable[[str], int]) -> dict[str, Any]:
    """Return baseline, variant and delta weights for every grammar and form."""

    report: dict[str, Any] = {}
    for pair in grammar_pairs():
        forms: dict[str, Any] = {}
        for form in SCHEMA_FORMS:
            baseline = schema_weight(pair.baseline, form, count)
            variant = schema_weight(pair.variant, form, count)
            forms[form] = {
                "baseline": baseline,
                "variant": variant,
                "delta": {
                    "bytes": variant["bytes"] - baseline["bytes"],
                    "tokens": variant["tokens"] - baseline["tokens"],
                },
            }
        report[pair.key] = {
            "baseline_model": pair.baseline.__name__,
            "added_field": pair.added_field,
            "forms": forms,
        }
    return report


def coordinates_member_text() -> str:
    """Return the compact ``coordinates`` member one point adds to a reply."""

    return '"coordinates":' + compact_point()


def compact_point() -> str:
    """Return the sample point as compact JSON, latitude first."""

    return json.dumps(
        {"lat": SAMPLE_LAT, "lon": SAMPLE_LON},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def new_place_entry_text(name: str) -> str:
    """Return one compact ``new_place_points`` entry for ``name``."""

    return (
        '{"place_ref":'
        + json.dumps(name, ensure_ascii=False)
        + ',"coordinates":'
        + compact_point()
        + "}"
    )


def per_place_output(
    retrograde_stub_names: Sequence[str], count: Callable[[str], int]
) -> dict[str, Any]:
    """Return output tokens one point adds per place, in both grammar shapes."""

    names = list(dict.fromkeys(retrograde_stub_names))
    names_source = "retrograde_stubs"
    if not names:
        names = [FIXTURE_PLACE_NAME]
        names_source = "fixture"
    member = coordinates_member_text()
    return {
        "coordinates_member": {"text": member, "tokens": count(member)},
        "new_place_entries_source": names_source,
        "new_place_entries": [
            {
                "name": name,
                "text": new_place_entry_text(name),
                "tokens": count(new_place_entry_text(name)),
            }
            for name in names
        ],
    }


def request_schema_form(settings: Settings, model: str) -> str:
    """Return the schema form ``build_native_structured_provider`` sends."""

    provider = settings.provider_for_model(model)
    endpoint = get_openai_compatible_endpoint(model)
    if provider == "anthropic" and endpoint is None:
        return "anthropic_json_schema"
    if provider == "openai" or endpoint is not None:
        return "strict_json_schema"
    raise ValueError(f"Unsupported provider type for model {model!r}: {provider}")


@dataclass(frozen=True)
class PlaceRow:
    """One ``places`` row as the report reads it."""

    place_id: int
    name: str
    summary: Optional[str]
    created_at: datetime
    source: str
    sources: Any
    point: Optional[tuple[float, float, float, float]]
    zone_id: Optional[int]
    zone_name: Optional[str]
    zone_summary: Optional[str]


def summary_stats(values: Sequence[int]) -> dict[str, Any]:
    """Return min, mean and max of ``values``, or nulls when empty."""

    if not values:
        return {"min": None, "mean": None, "max": None}
    return {
        "min": min(values),
        "mean": round(sum(values) / len(values), 2),
        "max": max(values),
    }


def dedicated_call(
    settings: Settings,
    model: str,
    pointless_places: Sequence[tuple[str, PlaceRow]],
    count: Callable[[str], int],
) -> dict[str, Any]:
    """Return the dedicated geo-authoring call's request and output weights."""

    form = request_schema_form(settings, model)
    schemas = {
        name: schema_weight(GeoAuthoringResponse, name, count) for name in SCHEMA_FORMS
    }
    schema_tokens = schemas[form]["tokens"]
    output_text = '{"coordinates":' + compact_point() + "}"
    requests: list[int] = []
    by_database: dict[str, list[int]] = {}
    for dbname, place in pointless_places:
        if place.zone_name is None:
            raise ValueError(
                f"{dbname} place {place.place_id} ({place.name!r}) has no zone; "
                "the geo-authoring prompt needs one"
            )
        prompt = render_geo_authoring_prompt(
            place_name=place.name,
            place_summary=place.summary,
            zone_name=place.zone_name,
            zone_summary=place.zone_summary,
        )
        tokens = 2 * count(prompt) + schema_tokens
        requests.append(tokens)
        by_database.setdefault(dbname, []).append(tokens)
    return {
        "schema": schemas,
        "request_schema_form": form,
        "request": {
            "formula": REQUEST_FORMULA,
            "places_measured": len(requests),
            **summary_stats(requests),
            "by_database": {
                dbname: {"places_measured": len(values), **summary_stats(values)}
                for dbname, values in by_database.items()
            },
        },
        "output": {"text": output_text, "tokens": count(output_text)},
        "transport_framing_counted": False,
        "batch_call_measured": False,
        "notes": [TRANSPORT_FRAMING_NOTE, BATCH_CALL_NOTE],
    }


def _source_of(extra_data: Any) -> str:
    if isinstance(extra_data, Mapping):
        source = extra_data.get("source")
        if source is not None:
            return str(source)
    return SOURCE_NONE


def _sources_of(extra_data: Any) -> Any:
    if isinstance(extra_data, Mapping):
        return extra_data.get("sources")
    return None


def first_maturation_job_id(sources: Any) -> Optional[int]:
    """Return the job id of the first ``sources[].event_ref`` naming a job."""

    if not isinstance(sources, list):
        return None
    for entry in sources:
        if not isinstance(entry, Mapping):
            continue
        event_ref = entry.get("event_ref")
        if not isinstance(event_ref, str):
            continue
        match = MATURATION_EVENT_REF_PATTERN.match(event_ref)
        if match:
            return int(match.group("job_id"))
    return None


def _split_counts(rows: Sequence[PlaceRow]) -> dict[str, Any]:
    sources = Counter(row.source for row in rows)
    by_source = {
        RETROGRADE_SOURCE_KIND: sources.pop(RETROGRADE_SOURCE_KIND, 0),
        TRAIT_COMPILER_SOURCE: sources.pop(TRAIT_COMPILER_SOURCE, 0),
        SOURCE_NONE: sources.pop(SOURCE_NONE, 0),
    }
    by_source.update(sorted(sources.items()))
    present = sum(1 for row in rows if row.point is not None)
    return {
        "rows": len(rows),
        "by_source": by_source,
        "by_point": {"present": present, "null": len(rows) - present},
    }


def _read_places(cur: Any) -> list[PlaceRow]:
    cur.execute(
        """
        SELECT p.id, p.name, p.summary, p.created_at, p.extra_data,
               ST_X(p.geom), ST_Y(p.geom), ST_Z(p.geom), ST_M(p.geom),
               p.zone, z.name, z.summary
        FROM places p
        LEFT JOIN zones z ON z.id = p.zone
        ORDER BY p.id
        """
    )
    rows = []
    for (
        place_id,
        name,
        summary,
        created_at,
        extra_data,
        lon,
        lat,
        z_value,
        m_value,
        zone_id,
        zone_name,
        zone_summary,
    ) in cur.fetchall():
        rows.append(
            PlaceRow(
                place_id=int(place_id),
                name=str(name),
                summary=summary,
                created_at=created_at,
                source=_source_of(extra_data),
                sources=_sources_of(extra_data),
                point=None if lon is None else (lon, lat, z_value, m_value),
                zone_id=zone_id,
                zone_name=zone_name,
                zone_summary=zone_summary,
            )
        )
    return rows


def _shared_points(rows: Sequence[PlaceRow]) -> list[dict[str, Any]]:
    groups: dict[tuple[float, float, float, float], list[PlaceRow]] = {}
    for row in rows:
        if row.point is not None:
            groups.setdefault(row.point, []).append(row)
    return [
        {
            "lon": point[0],
            "lat": point[1],
            "place_ids": [row.place_id for row in members],
            "names": [row.name for row in members],
        }
        for point, members in groups.items()
        if len(members) >= 2
    ]


def _attribute_later_rows(
    cur: Any,
    later: Sequence[PlaceRow],
    chunks: Sequence[tuple[int, datetime]],
) -> list[dict[str, Any]]:
    job_ids = {
        job_id
        for job_id in (first_maturation_job_id(row.sources) for row in later)
        if job_id is not None
    }
    requesting: dict[int, int] = {}
    if job_ids:
        cur.execute(
            "SELECT id, requesting_chunk_id FROM orrery_maturation_jobs "
            "WHERE id = ANY(%s)",
            (sorted(job_ids),),
        )
        requesting = {int(job_id): int(chunk) for job_id, chunk in cur.fetchall()}

    detail: list[dict[str, Any]] = []
    for row in later:
        entry: dict[str, Any] = {
            "place_id": row.place_id,
            "name": row.name,
            "source": row.source,
            "has_point": row.point is not None,
        }
        job_id = first_maturation_job_id(row.sources)
        if job_id is not None and job_id in requesting:
            entry["turn_chunk_id"] = requesting[job_id]
            entry["turn_attribution"] = "maturation_job"
            entry["job_id"] = job_id
        else:
            eligible = [
                chunk_id
                for chunk_id, created_at in chunks
                if created_at <= row.created_at
            ]
            if not eligible:
                raise RuntimeError(
                    f"Later place {row.place_id} ({row.name!r}) has no chunk at "
                    "or before its created_at"
                )
            entry["turn_chunk_id"] = max(eligible)
            entry["turn_attribution"] = "created_at"
            if job_id is not None:
                entry["job_id"] = job_id
                entry["job_row_found"] = False
        detail.append(entry)
    return detail


def _turn_figures(
    first_chunk_id: int,
    chunks: Sequence[tuple[int, datetime]],
    detail: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    after_first = [chunk_id for chunk_id, _ in chunks if chunk_id != first_chunk_id]
    per_chunk = Counter(
        int(entry["turn_chunk_id"])
        for entry in detail
        if int(entry["turn_chunk_id"]) != first_chunk_id
    )
    unknown = sorted(set(per_chunk) - set(after_first))
    if unknown:
        raise RuntimeError(f"Later places name chunks that do not exist: {unknown}")
    counts = [per_chunk.get(chunk_id, 0) for chunk_id in after_first]
    histogram = Counter(counts)
    return {
        "chunks_after_first": len(after_first),
        "later_rows_on_first_chunk": sum(
            1 for entry in detail if int(entry["turn_chunk_id"]) == first_chunk_id
        ),
        "later_rows_per_chunk": {
            "mean": (round(sum(counts) / len(counts), 3) if counts else None),
            "max": max(counts) if counts else None,
            "histogram": {str(key): histogram[key] for key in sorted(histogram)},
        },
    }


@dataclass
class DatabaseReading:
    """One database's report section and the rows other sections reuse."""

    report: dict[str, Any]
    places: list[PlaceRow]


def read_database(dbname: str) -> DatabaseReading:
    """Read one database's place rows and turn attribution, read-only."""

    conn = open_read_only_connection(dbname)
    try:
        with conn.cursor() as cur:
            places = _read_places(cur)
            cur.execute(
                "SELECT id, created_at, authorial_directives "
                "FROM narrative_chunks ORDER BY id"
            )
            chunk_rows = cur.fetchall()
            report: dict[str, Any] = {
                "places_total": len(places),
                "shared_points": _shared_points(places),
            }
            if not chunk_rows:
                report["first_chunk"] = None
                return DatabaseReading(report=report, places=places)
            missing = [int(row[0]) for row in chunk_rows if row[1] is None]
            if missing:
                raise RuntimeError(
                    f"{dbname} chunks with NULL created_at cannot be ordered: "
                    f"{missing[:20]}"
                )
            chunks = [(int(row[0]), row[1]) for row in chunk_rows]
            first_id, first_created, first_directives = chunk_rows[0]
            genesis = [row for row in places if row.created_at <= first_created]
            later = [row for row in places if row.created_at > first_created]
            detail = _attribute_later_rows(cur, later, chunks)
        conn.rollback()
    finally:
        conn.close()

    report["first_chunk"] = {
        "id": int(first_id),
        "created_at": first_created.isoformat(),
        "authorial_directives": first_directives,
    }
    report["genesis"] = _split_counts(genesis)
    report["later"] = {**_split_counts(later), "rows_detail": detail}
    report["turns"] = _turn_figures(int(first_id), chunks, detail)
    return DatabaseReading(report=report, places=places)


def _orrery(settings: Settings) -> OrrerySettings:
    """Return the ``[orrery]`` settings, which this report requires."""

    if settings.orrery is None:
        raise ValueError("nexus.toml has no [orrery] table")
    return settings.orrery


def build_report(
    settings: Settings, model: str, dbnames: Sequence[str]
) -> dict[str, Any]:
    """Build the full report for ``model`` over ``dbnames``."""

    model = settings.resolve_model_ref(model)
    entry = settings.model_entry(model)
    count = local_text_counter(entry)

    databases: dict[str, Any] = {}
    stub_names: list[str] = []
    pointless: list[tuple[str, PlaceRow]] = []
    for dbname in dbnames:
        logger.info("Reading %s read-only", dbname)
        reading = read_database(dbname)
        databases[dbname] = reading.report
        for place in reading.places:
            if place.source == RETROGRADE_SOURCE_KIND:
                stub_names.append(place.name)
            if place.point is None:
                pointless.append((dbname, place))

    return {
        "issue": 840,
        "question": "840-Q4",
        "model": model,
        "tokenizer": entry.tokenizer_encoding or entry.tokenizer_repository,
        "serialization": SERIALIZATION,
        "sample_point": {"lat": SAMPLE_LAT, "lon": SAMPLE_LON},
        "grammars": grammar_weights(count),
        "per_place_output": per_place_output(stub_names, count),
        "dedicated_call": dedicated_call(settings, model, pointless, count),
        "configured_stub_cap": {
            "setting": "orrery.retrograde.wizard.max_new_entity_stubs",
            "value": _orrery(settings).retrograde.wizard.max_new_entity_stubs,
            "meaning": "cap on charged new stubs of all kinds per genesis expansion",
        },
        "databases": databases,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse the report's command line."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dbname",
        action="append",
        type=metrics_dbname,
        default=[],
        help="Database to read (repeatable): save_NN, qa640_* or ref_*.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Registered model id for token counts and the dedicated call's "
            "schema form (default: orrery.retrograde.maturation.model_ref)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Print the report as one JSON document on stdout."""

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    args = parse_args(argv)
    settings = load_settings()
    model = args.model or _orrery(settings).retrograde.maturation.model_ref
    if model is None:
        raise ValueError("orrery.retrograde.maturation.model_ref is not set")
    report = build_report(settings, model, args.dbname)
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
