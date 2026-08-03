"""Pre-commit prose mention reconciliation tests (issue #655)."""

from __future__ import annotations

import logging
import os
from typing import Any, Iterator
import uuid

import psycopg2
import pytest
from psycopg2 import sql

from nexus.agents.logon.apex_enums import ReferenceType
from nexus.agents.logon.skald_wire import (
    CharacterRef,
    PresenceBaseline,
    PresenceDelta,
    PresenceRef,
    SkaldTurnWire,
    hydrate_skald_turn,
)
from nexus.api.lore_adapter import compute_raw_text
from nexus.api.presence_reconciliation import (
    CharacterRosterRows,
    read_character_roster,
    reconcile_prose_mentions,
)


CHARACTERS = [
    {"id": 7, "name": "Kosi Adebayo", "summary": "A river pilot."},
    {"id": 9, "name": "Nneka Daramola", "summary": "A watch captain."},
]
ALIASES = [{"character_id": 7, "alias": "the Boatman"}]
ROSTER_ROWS = CharacterRosterRows(characters=CHARACTERS, aliases=ALIASES)
EMPTY_BASELINE = PresenceBaseline()


def _wire(
    narrative: str,
    *,
    choices: list[str] | None = None,
    letter: str = "Keep the river crossing unresolved.",
    presence: PresenceDelta | None = None,
) -> SkaldTurnWire:
    """Build a minimal valid extended wire response."""

    return SkaldTurnWire(
        narrative=narrative,
        choices=choices or ["Wait.", "Proceed."],
        presence=presence,
        letter=letter,
    )


@pytest.mark.parametrize(
    "prose",
    [
        "Kosi Adebayo waits beside the launch.",
        "The Boatman waits beside the launch.",
    ],
)
def test_canonical_name_and_alias_resolve_to_canonical_identity(prose: str) -> None:
    """Canonical names and aliases append the same canonical mention."""

    wire = reconcile_prose_mentions(
        _wire(prose),
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence is not None
    assert wire.presence.mentions == [
        PresenceRef(kind="character", name="Kosi Adebayo", id=7)
    ]


def test_choice_only_name_reconciles_for_every_possible_enacted_choice() -> None:
    """Offered-choice scanning is a safe superset of committed raw_text."""

    choices = ["Ask Kosi Adebayo about the launch.", "Wait by the river."]
    wire = reconcile_prose_mentions(
        _wire("The launch rocks against its mooring.", choices=choices),
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )
    enacted_raw_text = compute_raw_text(
        wire.narrative,
        {"presented": choices, "selected": 1},
        choices[0],
    )

    assert enacted_raw_text == (
        "The launch rocks against its mooring.\n\n" "Ask Kosi Adebayo about the launch."
    )
    assert wire.presence is not None
    assert wire.presence.mentions == [
        PresenceRef(kind="character", name="Kosi Adebayo", id=7)
    ]


def test_private_letter_is_not_scanned_for_presence_mentions() -> None:
    """Private correspondence never enters public detection or raw_text."""

    wire = _wire(
        "The launch rocks against its mooring.",
        letter="Have Kosi Adebayo arrive after the next crossing.",
    )

    reconcile_prose_mentions(
        wire,
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence is None


def test_end_of_turn_roster_accounts_for_detected_character() -> None:
    """A character entering this turn needs no additional mention."""

    wire = _wire(
        "Kosi Adebayo takes the wheel.",
        presence=PresenceDelta(
            enter=[CharacterRef(kind="character", name="Kosi Adebayo", id=7)]
        ),
    )

    reconcile_prose_mentions(
        wire,
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence is not None
    assert wire.presence.mentions == []


@pytest.mark.parametrize("wire_name", ["kosi adebayo", "the Boatman"])
def test_idless_noncanonical_roster_ref_does_not_account(wire_name: str) -> None:
    """Sloppy-cased and alias names cannot suppress a resolvable mention."""

    wire = _wire(
        "Kosi Adebayo takes the wheel.",
        presence=PresenceDelta(enter=[CharacterRef(kind="character", name=wire_name)]),
    )

    reconcile_prose_mentions(
        wire,
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence is not None
    assert wire.presence.mentions == [
        PresenceRef(kind="character", name="Kosi Adebayo", id=7)
    ]


def test_exact_canonical_idless_roster_ref_accounts() -> None:
    """An exact canonical name remains resolvable by commit-time SQL."""

    wire = _wire(
        "Kosi Adebayo takes the wheel.",
        presence=PresenceDelta(
            enter=[CharacterRef(kind="character", name="Kosi Adebayo")]
        ),
    )

    reconcile_prose_mentions(
        wire,
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence is not None
    assert wire.presence.mentions == []


def test_existing_mention_accounts_for_detected_character() -> None:
    """An existing current-chunk mention prevents duplication."""

    mention = PresenceRef(kind="character", name="Kosi Adebayo", id=7)
    wire = _wire(
        "The Boatman is expected before dawn.",
        presence=PresenceDelta(mentions=[mention]),
    )

    reconcile_prose_mentions(
        wire,
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence is not None
    assert wire.presence.mentions == [mention]


def test_parent_present_accounts_for_authored_exit() -> None:
    """A parent-present character remains exempt after an authored exit."""

    baseline = PresenceBaseline(
        present=[CharacterRef(kind="character", name="Kosi Adebayo", id=7)]
    )
    wire = _wire(
        "Kosi Adebayo leaves the launch behind.",
        presence=PresenceDelta(
            exit=[CharacterRef(kind="character", name="Kosi Adebayo", id=7)]
        ),
    )

    reconcile_prose_mentions(
        wire,
        presence_baseline=baseline,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence is not None
    assert wire.presence.mentions == []


def test_parent_mentioned_character_still_gets_child_mention() -> None:
    """Parent mentions are deliberately absent from the parent-present baseline."""

    wire = reconcile_prose_mentions(
        _wire("Kosi Adebayo is still expected before dawn."),
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence is not None
    assert wire.presence.mentions == [
        PresenceRef(kind="character", name="Kosi Adebayo", id=7)
    ]


@pytest.mark.parametrize(
    "prose",
    [
        "She watches the dark water without speaking.",
        "Unknown Mariner watches the dark water without speaking.",
    ],
)
def test_pronouns_and_unknown_names_add_nothing(prose: str) -> None:
    """Pronoun-only and unknown references stay outside the detector contract."""

    wire = _wire(prose)

    reconcile_prose_mentions(
        wire,
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence is None


def test_presence_none_constructs_mentions_only_delta_and_preserves_roster() -> None:
    """A mentions-only delta carries the baseline roster through hydration."""

    baseline = PresenceBaseline(
        present=[CharacterRef(kind="character", name="Nneka Daramola", id=9)]
    )
    wire = reconcile_prose_mentions(
        _wire("Kosi Adebayo answers from the far bank."),
        presence_baseline=baseline,
        roster_rows=ROSTER_ROWS,
    )

    assert wire.presence == PresenceDelta(
        mentions=[PresenceRef(kind="character", name="Kosi Adebayo", id=7)]
    )
    response = hydrate_skald_turn(wire, presence_baseline=baseline)
    assert [
        (reference.character_id, reference.reference_type)
        for reference in response.referenced_entities.characters
    ] == [
        (9, ReferenceType.PRESENT),
        (7, ReferenceType.MENTIONED),
    ]


def test_reconciliation_is_idempotent_and_round_trip_stable() -> None:
    """A second pass is silent and Pydantic revalidation preserves the mutation."""

    wire = reconcile_prose_mentions(
        _wire("Kosi Adebayo answers from the far bank."),
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )
    first_dump = wire.model_dump()

    reconcile_prose_mentions(
        wire,
        presence_baseline=EMPTY_BASELINE,
        roster_rows=ROSTER_ROWS,
    )
    revalidated = SkaldTurnWire.model_validate(wire.model_dump())

    assert wire.model_dump() == first_dump
    assert revalidated.model_dump() == first_dump


def test_warning_marker_emits_once_per_character_and_is_silent_when_clean(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only actual additions emit the grep-stable normalization marker."""

    wire = _wire("Kosi Adebayo speaks to Nneka Daramola about the crossing.")
    with caplog.at_level(
        logging.WARNING,
        logger="nexus.api.presence_reconciliation",
    ):
        reconcile_prose_mentions(
            wire,
            presence_baseline=EMPTY_BASELINE,
            roster_rows=ROSTER_ROWS,
        )
        reconcile_prose_mentions(
            wire,
            presence_baseline=EMPTY_BASELINE,
            roster_rows=ROSTER_ROWS,
        )

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "nexus.api.presence_reconciliation"
    ]
    assert messages == [
        "presence prose mention normalized: Kosi Adebayo",
        "presence prose mention normalized: Nneka Daramola",
    ]


def test_ambiguous_identity_is_not_reconciled_but_clean_identity_is(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Casefold collisions warn and fail open without choosing the wrong id."""

    roster = CharacterRosterRows(
        characters=[
            {"id": 21, "name": "Mara", "summary": None},
            {"id": 22, "name": "MARA", "summary": None},
            {"id": 23, "name": "Nneka Daramola", "summary": None},
        ],
        aliases=[],
    )
    wire = _wire("Mara speaks with Nneka Daramola beside the river.")

    with caplog.at_level(
        logging.WARNING,
        logger="nexus.api.presence_reconciliation",
    ):
        reconcile_prose_mentions(
            wire,
            presence_baseline=EMPTY_BASELINE,
            roster_rows=roster,
        )

    assert wire.presence is not None
    assert wire.presence.mentions == [
        PresenceRef(kind="character", name="Nneka Daramola", id=23)
    ]
    ambiguous_messages = [
        record.getMessage()
        for record in caplog.records
        if "presence prose mention ambiguous:" in record.getMessage()
    ]
    assert ambiguous_messages == [
        "presence prose mention ambiguous: mara candidate_ids=[21, 22]"
    ]


def test_alias_collision_participates_in_ambiguity_filter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Aliases and canonical names share one collision namespace."""

    roster = CharacterRosterRows(
        characters=[
            {"id": 31, "name": "Kosi Adebayo", "summary": None},
            {"id": 32, "name": "Harbor Master", "summary": None},
        ],
        aliases=[{"character_id": 31, "alias": "harbor master"}],
    )
    wire = _wire("The Harbor Master waits beside the launch.")

    with caplog.at_level(
        logging.WARNING,
        logger="nexus.api.presence_reconciliation",
    ):
        reconcile_prose_mentions(
            wire,
            presence_baseline=EMPTY_BASELINE,
            roster_rows=roster,
        )

    assert wire.presence is None
    assert [
        record.getMessage()
        for record in caplog.records
        if "presence prose mention ambiguous:" in record.getMessage()
    ] == ["presence prose mention ambiguous: harbor master candidate_ids=[31, 32]"]


def test_chunk_46_shape_adds_three_mentions_and_hydrates_reference_rows() -> None:
    """The issue's three off-scene names all become MENTIONED references."""

    characters = [
        {"id": 101, "name": "Ressa Morn", "summary": None},
        {"id": 102, "name": "Niko Rell", "summary": None},
        {"id": 103, "name": "Ora Pell", "summary": None},
        {"id": 104, "name": "Mara Vey", "summary": None},
    ]
    baseline = PresenceBaseline(
        present=[CharacterRef(kind="character", name="Mara Vey", id=104)]
    )
    wire = _wire(
        "Ivo Senn's account to Ressa Morn remains due before dawn. "
        "Niko Rell and Ora Pell have made no contact with this hall."
    )

    reconcile_prose_mentions(
        wire,
        presence_baseline=baseline,
        roster_rows=CharacterRosterRows(characters=characters, aliases=[]),
    )

    assert wire.presence is not None
    assert [(mention.id, mention.name) for mention in wire.presence.mentions] == [
        (101, "Ressa Morn"),
        (102, "Niko Rell"),
        (103, "Ora Pell"),
    ]
    response = hydrate_skald_turn(wire, presence_baseline=baseline)
    mentioned = [
        reference
        for reference in response.referenced_entities.characters
        if reference.reference_type == ReferenceType.MENTIONED
    ]
    assert [
        (reference.character_id, reference.character_name) for reference in mentioned
    ] == [
        (101, "Ressa Morn"),
        (102, "Niko Rell"),
        (103, "Ora Pell"),
    ]


def _connect(dbname: str) -> Any:
    """Open a direct psycopg2 connection to a disposable database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture()
def qa655_db() -> Iterator[str]:
    """Clone NEXUS_template into a qa655 database and always drop it."""

    dbname = f"qa655_{uuid.uuid4().hex[:12]}"
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )
        yield dbname
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (dbname,),
            )
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
            )
        admin.close()


@pytest.mark.requires_postgres
def test_roster_fetch_reads_characters_and_aliases_from_disposable_clone(
    qa655_db: str,
) -> None:
    """The read-only helper executes both roster queries against PostgreSQL."""

    with _connect(qa655_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL session_replication_role = replica")
            cur.execute(
                "INSERT INTO entities (kind) VALUES ('character'::entity_kind) "
                "RETURNING id"
            )
            entity_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO characters (name, summary, entity_id) "
                "VALUES (%s, %s, %s) RETURNING id",
                (
                    "QA655 Canonical Mariner",
                    "Disposable roster-fetch fixture.",
                    entity_id,
                ),
            )
            character_id = int(cur.fetchone()[0])
            character_name = "QA655 Canonical Mariner"
            alias = f"QA655 Boatman {uuid.uuid4().hex}"
            cur.execute(
                "INSERT INTO character_aliases (character_id, alias) VALUES (%s, %s)",
                (character_id, alias),
            )
            cur.execute("SET LOCAL session_replication_role = origin")

    roster = read_character_roster(qa655_db)

    assert any(
        row["id"] == character_id and row["name"] == character_name
        for row in roster.characters
    )
    assert any(
        row["character_id"] == character_id and row["alias"] == alias
        for row in roster.aliases
    )
