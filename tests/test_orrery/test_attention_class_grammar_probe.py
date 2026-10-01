"""Tests for the read-only #784 attention-class grammar probe (784-S1).

Offline tests import the probe's builders and compare them with the production
renderers. PostgreSQL tests use one disposable ``qa640_784s1`` clone of
``NEXUS_template`` (it carries the seeded registry), routed as slot 5.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import psycopg2
import pytest

from nexus.agents.logon.gaia_registry_schema import load_gaia_registry_wire_spec
from nexus.agents.logon.skald_wire import (
    skald_gaia_lenient_schema,
    skald_gaia_prompt_guide,
    skald_gaia_strict_text_format,
    skald_wire_lenient_schema,
    skald_wire_prompt_guide,
    skald_wire_strict_text_format,
)
from nexus.agents.lore.logon_utility import _orrery_card_line
from nexus.agents.orrery.cards import card_key, proposal_handles, rendered_selection
from nexus.config import load_settings
from nexus.config.settings_models import OrreryPromptSettings
from nexus.telemetry.prompt_window import estimator_for
from scripts.qa_shift import attention_class_grammar_probe as probe
from tests.pg_fixtures import disposable_slot_database, route_slot_to_disposable

STATIC_SEATS = ("gaia", "single_pass")


def _serialized(value: Any) -> str:
    return probe.serialize_rendering(value)


def _gaia_estimator() -> Any:
    settings = load_settings()
    return estimator_for(probe.gaia_model_id(settings), settings=settings)


def test_head_builders_match_production() -> None:
    head = probe.head_renderings()
    production = {
        ("gaia", "strict"): skald_gaia_strict_text_format()["schema"],
        ("gaia", "lenient"): skald_gaia_lenient_schema(),
        ("gaia", "guide"): skald_gaia_prompt_guide(),
        ("single_pass", "strict"): skald_wire_strict_text_format()["schema"],
        ("single_pass", "lenient"): skald_wire_lenient_schema(),
        ("single_pass", "guide"): skald_wire_prompt_guide(),
    }
    assert set(head) == set(production)
    for key, rendering in production.items():
        assert _serialized(head[key]) == _serialized(rendering), key
        if not isinstance(rendering, str):
            # The JSON key order is part of what the provider receives.
            assert json.dumps(head[key]) == json.dumps(rendering), key


def test_ceiling_changes_only_the_adjudication_definition() -> None:
    head = probe.head_renderings()
    ceiling = probe.ceiling_renderings()
    for seat in STATIC_SEATS:
        for rendering in ("strict", "lenient"):
            head_schema = head[(seat, rendering)]
            ceiling_schema = ceiling[(seat, rendering)]
            assert ceiling_schema["title"] == head_schema["title"]
            assert set(ceiling_schema["$defs"]) == set(head_schema["$defs"])
            assert {k: v for k, v in ceiling_schema.items() if k != "$defs"} == {
                k: v for k, v in head_schema.items() if k != "$defs"
            }
            changed = {
                name
                for name in head_schema["$defs"]
                if head_schema["$defs"][name] != ceiling_schema["$defs"][name]
            }
            assert changed == {"OrreryAdjudication"}
            head_adj = head_schema["$defs"]["OrreryAdjudication"]
            ceiling_adj = ceiling_schema["$defs"]["OrreryAdjudication"]
            assert set(ceiling_adj["properties"]) - set(head_adj["properties"]) == {
                "attention"
            }
            assert ceiling_adj["properties"]["attention"]["description"] == (
                "Attention class of the proposal."
            )
            assert ceiling_adj["description"] == head_adj["description"]
            if rendering == "strict":
                assert ceiling_adj["required"] == head_adj["required"] + ["attention"]
            else:
                assert ceiling_adj.get("required") == head_adj.get("required")
            probe.assert_ceiling_shape(
                head_schema, ceiling_schema, seat=seat, rendering=rendering
            )

        head_guide = head[(seat, "guide")].split("\n")
        ceiling_guide = ceiling[(seat, "guide")].split("\n")
        assert len(ceiling_guide) == len(head_guide) + 1
        start = head_guide.index("OrreryAdjudication{")
        close = head_guide.index("}", start)
        assert head_guide[close - 1].startswith("replacement_event_type")
        expected_line = 'attention?:string|enum=["background","meaningful","urgent"]'
        if seat == "single_pass":
            expected_line += '|"Attention class of the proposal."'
        assert ceiling_guide == (
            head_guide[:close] + [expected_line] + head_guide[close:]
        )
        probe.assert_ceiling_shape(
            head[(seat, "guide")],
            ceiling[(seat, "guide")],
            seat=seat,
            rendering="guide",
        )

    for key, rendering in head.items():
        head_bytes = len(_serialized(rendering).encode("utf-8"))
        ceiling_bytes = len(_serialized(ceiling[key]).encode("utf-8"))
        assert ceiling_bytes > head_bytes, key


def test_no_wire_property_names_the_class() -> None:
    head = probe.head_renderings()
    ceiling = probe.ceiling_renderings()
    for key, rendering in head.items():
        if key[1] == "guide":
            continue
        names = probe.property_names(rendering)
        # Nested definitions are walked: these live only under $defs.
        assert {"proposal_id", "replacement_event_type"} <= names, key
        assert not names & probe.CLASS_PROPERTY_NAMES, key
        probe.assert_class_off_wire(rendering, str(key))
        assert "attention" in probe.property_names(ceiling[key]), key
        with pytest.raises(probe.ProbePremiseError):
            probe.assert_class_off_wire(ceiling[key], str(key))


def _seeded_card(template_id: str, index: int) -> dict[str, Any]:
    return {
        "template_id": template_id,
        "binding_hash": f"{index:02d}{template_id}".ljust(16, "0"),
        "binding_names": {"actor": f"Actor {index}"},
        "branch_label": f"{template_id} branch {index}",
        "position": None,
    }


def test_card_block_arms_on_a_seeded_snapshot() -> None:
    order = (
        "stroll",
        "hide",
        "stroll",
        "sleep",
        "surveil",
        "honor_debt",
        "check_on_dependent",
    )
    resolutions = [
        _seeded_card(template, index) for index, template in enumerate(order)
    ]
    snapshot = {"resolutions": resolutions, "scene_pressures": []}
    caps = OrreryPromptSettings(max_rendered_proposals=5)
    estimator = _gaia_estimator()

    arm_lines = probe.card_block_arms(snapshot, caps)
    rows = probe.card_block_rows("seeded", snapshot, caps, estimator)
    arms = {(row["roster"], row["arm"]): row for row in rows}
    expected_arm_keys = [(None, "head")] + [
        (roster, arm)
        for roster in ("R1", "R2")
        for arm in ("drop_only", "refill", "head_marked", "refill_marked")
    ]
    assert list(arm_lines) == expected_arm_keys
    assert [(row["roster"], row["arm"]) for row in rows] == expected_arm_keys

    def expected_pairs(cards: list[dict[str, Any]]) -> list[tuple[dict, str]]:
        """Render ``cards`` as the turn prompt does; positions index ``cards``."""

        selection = rendered_selection({"resolutions": cards}, caps)
        handles = proposal_handles(selection)
        by_key = {card_key(card): (index, card) for index, card in enumerate(cards)}
        pairs = []
        for item in selection:
            index, card = by_key[item["proposal_id"]]
            pairs.append(
                (
                    card,
                    _orrery_card_line(
                        card,
                        handles[item["proposal_id"]],
                        position=index,
                        description=card["branch_label"],
                    ),
                )
            )
        return pairs

    def check_arm(
        key: tuple[Any, str], pairs: list[tuple[dict, str]], count: int
    ) -> None:
        cards, lines = arm_lines[key]
        expected_ids = [card_key(card) for card, _ in pairs]
        expected_text = [line for _, line in pairs]
        # Line text, not only token totals: a wrong position or marker shows here.
        assert lines == expected_text, key
        assert [card_key(card) for card in cards] == expected_ids, key
        row = arms[key]
        assert row["lines"] == count, key
        assert row["proposal_ids"] == expected_ids, key
        assert row["tokens"] == estimator("\n".join(expected_text)), key

    head_pairs = expected_pairs(resolutions)
    assert [card["template_id"] for card, _ in head_pairs] == list(order[:5])
    assert [line.split(" ")[1] for _, line in head_pairs] == [
        f"[{index}]" for index in range(5)
    ]
    check_arm((None, "head"), head_pairs, 5)

    for roster, drop_count, refill_count in (("R1", 3, 5), ("R2", 2, 4)):
        members = probe.ROSTERS[roster]

        def marked(pairs: list[tuple[dict, str]]) -> list[tuple[dict, str]]:
            return [
                (
                    card,
                    f"{line} · "
                    + (
                        "background" if card["template_id"] in members else "meaningful"
                    ),
                )
                for card, line in pairs
            ]

        kept = [pair for pair in head_pairs if pair[0]["template_id"] not in members]
        check_arm((roster, "drop_only"), kept, drop_count)

        filtered = [card for card in resolutions if card["template_id"] not in members]
        refill_pairs = expected_pairs(filtered)
        # Refill positions index the filtered list, so they differ from head's.
        assert [line.split(" ")[1] for _, line in refill_pairs] == [
            f"[{index}]" for index in range(refill_count)
        ]
        assert [card_key(card) for card, _ in refill_pairs][-2:] == [
            card_key(resolutions[5]),
            card_key(resolutions[6]),
        ]
        check_arm((roster, "refill"), refill_pairs, refill_count)

        head_marked = marked(head_pairs)
        assert [line.rsplit(" · ", 1)[1] for _, line in head_marked] == [
            "background" if template in members else "meaningful"
            for template in order[:5]
        ]
        check_arm((roster, "head_marked"), head_marked, 5)
        check_arm((roster, "refill_marked"), marked(refill_pairs), refill_count)


@pytest.fixture(scope="module")
def qa640_784s1_clone() -> Iterator[str]:
    """One disposable template clone, routed as slot 5 for the module."""

    routing = pytest.MonkeyPatch()
    with disposable_slot_database("qa640_784s1") as dbname:
        try:
            route_slot_to_disposable(routing.setattr, slot=5, dbname=dbname)
            yield dbname
        finally:
            routing.undo()


@pytest.mark.requires_postgres
def test_registry_head_and_ceiling_on_clone(qa640_784s1_clone: str) -> None:
    spec = probe.load_registry_spec(qa640_784s1_clone)
    head = probe.registry_head_rendering(spec)
    production = skald_gaia_strict_text_format(
        load_gaia_registry_wire_spec(qa640_784s1_clone, scene_entity_refs=()).model
    )["schema"]
    assert _serialized(head) == _serialized(production)
    probe.assert_class_off_wire(head, "gaia_registry/strict/head")

    ceiling = probe.ceiling_renderings(spec.model)[("gaia_registry", "strict")]
    probe.assert_ceiling_shape(head, ceiling, seat="gaia_registry", rendering="strict")
    adjudication = ceiling["$defs"]["OrreryAdjudicationRegistry"]
    # The registry ceiling keeps the live enum for replacement_event_type.
    assert (
        adjudication["properties"]["replacement_event_type"]
        == head["$defs"]["OrreryAdjudicationRegistry"]["properties"][
            "replacement_event_type"
        ]
    )
    assert len(_serialized(ceiling)) > len(_serialized(head))


@pytest.mark.requires_postgres
def test_probe_session_is_read_only(qa640_784s1_clone: str) -> None:
    with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
        with probe.read_only_cursor(qa640_784s1_clone) as cur:
            cur.execute("UPDATE narrative_chunks SET raw_text = raw_text WHERE false")
