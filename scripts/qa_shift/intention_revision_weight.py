"""Offline Gaia revision grammar and listing measurement for issue 782 (782-Q4).

The report compares two ways Gaia could revise a durable intention against the
static Gaia wire. Option 1 adds a new closed ``intention_revisions`` field to
the Gaia wire, addressed by intention id, and needs a listing of every open
intention in Gaia's context. Option 2 extends the adjudication replace path
with an ``intention_revision`` delta, addressed by the card's ``proposal_id``,
and needs no listing. The probe wires live only in this script; the
production modules are not edited.

The report opens no database connection, makes no network request and calls
no provider. It prints one JSON document to stdout.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Type, cast

from pydantic import BaseModel, ConfigDict, Field, create_model

from nexus.agents.logon.apex_schema import (
    OrreryAdjudication,
    OrreryReplacementStateDelta,
)
from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    _render_prompt_guide,
    skald_gaia_strict_text_format,
)
from nexus.agents.orrery.substrate import _PROJECT_STAGE_LADDERS
from nexus.api.native_structured_output import de_null_schema
from nexus.config import load_settings
from nexus.telemetry.prompt_window import estimator_for

logger = logging.getLogger("nexus.qa_shift.intention_revision_weight")

GRAMMAR_KINDS: tuple[str, ...] = ("strict", "lenient", "prompt_guide")
OPTIONS: tuple[str, ...] = ("option_1_new_field", "option_2_replace_path")
DEFAULT_OPEN_COUNTS = "0,1,2,3,5,10,20"

PROJECT_TYPES: tuple[str, ...] = (
    "plan_relocation",
    "recruit_ally",
    "build_venture",
    "pursue_romance",
    "court_patron",
    "seek_redemption",
)
HOLDERS: tuple[str, ...] = (
    "Ilse Varga",
    "Tomas Reyes",
    "Noor Haddad",
    "Kenji Arai",
    "Petra Lind",
    "Dario Costa",
)
FIXED_TARGETS: Dict[str, str] = {
    "plan_relocation": "Lisbon harbor district",
    "build_venture": "none",
    "court_patron": "the Harbor Guild",
}

BASELINE_SENTENCE = (
    "static SkaldGaiaWire; the OpenAI seat sends the database-specialized "
    "SkaldGaiaRegistryWire (gaia_registry_schema.py:497), so absolute strict "
    "counts differ from production; the deltas are the measurement"
)
PROBE_SHAPE_SENTENCE = (
    "upper bound for measurement: four verbs, three target fields, urgency 1-3; "
    "not a ruling on the open verb or urgency questions"
)
LISTING_DESCRIPTIONS: Dict[str, str] = {
    "option_1_new_field": (
        "'Open intentions:' header plus one line per open intention, "
        "rendered to Gaia each turn"
    ),
    "option_2_replace_path": "none: the card already names the intention",
}

ProjectTypeLiteral = Literal[
    "plan_relocation",
    "recruit_ally",
    "build_venture",
    "pursue_romance",
    "court_patron",
    "seek_redemption",
]
VerbLiteral = Literal["retarget", "reprioritize", "retire", "replace"]


class IntentionRevisionProbe(BaseModel):
    """One Gaia revision of an open intention, addressed by intention id."""

    model_config = ConfigDict(extra="forbid")

    intention_id: int = Field(
        ge=1, description="Open intention id from the intention listing"
    )
    verb: VerbLiteral = Field(description="Closed revision verb")
    project_type: Optional[ProjectTypeLiteral] = Field(
        default=None, description="Replacement project type; replace only"
    )
    target_character_entity_id: Optional[int] = Field(
        default=None, description="New target; retarget or replace"
    )
    target_place_id: Optional[int] = Field(
        default=None, description="New target; retarget or replace"
    )
    target_faction_entity_id: Optional[int] = Field(
        default=None, description="New target; retarget or replace"
    )
    urgency: Optional[int] = Field(
        default=None, ge=1, le=3, description="New urgency; reprioritize only"
    )
    note: Optional[str] = Field(
        default=None, max_length=500, description="Brief canon reason for audit"
    )


class IntentionRevisionDeltaProbe(BaseModel):
    """One Gaia revision of the intention behind an adjudicated card."""

    model_config = ConfigDict(extra="forbid")

    verb: VerbLiteral = Field(description="Closed revision verb")
    project_type: Optional[ProjectTypeLiteral] = Field(
        default=None, description="Replacement project type; replace only"
    )
    target_character_entity_id: Optional[int] = Field(
        default=None, description="New target; retarget or replace"
    )
    target_place_id: Optional[int] = Field(
        default=None, description="New target; retarget or replace"
    )
    target_faction_entity_id: Optional[int] = Field(
        default=None, description="New target; retarget or replace"
    )
    urgency: Optional[int] = Field(
        default=None, ge=1, le=3, description="New urgency; reprioritize only"
    )
    note: Optional[str] = Field(
        default=None, max_length=500, description="Brief canon reason for audit"
    )


def _option_1_wire() -> Type[BaseModel]:
    """Build the Gaia wire with a new closed ``intention_revisions`` field."""

    return create_model(
        "SkaldGaiaWire",
        __base__=SkaldGaiaWire,
        __doc__=SkaldGaiaWire.__doc__,
        __module__=__name__,
        intention_revisions=(
            List[IntentionRevisionProbe],
            Field(
                default_factory=list,  # type: ignore[arg-type]
                description=(
                    "Revisions of open intentions when accepted canon changes "
                    "priorities."
                ),
            ),
        ),
    )


def _option_2_wire() -> Type[BaseModel]:
    """Build the Gaia wire whose replace path carries ``intention_revision``."""

    delta = create_model(
        "OrreryReplacementStateDelta",
        __base__=OrreryReplacementStateDelta,
        __doc__=OrreryReplacementStateDelta.__doc__,
        __module__=__name__,
        intention_revision=(
            Optional[IntentionRevisionDeltaProbe],
            Field(
                default=None,
                description="Revision of the intention behind this card",
            ),
        ),
    )
    adjudication = create_model(
        "OrreryAdjudication",
        __base__=OrreryAdjudication,
        __doc__=OrreryAdjudication.__doc__,
        __module__=__name__,
        replacement_state_delta=(
            Optional[delta],  # type: ignore[valid-type]
            OrreryAdjudication.model_fields["replacement_state_delta"],
        ),
    )
    return create_model(
        "SkaldGaiaWire",
        __base__=SkaldGaiaWire,
        __doc__=SkaldGaiaWire.__doc__,
        __module__=__name__,
        orrery_adjudications=(
            List[adjudication],  # type: ignore[valid-type]
            SkaldGaiaWire.model_fields["orrery_adjudications"],
        ),
    )


WIRES: Dict[str, Type[BaseModel]] = {
    "baseline": SkaldGaiaWire,
    "option_1_new_field": _option_1_wire(),
    "option_2_replace_path": _option_2_wire(),
}


def strict_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Return the strict schema the OpenAI wire sends for one Gaia wire."""

    text_format = skald_gaia_strict_text_format(cast(Type[SkaldGaiaWire], model))
    return cast(Dict[str, Any], text_format["schema"])


def lenient_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Return the omittable-field schema the local and Anthropic wires use."""

    return cast(Dict[str, Any], de_null_schema(model.model_json_schema()))


def grammar_texts(model: Type[BaseModel]) -> Dict[str, str]:
    """Return the measured grammar text of one wire for each grammar kind."""

    lenient = lenient_schema(model)
    return {
        "strict": json.dumps(strict_schema(model), ensure_ascii=False),
        "lenient": json.dumps(lenient, ensure_ascii=False),
        "prompt_guide": _render_prompt_guide(lenient, include_descriptions=False),
    }


def _listing_target(index: int, project_type: str) -> str:
    """Return the probe target of the listing row at ``index``."""

    if project_type in FIXED_TARGETS:
        return FIXED_TARGETS[project_type]
    return HOLDERS[(index + 1) % len(HOLDERS)]


def render_listing(open_count: int) -> str:
    """Render option 1's probe listing of ``open_count`` open intentions.

    An empty listing renders nothing.
    """

    if open_count < 0:
        raise ValueError(f"Open count must be >= 0, got {open_count}")
    if open_count == 0:
        return ""
    lines = []
    for index in range(open_count):
        project_type = PROJECT_TYPES[index % len(PROJECT_TYPES)]
        holder = HOLDERS[index % len(HOLDERS)]
        stage = _PROJECT_STAGE_LADDERS[project_type][0]
        target = _listing_target(index, project_type)
        lines.append(
            f"- intention {index + 1}: {holder} pursues {project_type} "
            f"at {stage}; target {target}"
        )
    return "\n".join(["Open intentions:", *lines])


def listing_tokens(
    option: str, open_counts: Sequence[int], count: Callable[[str], int]
) -> Dict[str, int]:
    """Return the per-turn listing tokens of one option at each open count."""

    if option == "option_1_new_field":
        return {str(n): count(render_listing(n)) for n in open_counts}
    if option == "option_2_replace_path":
        return {str(n): 0 for n in open_counts}
    raise ValueError(f"Unknown option {option!r}")


def build_report(open_counts: Sequence[int]) -> Dict[str, Any]:
    """Measure every wire, listing and per-call growth and return the report."""

    settings = load_settings()
    model_id = settings.apex.gaia_model or settings.apex.model
    count = estimator_for(model_id, settings=settings)

    grammar: Dict[str, Dict[str, int]] = {}
    for wire_name, model in WIRES.items():
        texts = grammar_texts(model)
        grammar[wire_name] = {kind: count(texts[kind]) for kind in GRAMMAR_KINDS}

    grammar_delta = {
        option: {
            kind: grammar[option][kind] - grammar["baseline"][kind]
            for kind in GRAMMAR_KINDS
        }
        for option in OPTIONS
    }
    listings = {
        option: listing_tokens(option, open_counts, count) for option in OPTIONS
    }
    rendered_context = {
        option: {"listing": LISTING_DESCRIPTIONS[option], "tokens": listings[option]}
        for option in OPTIONS
    }
    per_call_growth = {
        option: {
            kind: {
                str(n): grammar_delta[option][kind] + listings[option][str(n)]
                for n in open_counts
            }
            for kind in GRAMMAR_KINDS
        }
        for option in OPTIONS
    }
    return {
        "model_id": model_id,
        "baseline": BASELINE_SENTENCE,
        "verb_set": "upper_bound",
        "probe_shape": PROBE_SHAPE_SENTENCE,
        "grammar": grammar,
        "grammar_delta": grammar_delta,
        "rendered_context": rendered_context,
        "per_call_growth": per_call_growth,
    }


def _parse_open_counts(raw: str) -> List[int]:
    """Parse a comma-separated list of distinct non-negative open counts."""

    counts = [int(part) for part in raw.split(",")]
    if any(n < 0 for n in counts):
        raise argparse.ArgumentTypeError(f"Open counts must be >= 0: {raw!r}")
    if len(set(counts)) != len(counts):
        raise argparse.ArgumentTypeError(f"Open counts must be distinct: {raw!r}")
    return counts


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    """Parse the report options."""

    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--open-counts",
        type=_parse_open_counts,
        default=_parse_open_counts(DEFAULT_OPEN_COUNTS),
        help="Comma-separated open-intention counts for option 1's listing.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Measure both options and print one JSON document on stdout."""

    args = _parse_args(argv)
    report = build_report(args.open_counts)
    logger.info("Measured %d wires for %s", len(WIRES), report["model_id"])
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    raise SystemExit(main())
