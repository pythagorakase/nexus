"""The issue 788 place-scale grammar measurement against a disposable clone.

``tests.pg_fixtures`` owns one ``NEXUS_template`` clone, routed as slot 5. The
Gaia baseline must be the live registry format of that clone, and the command
line must print one report from read-only sessions.
"""

from __future__ import annotations

from contextlib import closing
import json
import os
from typing import Any, Iterator

import pytest

from nexus.agents.logon.gaia_registry_schema import load_gaia_registry_wire_spec
from nexus.agents.logon.skald_wire import skald_gaia_strict_text_format
from nexus.config import load_settings
from nexus.config.story_model import resolve_seat
from nexus.telemetry.prompt_window import estimator_for
from scripts.measure_place_scale_grammar import (
    SCALE_TAG_NAMES,
    load_gaia_inputs,
    main,
    measure_gaia,
)
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
)

pytestmark = pytest.mark.requires_postgres

ENTRY_POINTS = [
    ("gaia_two_pass_openai", "gaia"),
    ("skald_single_pass_openai", "skald"),
    ("wizard_set_designer_openai", "wizard"),
]


@pytest.fixture
def scale_clone(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Yield one routed ``NEXUS_template`` clone and drop it afterwards."""

    with disposable_slot_database("qa640_788_scale") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        yield dbname


def _enum_value_count(value: Any) -> int:
    if isinstance(value, dict):
        own = len(value["enum"]) if isinstance(value.get("enum"), list) else 0
        return own + sum(_enum_value_count(nested) for nested in value.values())
    if isinstance(value, list):
        return sum(_enum_value_count(nested) for nested in value)
    return 0


def test_gaia_baseline_is_the_live_registry_format(scale_clone: str) -> None:
    vocabulary, digest = load_gaia_inputs(scale_clone)
    measurement = measure_gaia(vocabulary, digest, estimator_for("TEST"))
    live = skald_gaia_strict_text_format(
        load_gaia_registry_wire_spec(scale_clone).model
    )["schema"]

    baseline = measurement.forms["baseline"]
    assert baseline.schema == live
    assert baseline.enum_values == _enum_value_count(live)
    assert measurement.forms["tag_form"].enum_values == baseline.enum_values + 5

    with closing(connect(scale_clone)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tag FROM tags WHERE tag = ANY(%s)", (list(SCALE_TAG_NAMES),)
            )
            assert cursor.fetchall() == []


def test_main_prints_one_read_only_report(
    scale_clone: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A nested context restores PGOPTIONS before the clone is dropped: a
    # read-only ambient session could not run DROP DATABASE.
    with monkeypatch.context() as patch:
        patch.setenv("PGOPTIONS", "")

        assert main(["--dbname", scale_clone]) == 0

        report = json.loads(capsys.readouterr().out)
        assert "default_transaction_read_only=on" in os.environ["PGOPTIONS"]
        # Every connection opened with the ambient options main installed
        # reads in a read-only transaction.
        with closing(connect(scale_clone)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('transaction_read_only')")
                assert cursor.fetchone()[0] == "on"

    assert report["dbname"] == scale_clone
    assert report["read_only_session"] is True
    assert [
        (entry["name"], entry["seat"]) for entry in report["entry_points"]
    ] == ENTRY_POINTS
    settings = load_settings()
    for entry in report["entry_points"]:
        assert entry["model"] == resolve_seat(entry["seat"], settings=settings).model
