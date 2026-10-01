"""Read-only wire-grammar and card-block probe for issue 784.

The owner ruling on #784 asks which representation of the attention class
(extending the ``drive_band`` and ``promotable`` flags, or replacing them with
one three-way class) avoids growth of the structured-output grammar. This
probe measures the provider wire schemas under both options, the ceiling cost
if a later slice had to put the class on the wire, the token cost of marking
rendered resolution cards, and the card blocks and exposures each 784-Q1
roster candidate would move. It decides nothing.

Every database is read read-only: ``main`` prepends
``default_transaction_read_only=on`` to the ambient ``PGOPTIONS`` before the
first read, so the production registry readers inherit it, and the probe's own
SQL runs through ``read_only_cursor``.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing, contextmanager
import copy
import json
import logging
import os
from pathlib import Path
import subprocess
import typing
from typing import Any, Callable, Iterator, List, Literal, Mapping, Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field, create_model

from nexus.agents.logon.gaia_registry_schema import (
    GaiaRegistryWireSpec,
    load_gaia_registry_wire_spec,
)
from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    SkaldTurnWire,
    _render_prompt_guide,
    skald_gaia_lenient_schema,
    skald_gaia_prompt_guide,
    skald_gaia_strict_text_format,
    skald_wire_lenient_schema,
    skald_wire_prompt_guide,
    skald_wire_strict_text_format,
)
from nexus.agents.lore.logon_utility import _orrery_card_line
from nexus.agents.orrery.cards import card_key, proposal_handles, rendered_selection
from nexus.api.native_structured_output import (
    de_null_schema,
    openai_response_text_format,
    strict_json_schema,
)
from nexus.config import load_settings
from nexus.config.settings_models import OrreryPromptSettings, Settings
from nexus.database import connection_kwargs
from nexus.telemetry.prompt_window import estimator_for
from scripts.database_targets import metrics_dbname

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CORPORA: tuple[str, ...] = ("save_04", "ref_codex_bakeoff_2026_07")

# The three attention-class values the #784 design names.
ATTENTION_LABELS: tuple[str, ...] = ("background", "meaningful", "urgent")
AttentionClass = Literal["background", "meaningful", "urgent"]
ATTENTION_DESCRIPTION = "Attention class of the proposal."
ADJUDICATIONS_DESCRIPTION = "Rulings on current Orrery proposals."

# Wire property names that would mean the class already rides the wire.
CLASS_PROPERTY_NAMES: frozenset[str] = frozenset(
    {"drive_band", "promotable", "attention"}
)

# Background rosters: the 784-Q1 candidates on issue #784. R1 is the settled
# mundane set; R2 adds ordinary sleeping, eating and drinking, and is an upper
# bound because need severity (the "unless a need becomes critical" escape) is
# not stored on the snapshot or the exposure rows.
R1: tuple[str, ...] = ("train", "run_errands", "stroll", "upkeep", "recreate")
R2: tuple[str, ...] = R1 + ("sleep", "eat", "drink")
ROSTERS: dict[str, tuple[str, ...]] = {"R1": R1, "R2": R2}

SEATS: tuple[str, ...] = ("gaia", "gaia_registry", "single_pass")
VARIANTS: tuple[str, ...] = (
    "head",
    "extend_off_wire",
    "replace_off_wire",
    "class_on_wire_ceiling",
)
ADJUDICATION_ACTIONS: tuple[str, ...] = ("defer", "replace", "void")

_READ_ONLY_OPTIONS = (
    "-c default_transaction_read_only=on "
    "-c default_transaction_isolation=repeatable\\ read"
)

Rendering = Any  # a JSON schema dict, or a prompt-guide string


class ProbePremiseError(RuntimeError):
    """Raised when a measured fact contradicts the work order's premise."""


# --------------------------------------------------------------------------
# Measurement convention (shared with the 781-S1 probe)
# --------------------------------------------------------------------------


def serialize_rendering(rendering: Rendering) -> str:
    """Return the exact text whose bytes and tokens are measured."""

    if isinstance(rendering, str):
        return rendering
    return json.dumps(
        rendering, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def measure(rendering: Rendering, estimator: Callable[[str], int]) -> dict[str, int]:
    """Return UTF-8 bytes and estimator tokens for one rendering."""

    text = serialize_rendering(rendering)
    return {"bytes": len(text.encode("utf-8")), "tokens": estimator(text)}


def gaia_model_id(settings: Settings) -> str:
    """Return the configured Gaia seat model (``apex.gaia_model`` else apex)."""

    return settings.apex.gaia_model or settings.apex.model


def single_pass_model_id(settings: Settings) -> str:
    """Return the configured single-pass storyteller model."""

    return settings.apex.model


def tokenizer_name(settings: Settings, model_id: str) -> str:
    """Return the tokenizer the local estimator declares for ``model_id``."""

    entry = settings.model_entry(model_id)
    name = entry.tokenizer_encoding or entry.tokenizer_repository
    if not name:
        raise ValueError(f"No local tokenizer declared for {model_id!r}")
    return name


# --------------------------------------------------------------------------
# HEAD renderings: production functions only
# --------------------------------------------------------------------------


def head_renderings() -> dict[tuple[str, str], Rendering]:
    """Build the six static renderings with the production functions."""

    return {
        ("gaia", "strict"): skald_gaia_strict_text_format()["schema"],
        ("gaia", "lenient"): skald_gaia_lenient_schema(),
        ("gaia", "guide"): skald_gaia_prompt_guide(),
        ("single_pass", "strict"): skald_wire_strict_text_format()["schema"],
        ("single_pass", "lenient"): skald_wire_lenient_schema(),
        ("single_pass", "guide"): skald_wire_prompt_guide(),
    }


def load_registry_spec(dbname: str) -> GaiaRegistryWireSpec:
    """Read the registry wire spec without clear-only enums."""

    return load_gaia_registry_wire_spec(dbname, scene_entity_refs=())


def registry_head_rendering(spec: GaiaRegistryWireSpec) -> dict[str, Any]:
    """Build the registry Gaia strict schema with the production function."""

    return skald_gaia_strict_text_format(spec.model)["schema"]


# --------------------------------------------------------------------------
# Off-wire premise: no wire schema names the class
# --------------------------------------------------------------------------


def property_names(schema: Any) -> set[str]:
    """Collect every property name in a schema, nested ``$defs`` included."""

    found: set[str] = set()
    if isinstance(schema, Mapping):
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            found.update(str(name) for name in properties)
        for value in schema.values():
            found |= property_names(value)
    elif isinstance(schema, list):
        for item in schema:
            found |= property_names(item)
    return found


def assert_class_off_wire(schema: Mapping[str, Any], label: str) -> None:
    """Raise when a measured wire schema already carries a class property."""

    present = sorted(property_names(schema) & CLASS_PROPERTY_NAMES)
    if present:
        raise ProbePremiseError(
            f"{label} already carries {present}: the off-wire premise of "
            "work order 784-S1 is false"
        )


# --------------------------------------------------------------------------
# Class-on-wire ceiling
# --------------------------------------------------------------------------


def _attention_adjudication(base: type[BaseModel]) -> type[BaseModel]:
    """Return an adjudication subclass carrying the optional attention class."""

    return create_model(  # type: ignore[call-overload,no-any-return]
        base.__name__,
        __base__=base,
        __module__=__name__,
        __doc__=base.__doc__,
        attention=(
            Optional[AttentionClass],
            Field(default=None, description=ATTENTION_DESCRIPTION),
        ),
    )


def ceiling_wire_model(wire: type[BaseModel]) -> type[BaseModel]:
    """Return ``wire`` with adjudications that carry the attention class."""

    annotation = wire.model_fields["orrery_adjudications"].annotation
    (adjudication_base,) = typing.get_args(annotation)
    adjudication = _attention_adjudication(adjudication_base)
    return create_model(  # type: ignore[call-overload,no-any-return]
        wire.__name__,
        __base__=wire,
        __module__=__name__,
        __doc__=wire.__doc__,
        orrery_adjudications=(
            List[adjudication],  # type: ignore[valid-type]
            Field(
                default_factory=list,  # type: ignore[arg-type]
                description=ADJUDICATIONS_DESCRIPTION,
            ),
        ),
    )


def ceiling_renderings(
    registry_model: Optional[type[BaseModel]] = None,
) -> dict[tuple[str, str], Rendering]:
    """Render the ceiling the way ``skald_wire.py`` renders each wire."""

    gaia = ceiling_wire_model(SkaldGaiaWire)
    turn = ceiling_wire_model(SkaldTurnWire)
    gaia_lenient = de_null_schema(gaia.model_json_schema())
    turn_lenient = de_null_schema(turn.model_json_schema())
    renderings: dict[tuple[str, str], Rendering] = {
        ("gaia", "strict"): skald_gaia_strict_text_format(
            gaia  # type: ignore[arg-type]
        )["schema"],
        ("gaia", "lenient"): gaia_lenient,
        ("gaia", "guide"): _render_prompt_guide(
            gaia_lenient, include_descriptions=False
        ),
        ("single_pass", "strict"): openai_response_text_format(
            turn, schema=strict_json_schema(turn)
        )["schema"],
        ("single_pass", "lenient"): turn_lenient,
        ("single_pass", "guide"): _render_prompt_guide(turn_lenient),
    }
    if registry_model is not None:
        registry = ceiling_wire_model(registry_model)
        renderings[("gaia_registry", "strict")] = skald_gaia_strict_text_format(
            registry  # type: ignore[arg-type]
        )["schema"]
    return renderings


def adjudication_definition_name(seat: str) -> str:
    """Return the ``$defs`` name of the adjudication model for a seat."""

    if seat == "gaia_registry":
        return "OrreryAdjudicationRegistry"
    return "OrreryAdjudication"


def expected_guide_line(seat: str) -> str:
    """Return the one guide line the ceiling inserts for a seat."""

    labels = json.dumps(
        list(ATTENTION_LABELS), ensure_ascii=False, separators=(",", ":")
    )
    line = f"attention?:string|enum={labels}"
    if seat == "single_pass":
        line += "|" + json.dumps(ATTENTION_DESCRIPTION, ensure_ascii=False)
    return line


def _assert_schema_ceiling(
    head: Mapping[str, Any],
    ceiling: Mapping[str, Any],
    *,
    seat: str,
    rendering: str,
) -> None:
    label = f"{seat}/{rendering} ceiling"
    if head.get("title") != ceiling.get("title"):
        raise AssertionError(f"{label}: title changed")
    head_defs = head.get("$defs", {})
    ceiling_defs = ceiling.get("$defs", {})
    if set(head_defs) != set(ceiling_defs):
        raise AssertionError(
            f"{label}: $defs keys changed: "
            f"{sorted(set(head_defs) ^ set(ceiling_defs))}"
        )
    head_root = {key: value for key, value in head.items() if key != "$defs"}
    ceiling_root = {key: value for key, value in ceiling.items() if key != "$defs"}
    if head_root != ceiling_root:
        raise AssertionError(f"{label}: root content outside $defs changed")
    adjudication = adjudication_definition_name(seat)
    if adjudication not in head_defs:
        raise AssertionError(f"{label}: no {adjudication} definition in head")
    for name in head_defs:
        if name != adjudication and head_defs[name] != ceiling_defs[name]:
            raise AssertionError(f"{label}: definition {name} changed")
    head_adj = dict(head_defs[adjudication])
    ceiling_adj = dict(ceiling_defs[adjudication])
    ceiling_properties = dict(ceiling_adj.pop("properties"))
    head_properties = head_adj.pop("properties")
    if "attention" in head_properties or "attention" not in ceiling_properties:
        raise AssertionError(f"{label}: attention is not the added property")
    if list(ceiling_properties)[-1] != "attention":
        raise AssertionError(f"{label}: attention is not the last property")
    ceiling_properties.pop("attention")
    if ceiling_properties != head_properties:
        raise AssertionError(f"{label}: other adjudication properties changed")
    head_required = list(head_adj.pop("required", []))
    ceiling_required = list(ceiling_adj.pop("required", []))
    expected_required = (
        head_required + ["attention"] if rendering == "strict" else head_required
    )
    if ceiling_required != expected_required:
        raise AssertionError(
            f"{label}: required {ceiling_required} != {expected_required}"
        )
    if ceiling_adj != head_adj:
        raise AssertionError(f"{label}: adjudication definition changed elsewhere")


def _assert_guide_ceiling(head: str, ceiling: str, *, seat: str) -> None:
    lines = head.split("\n")
    start = lines.index("OrreryAdjudication{")
    close = lines.index("}", start)
    if not lines[close - 1].startswith("replacement_event_type"):
        raise AssertionError(
            f"{seat}/guide: replacement_event_type is not the last adjudication line"
        )
    expected = lines[:close] + [expected_guide_line(seat)] + lines[close:]
    if ceiling != "\n".join(expected):
        raise AssertionError(
            f"{seat}/guide ceiling is not head plus the one attention line"
        )


def assert_ceiling_shape(
    head: Rendering, ceiling: Rendering, *, seat: str, rendering: str
) -> None:
    """Raise unless the ceiling differs from head only by the attention field."""

    if rendering == "guide":
        _assert_guide_ceiling(head, ceiling, seat=seat)
    else:
        _assert_schema_ceiling(head, ceiling, seat=seat, rendering=rendering)


# --------------------------------------------------------------------------
# Wire section
# --------------------------------------------------------------------------


def wire_rows(
    settings: Settings, registry_spec: GaiaRegistryWireSpec
) -> list[dict[str, Any]]:
    """Measure every seat, rendering and variant against ``head``."""

    estimators = {
        "gaia": estimator_for(gaia_model_id(settings), settings=settings),
        "gaia_registry": estimator_for(gaia_model_id(settings), settings=settings),
        "single_pass": estimator_for(single_pass_model_id(settings), settings=settings),
    }

    def build_head() -> dict[tuple[str, str], Rendering]:
        head = head_renderings()
        head[("gaia_registry", "strict")] = registry_head_rendering(registry_spec)
        return head

    head = build_head()
    # Under both options the class is server-authored and no wire model reads
    # Branch, Template or the draft dict, so both rows rebuild the production
    # renderings; the property walk proves the premise for each.
    off_wire = {"extend_off_wire": build_head(), "replace_off_wire": build_head()}
    ceiling = ceiling_renderings(registry_spec.model)

    rows: list[dict[str, Any]] = []
    for seat in SEATS:
        for rendering in ("strict", "lenient", "guide"):
            key = (seat, rendering)
            if key not in head:
                continue
            variants: dict[str, Rendering] = {
                "head": head[key],
                **{name: renders[key] for name, renders in off_wire.items()},
                "class_on_wire_ceiling": ceiling[key],
            }
            if rendering != "guide":
                for variant in ("head", "extend_off_wire", "replace_off_wire"):
                    assert_class_off_wire(
                        variants[variant], f"{seat}/{rendering}/{variant}"
                    )
            assert_ceiling_shape(
                head[key], ceiling[key], seat=seat, rendering=rendering
            )
            base = measure(head[key], estimators[seat])
            for variant in VARIANTS:
                measured = measure(variants[variant], estimators[seat])
                rows.append(
                    {
                        "seat": seat,
                        "rendering": rendering,
                        "variant": variant,
                        "bytes": measured["bytes"],
                        "tokens": measured["tokens"],
                        "delta_bytes": measured["bytes"] - base["bytes"],
                        "delta_tokens": measured["tokens"] - base["tokens"],
                    }
                )
    return rows


# --------------------------------------------------------------------------
# Card blocks
# --------------------------------------------------------------------------


def strip_rendered_cards(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy without a frozen ``rendered_cards`` selection."""

    copied = copy.deepcopy(dict(snapshot))
    copied.pop("rendered_cards", None)
    return copied


def rendered_resolution_cards(
    snapshot: Mapping[str, Any], caps: OrreryPromptSettings
) -> list[tuple[dict[str, Any], str]]:
    """Select and render resolution cards the way the turn prompt does."""

    resolutions = list(snapshot.get("resolutions", []))
    positions: dict[str, int] = {}
    cards: dict[str, dict[str, Any]] = {}
    for index, card in enumerate(resolutions):
        key = card_key(card)
        if key in positions:
            raise ValueError(f"Duplicate resolution card {key!r} in snapshot")
        positions[key] = index
        cards[key] = card
    selection = rendered_selection(snapshot, caps)
    handles = proposal_handles(selection)
    rendered: list[tuple[dict[str, Any], str]] = []
    for item in selection:
        if item["kind"] != "resolution":
            continue
        key = item["proposal_id"]
        card = cards[key]
        rendered.append(
            (
                card,
                _orrery_card_line(
                    card,
                    handles[key],
                    position=positions[key],
                    description=card.get("branch_label") or card["template_id"],
                ),
            )
        )
    return rendered


def _arm(
    corpus: str,
    roster: Optional[str],
    arm: str,
    cards: Sequence[Mapping[str, Any]],
    lines: Sequence[str],
    estimator: Callable[[str], int],
) -> dict[str, Any]:
    return {
        "corpus": corpus,
        "roster": roster,
        "arm": arm,
        "lines": len(lines),
        "tokens": estimator("\n".join(lines)),
        "proposal_ids": [card_key(card) for card in cards],
    }


def _marked(card: Mapping[str, Any], line: str, roster: Sequence[str]) -> str:
    label = "background" if card["template_id"] in roster else "meaningful"
    return f"{line} · {label}"


def card_block_rows(
    corpus: str,
    snapshot: Mapping[str, Any],
    caps: OrreryPromptSettings,
    estimator: Callable[[str], int],
    rosters: Mapping[str, Sequence[str]] = ROSTERS,
) -> list[dict[str, Any]]:
    """Replay the head card block and each roster's arms on one snapshot."""

    snapshot = strip_rendered_cards(snapshot)
    head = rendered_resolution_cards(snapshot, caps)
    rows = [
        _arm(
            corpus,
            None,
            "head",
            [card for card, _ in head],
            [line for _, line in head],
            estimator,
        )
    ]
    for name, roster in rosters.items():
        dropped = [(c, line) for c, line in head if c["template_id"] not in roster]
        filtered = dict(snapshot)
        filtered["resolutions"] = [
            card
            for card in snapshot.get("resolutions", [])
            if card["template_id"] not in roster
        ]
        refill = rendered_resolution_cards(filtered, caps)
        for arm, pairs, marked in (
            ("drop_only", dropped, False),
            ("refill", refill, False),
            ("head_marked", head, True),
            ("refill_marked", refill, True),
        ):
            lines = [
                _marked(card, line, roster) if marked else line for card, line in pairs
            ]
            rows.append(
                _arm(corpus, name, arm, [c for c, _ in pairs], lines, estimator)
            )
    return rows


def card_line_rows(
    corpus: str,
    snapshot: Mapping[str, Any],
    caps: OrreryPromptSettings,
    estimator: Callable[[str], int],
) -> list[dict[str, Any]]:
    """Measure the per-line token delta of a `` · <label>`` suffix."""

    lines = [
        line
        for _, line in rendered_resolution_cards(strip_rendered_cards(snapshot), caps)
    ]
    rows = []
    for label in ATTENTION_LABELS:
        deltas = [estimator(f"{line} · {label}") - estimator(line) for line in lines]
        rows.append(
            {
                "corpus": corpus,
                "label": label,
                "lines": len(lines),
                "min_delta_tokens": min(deltas) if deltas else None,
                "max_delta_tokens": max(deltas) if deltas else None,
            }
        )
    return rows


# --------------------------------------------------------------------------
# Read-only SQL
# --------------------------------------------------------------------------


@contextmanager
def read_only_cursor(dbname: str) -> Iterator[Any]:
    """Yield a cursor on a read-only, repeatable-read session for ``dbname``."""

    metrics_dbname(dbname)
    with closing(
        psycopg2.connect(
            **connection_kwargs(dbname, options=_READ_ONLY_OPTIONS),
            cursor_factory=RealDictCursor,
        )
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('transaction_read_only') AS read_only")
            if cur.fetchone()["read_only"] != "on":
                raise RuntimeError(f"Read-only transaction is required on {dbname}")
            yield cur
        conn.rollback()


def install_read_only_pgoptions() -> None:
    """Prepend the read-only default to the ambient ``PGOPTIONS``."""

    os.environ["PGOPTIONS"] = (
        "-c default_transaction_read_only=on " + os.environ.get("PGOPTIONS", "")
    ).strip()


def assert_ambient_read_only(dbname: str) -> None:
    """Prove a default ``connection_kwargs`` session for ``dbname`` is read-only."""

    with closing(psycopg2.connect(**connection_kwargs(dbname))) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('transaction_read_only')")
            row = cur.fetchone()
            if row is None or row[0] != "on":
                raise RuntimeError(
                    f"Ambient session on {dbname} is not read-only: {row!r}"
                )
        conn.rollback()


def incubator_snapshot(dbname: str) -> dict[str, Any]:
    """Read the one ranked Orrery snapshot held by the incubator."""

    with read_only_cursor(dbname) as cur:
        cur.execute(
            "SELECT orrery_proposal FROM incubator WHERE orrery_proposal IS NOT NULL"
        )
        rows = cur.fetchall()
    if len(rows) != 1:
        raise RuntimeError(
            f"{dbname}: expected one incubator snapshot, found {len(rows)}"
        )
    snapshot = rows[0]["orrery_proposal"]
    if not isinstance(snapshot, dict):
        raise TypeError(f"{dbname}: incubator orrery_proposal is not an object")
    return snapshot


def exposure_rows(
    dbname: str, rosters: Mapping[str, Sequence[str]] = ROSTERS
) -> list[dict[str, Any]]:
    """Replay prompt exposures, adjudications and the refill pool per roster."""

    rows: list[dict[str, Any]] = []
    with read_only_cursor(dbname) as cur:
        for name, roster in rosters.items():
            templates = list(roster)
            cur.execute(
                """
                SELECT count(DISTINCT tick_chunk_id) AS ticks,
                       count(*) AS resolution_exposures,
                       count(*) FILTER (WHERE template_id = ANY(%(roster)s))
                           AS roster_exposures
                  FROM orrery_prompt_exposures
                 WHERE kind = 'resolution'
                """,
                {"roster": templates},
            )
            exposures = dict(cur.fetchone())
            cur.execute(
                """
                SELECT count(*) AS all_roster_ticks
                  FROM (
                        SELECT tick_chunk_id
                          FROM orrery_prompt_exposures
                         WHERE kind = 'resolution'
                         GROUP BY tick_chunk_id
                        HAVING bool_and(template_id = ANY(%(roster)s))
                       ) AS ticks
                """,
                {"roster": templates},
            )
            all_roster_ticks = cur.fetchone()["all_roster_ticks"]
            cur.execute(
                """
                SELECT action, count(*) AS count
                  FROM orrery_adjudication_log
                 WHERE template_id = ANY(%(roster)s)
                 GROUP BY action
                """,
                {"roster": templates},
            )
            actions = Counter({row["action"]: row["count"] for row in cur.fetchall()})
            unknown = set(actions) - set(ADJUDICATION_ACTIONS)
            if unknown:
                raise ValueError(f"{dbname}: unknown adjudication actions {unknown}")
            cur.execute(
                """
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE NOT (r.template_id = ANY(%(roster)s)))
                           AS outside_roster
                  FROM orrery_resolutions AS r
                 WHERE NOT EXISTS (
                        SELECT 1
                          FROM orrery_prompt_exposures AS e
                         WHERE e.tick_chunk_id = r.tick_chunk_id
                           AND e.template_id = r.template_id
                           AND e.binding_hash = r.binding_hash
                       )
                """,
                {"roster": templates},
            )
            pool = dict(cur.fetchone())
            rows.append(
                {
                    "corpus": dbname,
                    "roster": name,
                    "ticks": exposures["ticks"],
                    "resolution_exposures": exposures["resolution_exposures"],
                    "roster_exposures": exposures["roster_exposures"],
                    "all_roster_ticks": all_roster_ticks,
                    "adjudications": {
                        action: actions.get(action, 0)
                        for action in ADJUDICATION_ACTIONS
                    },
                    "refill_pool_total": pool["total"],
                    "refill_pool_outside_roster": pool["outside_roster"],
                    # The rank of an unshown draft is not stored.
                    "refill_pool_upper_bound": True,
                }
            )
    return rows


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--registry-dbname",
        type=metrics_dbname,
        default="save_04",
        help="save_NN database whose registry builds the registry Gaia grammar",
    )
    parser.add_argument(
        "--corpus",
        type=metrics_dbname,
        action="append",
        default=None,
        help="corpus database for card and exposure replay (repeatable)",
    )
    return parser.parse_args(argv)


def build_report(registry_dbname: str, corpora: Sequence[str]) -> dict[str, Any]:
    """Assemble the full report; every database read is read-only."""

    settings = load_settings()
    gaia_model = gaia_model_id(settings)
    single_pass_model = single_pass_model_id(settings)
    gaia_estimator = estimator_for(gaia_model, settings=settings)
    if settings.orrery is None:
        raise RuntimeError("nexus.toml requires [orrery] for the card render caps")
    caps = settings.orrery.prompt

    for dbname in dict.fromkeys([registry_dbname, *corpora]):
        assert_ambient_read_only(dbname)

    registry_spec = load_registry_spec(registry_dbname)
    wire = wire_rows(settings, registry_spec)

    card_lines: list[dict[str, Any]] = []
    card_blocks: list[dict[str, Any]] = []
    exposures: list[dict[str, Any]] = []
    for corpus in corpora:
        logger.info("Replaying cards and exposures on %s", corpus)
        snapshot = incubator_snapshot(corpus)
        card_lines.extend(card_line_rows(corpus, snapshot, caps, gaia_estimator))
        card_blocks.extend(card_block_rows(corpus, snapshot, caps, gaia_estimator))
        exposures.extend(exposure_rows(corpus))

    return {
        "header": {
            "commit": _git_commit(),
            "gaia_model": gaia_model,
            "single_pass_model": single_pass_model,
            "gaia_tokenizer": tokenizer_name(settings, gaia_model),
            "single_pass_tokenizer": tokenizer_name(settings, single_pass_model),
            "registry_dbname": registry_dbname,
            "registry_digest": registry_spec.registry_digest,
            "corpora": list(corpora),
            "decides": "nothing",
        },
        "wire": wire,
        "card_lines": card_lines,
        "card_blocks": card_blocks,
        "exposures": exposures,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Measure both options and print one JSON document to stdout."""

    args = _parse_args(argv)
    corpora = list(args.corpus) if args.corpus is not None else list(DEFAULT_CORPORA)
    install_read_only_pgoptions()
    report = build_report(args.registry_dbname, corpora)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
