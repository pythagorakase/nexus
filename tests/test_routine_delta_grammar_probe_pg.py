"""The issue 783 routine-delta grammar probe against a seeded disposable clone.

``tests.pg_fixtures`` owns creation, seeding, and drop: a two-turn played
story on a ``qa640_783_probe`` clone that serves slot 5 for the whole module,
so the tag library's slot validation admits the clone. Each test that reaches
the seats writes its own story pin first, through a writable session, and
then makes every later session read-only through ``PGOPTIONS``. No live slot
is touched and no provider client is built.
"""

from __future__ import annotations

from contextlib import closing
import json
from typing import Any, Iterator

import pytest

from nexus.agents.logon.gaia_registry_schema import (
    GaiaRegistryWireSpec,
    load_gaia_registry_wire_spec,
)
from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    skald_gaia_lenient_schema,
    skald_gaia_prompt_guide,
    skald_gaia_strict_text_format,
)
from nexus.agents.lore.logon_utility import (
    present_entity_refs,
    read_presence_baseline,
)
from nexus.agents.orrery.retrograde_expansion import RetrogradeExpansionWireResponse
from nexus.api.native_structured_output import openai_response_text_format
from nexus.config import load_settings
from nexus.config.story_model import StorySettings, write_story_settings
from scripts.qa_shift.routine_delta_grammar_probe import (
    PLACEMENTS,
    RoutineVocabulary,
    gaia_variant,
    measure,
)
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_played_story,
)

pytestmark = pytest.mark.requires_postgres

PROBE_SLOT = 5
READ_ONLY_PGOPTIONS = "-c default_transaction_read_only=on"
GAIA_SURFACES = ("gaia_registry_strict", "gaia_lenient", "gaia_prompt_guide")
RETROGRADE_SEATS = ("wizard", "orrery.retrograde.maturation.model_ref")


@pytest.fixture(scope="module")
def probe_clone() -> Iterator[tuple[str, int]]:
    """Yield a routed, seeded clone and its newest chunk id (the anchor).

    The slot routing stays active for the whole module: ``measure`` reaches
    the tag library, whose slot validation rejects a ``qa640_*`` name unless
    the routing patch admitted it.
    """

    with disposable_slot_database("qa640_783_probe") as dbname:
        with pytest.MonkeyPatch.context() as mp:
            route_slot_to_disposable(mp.setattr, slot=PROBE_SLOT, dbname=dbname)
            chunk_ids = seed_played_story(dbname, turns=2, slot=PROBE_SLOT)
            yield dbname, chunk_ids[-1]


def _pin(dbname: str, model: str) -> None:
    """Commit one story pin through a writable session."""

    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        write_story_settings(cur, StorySettings(skald_model=model, gaia_model=None))


def _read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every later session's transactions read-only."""

    monkeypatch.setenv("PGOPTIONS", READ_ONLY_PGOPTIONS)


def _dumps(rendering: Any) -> str:
    """Serialize a rendering as the probe measures it."""

    if isinstance(rendering, str):
        return rendering
    return json.dumps(rendering, ensure_ascii=False)


def _byte_count(rendering: Any) -> int:
    """Return a rendering's UTF-8 length."""

    return len(_dumps(rendering).encode("utf-8"))


def _registry_spec(dbname: str, anchor: int) -> GaiaRegistryWireSpec:
    """Build the registry spec exactly as the probe's item 6 does."""

    baseline = read_presence_baseline(dbname, anchor)
    return load_gaia_registry_wire_spec(
        dbname,
        scene_entity_refs=present_entity_refs(dbname, baseline),
        anchor_chunk_id=anchor,
    )


def _vocabulary(dbname: str) -> RoutineVocabulary:
    """Read the routine enum labels in ``enumsortorder``."""

    labels: dict[str, tuple[str, ...]] = {}
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        for enum_name in (
            "orrery_routine_anchor_type",
            "orrery_routine_mobility_policy",
        ):
            cur.execute(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = %s ORDER BY e.enumsortorder",
                (enum_name,),
            )
            labels[enum_name] = tuple(label for (label,) in cur.fetchall())
    return RoutineVocabulary(
        anchor_types=labels["orrery_routine_anchor_type"],
        mobility_policies=labels["orrery_routine_mobility_policy"],
    )


def _row(
    report: dict[str, Any], surface: str, seat: str, placement: str
) -> dict[str, Any]:
    """Return the one report row for a surface, seat, and placement."""

    matches = [
        row
        for row in report["rows"]
        if (row["surface"], row["seat"], row["placement"]) == (surface, seat, placement)
    ]
    assert len(matches) == 1, (surface, seat, placement, matches)
    return matches[0]


def test_null_variant_reproduces_production_renderings(
    probe_clone: tuple[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each ``before`` row measures exactly the production rendering."""

    dbname, anchor = probe_clone
    _pin(dbname, load_settings().apex.model)
    _read_only(monkeypatch)

    report = measure(dbname, anchor)

    spec = _registry_spec(dbname, anchor)
    assert report["registry_digest"] == spec.registry_digest
    production = {
        "gaia_registry_strict": skald_gaia_strict_text_format(spec.model),
        "gaia_lenient": openai_response_text_format(
            SkaldGaiaWire, schema=skald_gaia_lenient_schema()
        ),
        "gaia_prompt_guide": skald_gaia_prompt_guide(),
    }
    for surface, rendering in production.items():
        assert _row(report, surface, "gaia", "before")["bytes"] == _byte_count(
            rendering
        ), surface
    retrograde = openai_response_text_format(RetrogradeExpansionWireResponse)
    for seat in RETROGRADE_SEATS:
        assert _row(report, "retrograde_strict", seat, "before")[
            "bytes"
        ] == _byte_count(retrograde), seat
    assert _dumps(
        skald_gaia_strict_text_format(gaia_variant(spec.model, "before"))
    ) == _dumps(production["gaia_registry_strict"])


def test_both_placements_measured(
    probe_clone: tuple[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every surface and seat has all three placements, on the right objects."""

    dbname, anchor = probe_clone
    _pin(dbname, load_settings().apex.model)
    _read_only(monkeypatch)

    report = measure(dbname, anchor)

    assert len(report["rows"]) == 15
    expected_keys = {
        (surface, "gaia", placement)
        for surface in GAIA_SURFACES
        for placement in PLACEMENTS
    } | {
        ("retrograde_strict", seat, placement)
        for seat in RETROGRADE_SEATS
        for placement in PLACEMENTS
    }
    assert {
        (row["surface"], row["seat"], row["placement"]) for row in report["rows"]
    } == expected_keys
    for row in report["rows"]:
        if row["placement"] == "before":
            assert row["delta_bytes"] == 0 and row["delta_tokens"] == 0, row
        else:
            assert row["delta_bytes"] > 0, row
    for seat in RETROGRADE_SEATS:
        nested = _row(report, "retrograde_strict", seat, "sub_object")
        listed = _row(report, "retrograde_strict", seat, "top_level_list")
        assert {key: value for key, value in nested.items() if key != "placement"} == {
            key: value for key, value in listed.items() if key != "placement"
        }

    spec = _registry_spec(dbname, anchor)
    vocabulary = _vocabulary(dbname)
    nested_defs = skald_gaia_strict_text_format(
        gaia_variant(spec.model, "sub_object", vocabulary=vocabulary)
    )["schema"]["$defs"]
    listed_defs = skald_gaia_strict_text_format(
        gaia_variant(spec.model, "top_level_list", vocabulary=vocabulary)
    )["schema"]["$defs"]
    assert "routine" in nested_defs["CharacterUpdateDeltaRegistry"]["properties"]
    assert "routines" not in nested_defs["UpdatesBlockRegistry"]["properties"]
    assert "routines" in listed_defs["UpdatesBlockRegistry"]["properties"]
    assert "routines" in listed_defs["UpdatesBlockRegistry"]["required"]
    assert "routine" not in listed_defs["CharacterUpdateDeltaRegistry"]["properties"]
    assert nested_defs["RoutineAnchorBody"]["properties"]["anchor_type"]["enum"] == (
        list(vocabulary.anchor_types)
    )


def test_missing_anchor_chunk_raises(
    probe_clone: tuple[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An anchor above the newest chunk fails before any seat is resolved."""

    dbname, anchor = probe_clone
    _read_only(monkeypatch)
    missing = anchor + 1000

    with pytest.raises(ValueError, match=rf"\b{missing}\b"):
        measure(dbname, missing)


def test_non_openai_seat_raises(
    probe_clone: tuple[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first seat off OpenAI, in item-3 order, is the one named."""

    dbname, anchor = probe_clone
    _pin(dbname, "TEST")
    _read_only(monkeypatch)

    with pytest.raises(ValueError) as excinfo:
        measure(dbname, anchor)
    message = str(excinfo.value)
    assert "'wizard'" in message
    assert "'TEST'" in message
    assert "'test'" in message


def test_requires_read_only_session(
    probe_clone: tuple[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the read-only session option the probe refuses to read."""

    dbname, anchor = probe_clone
    monkeypatch.delenv("PGOPTIONS", raising=False)

    with pytest.raises(RuntimeError, match="transaction_read_only='off'"):
        measure(dbname, anchor)
