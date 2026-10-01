"""Read-only rearm grammar weight report for issue 781 (decision 781-Q2).

The report builds throwaway Pydantic variants of the Skald wires inside this
script. Each variant adds one optional ``rearm`` field to the Orrery
adjudication, so a deferred proposal can name the condition that makes it
eligible again. The report measures the bytes and local token estimates of
every provider surface for each variant against the baseline of the same seat
and surface. It puts nothing on any wire and calls no provider.

The static seats are offline. The registry seat reads one slot registry
through a session whose transactions are read-only by
``default_transaction_read_only=on``.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from typing import Any, Callable, Literal, Optional, Sequence, get_args

import psycopg2
from pydantic import BaseModel, ConfigDict, Field, create_model

from nexus.agents.logon.apex_schema import OrreryAdjudication
from nexus.agents.logon.gaia_registry_schema import (
    GaiaRegistryWireSpec,
    load_gaia_registry_wire_spec,
)
from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    SkaldTurnWire,
    _render_prompt_guide,
)
from nexus.api.native_structured_output import de_null_schema, strict_json_schema
from nexus.config import load_settings
from nexus.config.settings_models import Settings
from nexus.database import connection_kwargs
from nexus.telemetry.prompt_window import estimator_for

StaticSeat = Literal["gaia", "single_pass"]

# Variant names in report order; ``baseline`` adds no field.
VARIANTS: tuple[str, ...] = (
    "baseline",
    "typed_fields",
    "minimal_typed",
    "compact_string",
    "package_default",
)
STATIC_SEATS: tuple[StaticSeat, ...] = ("gaia", "single_pass")
REGISTRY_SEAT = "gaia_registry"
STATIC_SURFACES: tuple[str, ...] = ("strict", "lenient", "guide")
REGISTRY_SURFACES: tuple[str, ...] = ("strict",)

READ_ONLY_OPTION = "-c default_transaction_read_only=on"

RearmKind = Literal["after_hours", "on_event", "on_state", "on_blocker_cleared"]

REARM_KIND_DESCRIPTION = "What makes the deferred proposal eligible again."
REARM_FIELD_DESCRIPTION = "Condition that makes a deferred proposal eligible again."
EVENT_TYPE_DESCRIPTION = "Registered event type, for on_event."
ADJUDICATIONS_DESCRIPTION = "Rulings on current Orrery proposals."


@dataclass(frozen=True)
class Row:
    """One measured surface of one variant, with deltas against its baseline."""

    seat: str
    surface: str
    variant: str
    bytes: int
    tokens: int
    delta_bytes: int
    delta_tokens: int
    delta_bytes_pct: float


def _typed_rearm_model() -> type[BaseModel]:
    """Build the ``typed_fields`` rearm model for the static seats."""

    return create_model(
        "OrreryRearm",
        __config__=ConfigDict(extra="forbid"),
        __module__=__name__,
        __doc__="Typed condition that makes a deferred proposal eligible again.",
        kind=(RearmKind, Field(description=REARM_KIND_DESCRIPTION)),
        hours=(
            Optional[float],
            Field(
                default=None,
                gt=0,
                description="World hours to wait, for after_hours.",
            ),
        ),
        event_type=(
            Optional[str],
            Field(default=None, description=EVENT_TYPE_DESCRIPTION),
        ),
        entity=(
            Optional[str],
            Field(
                default=None,
                description="Card handle of the entity the condition names.",
            ),
        ),
        tag=(
            Optional[str],
            Field(
                default=None,
                description=(
                    "Tag whose change rearms, for on_state or on_blocker_cleared."
                ),
            ),
        ),
    )


def _minimal_rearm_model() -> type[BaseModel]:
    """Build the ``minimal_typed`` rearm model."""

    return create_model(
        "OrreryRearm",
        __config__=ConfigDict(extra="forbid"),
        __module__=__name__,
        __doc__="Rearm kind with one argument whose meaning depends on the kind.",
        kind=(RearmKind, Field(description=REARM_KIND_DESCRIPTION)),
        argument=(
            str,
            Field(
                min_length=1,
                description=(
                    "Hours, event type, or handle and tag, as the kind requires."
                ),
            ),
        ),
    )


def _rearm_field(
    variant: str,
    event_type_annotation: Optional[Any],
) -> Optional[tuple[Any, Any]]:
    """Return the ``rearm`` field definition for one variant, or None.

    ``event_type_annotation`` is the registry adjudication's own
    ``replacement_event_type`` annotation; when given, the ``typed_fields``
    rearm model is subclassed under the same name so ``event_type`` reuses
    the shared ``EventTypeName`` definition. ``tag`` stays a plain string.
    """

    if variant == "baseline":
        return None
    if variant == "typed_fields":
        rearm_model = _typed_rearm_model()
        if event_type_annotation is not None:
            rearm_model = create_model(
                rearm_model.__name__,
                __base__=rearm_model,
                __module__=__name__,
                __doc__=rearm_model.__doc__,
                event_type=(
                    event_type_annotation,
                    Field(default=None, description=EVENT_TYPE_DESCRIPTION),
                ),
            )
        return (
            Optional[rearm_model],
            Field(default=None, description=REARM_FIELD_DESCRIPTION),
        )
    if variant == "minimal_typed":
        return (
            Optional[_minimal_rearm_model()],
            Field(default=None, description=REARM_FIELD_DESCRIPTION),
        )
    if variant == "compact_string":
        return (
            Optional[str],
            Field(
                default=None,
                min_length=1,
                description=(
                    "Rearm rule, e.g. 'after 6h' or 'when <handle> loses <tag>'."
                ),
            ),
        )
    if variant == "package_default":
        return (
            Optional[str],
            Field(
                default=None,
                min_length=1,
                description=(
                    "Optional override of the package default rearm, e.g. 'after 6h'."
                ),
            ),
        )
    raise ValueError(f"Unknown rearm variant {variant!r}")


def _wire_variants(
    wire: type[BaseModel],
    base: type[BaseModel],
    *,
    event_type_annotation: Optional[Any] = None,
) -> dict[str, type[BaseModel]]:
    """Build the five wire variants of one wire and adjudication base."""

    variants: dict[str, type[BaseModel]] = {}
    for variant in VARIANTS:
        rearm = _rearm_field(variant, event_type_annotation)
        extra_fields: dict[str, Any] = {} if rearm is None else {"rearm": rearm}
        adjudication = create_model(
            base.__name__,
            __base__=base,
            __module__=__name__,
            __doc__=base.__doc__,
            **extra_fields,
        )
        variants[variant] = create_model(
            wire.__name__,
            __base__=wire,
            __module__=__name__,
            __doc__=wire.__doc__,
            orrery_adjudications=(
                list[adjudication],  # type: ignore[valid-type]
                # The order's construction: the production field's own factory.
                Field(
                    default_factory=list,  # type: ignore[arg-type]
                    description=ADJUDICATIONS_DESCRIPTION,
                ),
            ),
        )
    return variants


def build_variants(seat: StaticSeat) -> dict[str, type[BaseModel]]:
    """Return the five wire variants of one static seat, in report order."""

    if seat == "gaia":
        return _wire_variants(SkaldGaiaWire, OrreryAdjudication)
    if seat == "single_pass":
        return _wire_variants(SkaldTurnWire, OrreryAdjudication)
    raise ValueError(f"Unknown static seat {seat!r}")


def registry_variants(
    dbname: str,
) -> tuple[GaiaRegistryWireSpec, dict[str, type[BaseModel]]]:
    """Return the registry spec of ``dbname`` and its five wire variants.

    The spec is built without scene entities, so it has no clear-only enums.
    """

    spec = load_gaia_registry_wire_spec(dbname)
    registry_model = spec.model
    base = get_args(registry_model.model_fields["orrery_adjudications"].annotation)[0]
    event_type_annotation = base.model_fields["replacement_event_type"].annotation
    return spec, _wire_variants(
        registry_model,
        base,
        event_type_annotation=event_type_annotation,
    )


def compact_json(schema: dict[str, Any]) -> str:
    """Serialize one schema as the wire-size tests do."""

    return json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def surfaces(model: type[BaseModel], seat: str) -> dict[str, str]:
    """Return the measured surface texts of one wire model for one seat.

    ``strict`` and ``lenient`` are compact schema serializations; ``guide`` is
    the prompted-output guide text. The registry seat is OpenAI-only, so it
    has only ``strict``.
    """

    strict = compact_json(strict_json_schema(model))
    if seat == REGISTRY_SEAT:
        return {"strict": strict}
    if seat not in STATIC_SEATS:
        raise ValueError(f"Unknown seat {seat!r}")
    lenient_schema = de_null_schema(model.model_json_schema())
    return {
        "strict": strict,
        "lenient": compact_json(lenient_schema),
        "guide": _render_prompt_guide(
            lenient_schema,
            include_descriptions=seat == "single_pass",
        ),
    }


def seat_model_id(settings: Settings, seat: str) -> str:
    """Return the configured default model whose counter estimates ``seat``."""

    if seat in ("gaia", REGISTRY_SEAT):
        return settings.apex.gaia_model or settings.apex.model
    if seat == "single_pass":
        return settings.apex.model
    raise ValueError(f"Unknown seat {seat!r}")


def _seat_rows(
    seat: str,
    variants: dict[str, type[BaseModel]],
    surface_names: tuple[str, ...],
    count: Callable[[str], int],
) -> list[Row]:
    """Measure every surface of every variant of one seat, with deltas."""

    texts = {variant: surfaces(model, seat) for variant, model in variants.items()}
    rows: list[Row] = []
    for surface in surface_names:
        base_text = texts["baseline"][surface]
        base_bytes = len(base_text.encode("utf-8"))
        base_tokens = count(base_text)
        for variant in VARIANTS:
            text = texts[variant][surface]
            size = len(text.encode("utf-8"))
            tokens = count(text)
            delta_bytes = size - base_bytes
            rows.append(
                Row(
                    seat=seat,
                    surface=surface,
                    variant=variant,
                    bytes=size,
                    tokens=tokens,
                    delta_bytes=delta_bytes,
                    delta_tokens=tokens - base_tokens,
                    delta_bytes_pct=round(100.0 * delta_bytes / base_bytes, 2),
                )
            )
    return rows


def static_rows() -> list[Row]:
    """Return the offline rows of both static seats."""

    settings = load_settings()
    rows: list[Row] = []
    for seat in STATIC_SEATS:
        count = estimator_for(seat_model_id(settings, seat), settings=settings)
        rows.extend(_seat_rows(seat, build_variants(seat), STATIC_SURFACES, count))
    return rows


def registry_rows(dbname: str) -> tuple[str, list[Row]]:
    """Return the registry digest of ``dbname`` and the registry seat's rows."""

    settings = load_settings()
    spec, variants = registry_variants(dbname)
    count = estimator_for(seat_model_id(settings, REGISTRY_SEAT), settings=settings)
    return spec.registry_digest, _seat_rows(
        REGISTRY_SEAT, variants, REGISTRY_SURFACES, count
    )


def _tokenizer_settings(settings: Settings, model_id: str) -> dict[str, Any]:
    """Return the local tokenizer declaration of one registered model."""

    entry = settings.model_entry(model_id)
    return {
        "tokenizer_encoding": entry.tokenizer_encoding,
        "tokenizer_repository": entry.tokenizer_repository,
        "token_count_safety_margin": entry.token_count_safety_margin,
    }


def _require_read_only_session(dbname: str) -> None:
    """Force read-only transactions through PGOPTIONS and prove one session."""

    ambient = os.environ.get("PGOPTIONS", "")
    os.environ["PGOPTIONS"] = f"{READ_ONLY_OPTION} {ambient}".strip()
    conn = psycopg2.connect(**connection_kwargs(dbname))
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None or row[0] != "on":
        raise RuntimeError(
            f"Refusing to read {dbname!r}: transaction_read_only="
            f"{None if row is None else row[0]!r}"
        )


def _format_delta(value: int) -> str:
    """Render one signed integer delta."""

    return f"{value:+,}"


def render_markdown(header: dict[str, Any], rows: list[Row]) -> str:
    """Render the header and the rows as a Markdown report."""

    lines = ["# Rearm Grammar Weight", ""]
    for key, value in header.items():
        rendered = (
            json.dumps(value, sort_keys=True) if isinstance(value, dict) else value
        )
        lines.append(f"- {key}: {rendered}")
    lines.extend(
        [
            "",
            "| seat | surface | variant | bytes | tokens | Δ bytes | Δ tokens "
            "| Δ bytes % |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.seat} | {row.surface} | {row.variant} | {row.bytes:,} "
            f"| {row.tokens:,} | {_format_delta(row.delta_bytes)} "
            f"| {_format_delta(row.delta_tokens)} | {row.delta_bytes_pct:+.2f}% |"
        )
    return "\n".join(lines) + "\n"


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    """Parse the report options."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--registry-dbname",
        default="save_04",
        help="Slot database whose registry the registry seat reads (read-only).",
    )
    parser.add_argument(
        "--skip-registry",
        action="store_true",
        help="Measure only the static seats; open no database.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Report format on stdout.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Measure every seat, surface and variant and print the report."""

    args = _parse_args(argv)
    settings = load_settings()
    gaia_model = seat_model_id(settings, "gaia")
    single_pass_model = seat_model_id(settings, "single_pass")
    header: dict[str, Any] = {
        "gaia_model": gaia_model,
        "gaia_tokenizer": _tokenizer_settings(settings, gaia_model),
        "single_pass_model": single_pass_model,
        "single_pass_tokenizer": _tokenizer_settings(settings, single_pass_model),
    }
    rows = static_rows()
    if args.skip_registry:
        header["registry"] = "skipped"
    else:
        _require_read_only_session(args.registry_dbname)
        digest, registry = registry_rows(args.registry_dbname)
        header["registry_dbname"] = args.registry_dbname
        header["registry_digest"] = digest
        rows.extend(registry)
    if args.format == "json":
        print(
            json.dumps(
                {"header": header, "rows": [asdict(row) for row in rows]},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(render_markdown(header, rows), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
