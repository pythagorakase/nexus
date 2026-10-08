"""Seed helpers refuse the owner's databases before they connect.

``tests.pg_fixtures.require_disposable_target`` refuses ``NEXUS_template`` and
every save slot by name, and each seed helper calls it before it opens a
connection. An owner-slot seed is always a test bug, so there is no override.
The transaction-scoped writers in ``claim_accounts_test_support`` take an open
cursor instead of a name; each reads the cursor's database name client side and
refuses an owner database the same way before it runs a statement.
"""

from __future__ import annotations

import inspect
import re
import sys
import types
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any, NoReturn

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

from nexus.api import slot_utils
from tests import pg_fixtures
from tests.pg_fixtures import (
    active_slot_routes,
    admit_disposable_database,
    connect,
    disposable_slot_database,
    require_disposable_target,
    route_slot_to_disposable,
    route_slots_to_disposable,
    seed_character,
    seed_entity_tag,
    seed_story_clock,
)
from tests.test_orrery import claim_accounts_test_support
from tests.test_orrery.checkpointed_story_support import seed_checkpointed_story
from tests.test_orrery.claim_accounts_test_support import (
    _insert_chunk,
    _insert_claim,
    _insert_pair_tag,
    _install_valence_shadow,
    insert_transaction_chain,
    insert_transaction_character,
    insert_transaction_faction,
    insert_transaction_relationship,
)

OWNER_DATABASES = (
    "save_01",
    "save_02",
    "save_03",
    "save_04",
    "save_05",
    "NEXUS_template",
    "mock",
)

# Every guarded helper with valid keyword arguments. The guard runs first, so
# none of these values reaches a database.
SEED_CALLS: dict[str, tuple[Callable[..., Any], dict[str, Any]]] = {
    "seed_protagonist": (pg_fixtures.seed_protagonist, {}),
    "seed_story_base": (pg_fixtures.seed_story_base, {}),
    "seed_committed_chunk": (
        pg_fixtures.seed_committed_chunk,
        {"raw_text": "Refused."},
    ),
    "seed_story_clock": (
        pg_fixtures.seed_story_clock,
        {"world_time": datetime(2073, 8, 1, 12, 0, tzinfo=timezone.utc)},
    ),
    "seed_story_setting": (
        pg_fixtures.seed_story_setting,
        {"setting": {"genre": "thriller", "world_name": "Refused World"}},
    ),
    "seed_zone": (
        pg_fixtures.seed_zone,
        {
            "name": "Refused Zone",
            "min_longitude": -1.0,
            "min_latitude": -1.0,
            "max_longitude": 1.0,
            "max_latitude": 1.0,
        },
    ),
    "seed_place": (pg_fixtures.seed_place, {"name": "Refused Place"}),
    "seed_character": (pg_fixtures.seed_character, {"name": "Refused Character"}),
    "seed_character_pair": (
        pg_fixtures.seed_character_pair,
        {
            "world_time": datetime(2073, 8, 1, 12, 0, tzinfo=timezone.utc),
            "actor_name": "Refused Actor",
            "target_name": "Refused Target",
        },
    ),
    "seed_faction": (pg_fixtures.seed_faction, {"name": "Refused Faction"}),
    "seed_faction_membership": (
        pg_fixtures.seed_faction_membership,
        {"character_id": 1, "faction_id": 1, "role": "member"},
    ),
    "seed_relationship": (
        pg_fixtures.seed_relationship,
        {
            "subject_character_id": 1,
            "object_character_id": 2,
            "relationship_type": "ally",
        },
    ),
    "seed_entity_tag": (
        pg_fixtures.seed_entity_tag,
        {"entity_id": 1, "tag": "kin_protector"},
    ),
    "seed_routine_anchor": (
        pg_fixtures.seed_routine_anchor,
        {"character_entity_id": 1, "place_id": 1},
    ),
    "seed_pair_tag": (
        pg_fixtures.seed_pair_tag,
        {"subject_entity_id": 1, "object_entity_id": 2, "tag": "ally"},
    ),
    "seed_legacy_faction_tag": (
        pg_fixtures.seed_legacy_faction_tag,
        {"faction_entity_id": 1, "tag": "gray_legal"},
    ),
    "seed_deprecated_category_tag": (
        pg_fixtures.seed_deprecated_category_tag,
        {"entity_id": 1, "tag": "worksite"},
    ),
    "seed_adjudication_ledger": (
        pg_fixtures.seed_adjudication_ledger,
        {"actor_entity_id": 1, "ticks": (1, 2)},
    ),
    "seed_adjudication_rulings": (
        pg_fixtures.seed_adjudication_rulings,
        {
            "template_id": "surveil",
            "bindings": {"actor": 1},
            "rulings": ((1, "defer"),),
        },
    ),
    "seed_pending_turn": (
        pg_fixtures.seed_pending_turn,
        {"user_text": "Refused.", "storyteller_text": "Refused."},
    ),
    "seed_accepted_turn": (
        pg_fixtures.seed_accepted_turn,
        {"user_text": "Refused.", "storyteller_text": "Refused."},
    ),
    "seed_played_story": (pg_fixtures.seed_played_story, {"turns": 1}),
    "seed_starved_story": (pg_fixtures.seed_starved_story, {"slot": 4}),
    "seed_checkpointed_story": (seed_checkpointed_story, {}),
    "seed_experience_candidates": (
        pg_fixtures.seed_experience_candidates,
        {"settings": {}, "label": "x"},
    ),
    "seed_experience_render_job": (
        pg_fixtures.seed_experience_render_job,
        {"settings": {}, "label": "x", "slot": 736},
    ),
}


def _refuse_connection(*args: object, **kwargs: object) -> NoReturn:
    """Fail the test the moment a seed helper dials PostgreSQL."""

    pytest.fail(
        "A seed helper opened a PostgreSQL connection before refusing its target.",
        pytrace=False,
    )


@pytest.mark.parametrize("dbname", OWNER_DATABASES)
def test_require_disposable_target_refuses_owner_databases(dbname: str) -> None:
    """Each save slot and the template raise, and the error names the database."""

    with pytest.raises(RuntimeError, match=re.escape(repr(dbname))):
        require_disposable_target(dbname)


def test_require_disposable_target_returns_a_disposable_name() -> None:
    """A disposable clone name passes through unchanged."""

    assert require_disposable_target("qa640_x") == "qa640_x"


def test_seed_calls_cover_every_seed_helper() -> None:
    """A new seed helper must join ``SEED_CALLS``, which proves its guard."""

    defined = {
        name
        for name, function in inspect.getmembers(pg_fixtures, inspect.isfunction)
        if name.startswith("seed_") and function.__module__ == pg_fixtures.__name__
    }
    assert defined | {"seed_checkpointed_story"} == set(SEED_CALLS)


@pytest.mark.parametrize("helper", sorted(SEED_CALLS))
def test_seed_helpers_refuse_owner_databases_before_connecting(
    helper: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each helper raises on every owner name without dialing PostgreSQL.

    The test installs the ``psycopg2.connect`` tripwire that the conftest
    applies offline, in both gates, so a helper that lost its guard fails here
    instead of reaching an owner database.
    """

    monkeypatch.setattr(psycopg2, "connect", _refuse_connection)
    seed, arguments = SEED_CALLS[helper]
    for dbname in OWNER_DATABASES:
        with pytest.raises(RuntimeError, match=re.escape(repr(dbname))):
            seed(dbname, **arguments)


@pytest.mark.parametrize(
    "helper",
    [
        pg_fixtures.seed_accepted_turn,
        pg_fixtures.seed_played_story,
        pg_fixtures.seed_starved_story,
    ],
)
def test_turn_factory_refuses_a_slot_label_routed_elsewhere(
    helper: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slot label must route to the clone before any turn is staged.

    The accepting commit stamps the slot on the jobs it enqueues and may
    resolve story state through it, so an unrouted slot 4 (the owner's
    ``save_04``) is refused before a connection is opened.
    """

    monkeypatch.setattr(psycopg2, "connect", _refuse_connection)
    arguments: dict[str, Any] = {
        pg_fixtures.seed_played_story: {"turns": 1},
        pg_fixtures.seed_starved_story: {},
    }.get(helper, {"user_text": "Refused.", "storyteller_text": "Refused."})
    with pytest.raises(RuntimeError, match="Slot 4 routes to 'save_04'"):
        helper("qa640_unrouted", slot=4, **arguments)


def test_turn_factory_refuses_an_ambient_slot_routed_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``slot=None`` is checked as the ambient ``NEXUS_SLOT`` the commit uses.

    A declared entity's maturation job is labelled with ``get_active_slot()``
    when the commit receives no slot, so an unrouted ambient slot 4 (the
    owner's ``save_04``) is refused before a connection is opened.
    """

    monkeypatch.setattr(psycopg2, "connect", _refuse_connection)
    monkeypatch.setenv("NEXUS_SLOT", "4")
    with pytest.raises(RuntimeError, match="NEXUS_SLOT=4 routes to 'save_04'"):
        pg_fixtures.seed_accepted_turn(
            "qa640_unrouted",
            user_text="Refused.",
            storyteller_text="Refused Courier waits by the gate.",
            slot=None,
            new_entities=[
                {
                    "kind": "character",
                    "name": "Refused Courier",
                    "summary": "A courier who never reaches the clone.",
                }
            ],
        )


def test_route_teardown_restores_a_module_first_imported_while_routed() -> None:
    """A binding made while routed resolves unrouted once the route is undone.

    A module whose ``from nexus.api.slot_utils import slot_dbname`` first runs
    inside a routed window binds the routed resolver, and the test's
    monkeypatch never records that binding. After teardown it must resolve
    the owner names again instead of a dropped clone, and a later route must
    reach it.
    """

    name = "tests._route_probe_first_import"
    probe = types.ModuleType(name)
    sys.modules[name] = probe
    try:
        with pytest.MonkeyPatch.context() as patch:
            route_slot_to_disposable(patch.setattr, slot=4, dbname="qa640_probe")
            exec("from nexus.api.slot_utils import slot_dbname", vars(probe))
            assert probe.slot_dbname(4) == "qa640_probe"
            with pytest.raises(RuntimeError, match="Slot 2 is not routed"):
                probe.slot_dbname(2)
        assert slot_utils.slot_dbname(4) == "save_04"
        assert probe.slot_dbname(4) == "save_04"
        assert probe.slot_dbname(2) == "save_02"
        assert "qa640_probe" not in slot_utils.VALID_DBNAMES

        with pytest.MonkeyPatch.context() as patch:
            route_slot_to_disposable(patch.setattr, slot=2, dbname="qa640_later")
            assert probe.slot_dbname(2) == "qa640_later"
            with pytest.raises(RuntimeError, match="Slot 4 is not routed"):
                probe.slot_dbname(4)
        assert probe.slot_dbname(2) == "save_02"
    finally:
        sys.modules.pop(name, None)


def test_nested_route_restores_the_outer_route() -> None:
    """An inner route replaces the outer one and hands it back at teardown."""

    with pytest.MonkeyPatch.context() as outer:
        route_slot_to_disposable(outer.setattr, slot=4, dbname="qa640_outer")
        with pytest.MonkeyPatch.context() as inner:
            route_slot_to_disposable(inner.setattr, slot=3, dbname="qa640_inner")
            assert slot_utils.slot_dbname(3) == "qa640_inner"
            with pytest.raises(RuntimeError, match="Slot 4 is not routed"):
                slot_utils.slot_dbname(4)
        assert slot_utils.slot_dbname(4) == "qa640_outer"
        assert slot_utils.VALID_DBNAMES == {"qa640_outer"}
    assert slot_utils.slot_dbname(3) == "save_03"


def test_multi_slot_route_sweeps_bound_and_late_imported_resolvers() -> None:
    """Each mapped slot reaches its own clone in every module; others raise.

    One probe binds ``slot_dbname`` before the route (the sweep rebinds it and
    the monkeypatch restores it), the other first binds it inside the route
    (the monkeypatch never records it). Both resolve the mapping while routed
    and the owner names after teardown.
    """

    bound_name = "tests._route_probe_bound_before"
    late_name = "tests._route_probe_bound_during"
    bound = types.ModuleType(bound_name)
    late = types.ModuleType(late_name)
    exec("from nexus.api.slot_utils import slot_dbname", vars(bound))
    unrouted = bound.slot_dbname
    sys.modules[bound_name] = bound
    sys.modules[late_name] = late
    try:
        with pytest.MonkeyPatch.context() as patch:
            route_slots_to_disposable(
                patch.setattr, {4: "qa640_left", 5: "qa640_right"}
            )
            exec("from nexus.api.slot_utils import slot_dbname", vars(late))
            for probe in (bound, late, slot_utils):
                assert probe.slot_dbname(4) == "qa640_left"
                assert probe.slot_dbname(5) == "qa640_right"
                with pytest.raises(RuntimeError, match="Slot 2 is not routed"):
                    probe.slot_dbname(2)
            assert slot_utils.VALID_DBNAMES == {"qa640_left", "qa640_right"}
            assert dict(active_slot_routes() or {}) == {
                4: "qa640_left",
                5: "qa640_right",
            }
        assert bound.slot_dbname is unrouted
        for probe in (bound, late, slot_utils):
            assert probe.slot_dbname(4) == "save_04"
            assert probe.slot_dbname(5) == "save_05"
        assert active_slot_routes() is None
        assert "qa640_left" not in slot_utils.VALID_DBNAMES
    finally:
        sys.modules.pop(bound_name, None)
        sys.modules.pop(late_name, None)


def test_route_sweeps_a_test_module_pytest_named_by_its_directory() -> None:
    """A module under ``tests/`` is swept whatever name pytest gave it.

    Pytest imports ``tests/test_runtime/<name>.py`` as ``test_runtime.<name>``
    (``tests/`` has no ``__init__.py``). Its ``from nexus.api.slot_utils
    import slot_dbname`` binding must reach the clone like a ``tests.*``
    module's, and be restored at teardown.
    """

    name = "test_runtime._route_probe_review"
    probe = types.ModuleType(name)
    probe.__file__ = str(
        Path(pg_fixtures.__file__).resolve().parent
        / "test_runtime"
        / "_route_probe_review.py"
    )
    exec("from nexus.api.slot_utils import slot_dbname", vars(probe))
    unrouted = probe.slot_dbname
    sys.modules[name] = probe
    try:
        with pytest.MonkeyPatch.context() as patch:
            route_slot_to_disposable(patch.setattr, slot=4, dbname="qa640_by_file")
            assert slot_utils.slot_dbname(4) == "qa640_by_file"
            assert probe.slot_dbname(4) == "qa640_by_file"
            with pytest.raises(RuntimeError, match="Slot 2 is not routed"):
                probe.slot_dbname(2)
        assert probe.slot_dbname is unrouted
        assert probe.slot_dbname(4) == "save_04"
    finally:
        sys.modules.pop(name, None)


def test_route_sweeps_an_aliased_resolver_binding() -> None:
    """A resolver bound under another name is routed and restored by identity.

    ``from nexus.api.slot_utils import slot_dbname as sd`` binds the unrouted
    function as ``sd``; a sweep by the name ``slot_dbname`` alone left it
    resolving owner names while a route was active.
    """

    name = "tests._route_probe_aliased"
    probe = types.ModuleType(name)
    exec("from nexus.api.slot_utils import slot_dbname as sd", vars(probe))
    unrouted = probe.sd
    sys.modules[name] = probe
    try:
        with pytest.MonkeyPatch.context() as patch:
            route_slot_to_disposable(patch.setattr, slot=4, dbname="qa640_alias")
            assert probe.sd is not unrouted
            assert probe.sd(4) == "qa640_alias"
            with pytest.raises(RuntimeError, match="Slot 2 is not routed"):
                probe.sd(2)
            # The capture the sweep resolves through is never rebound.
            assert pg_fixtures._UNROUTED_SLOT_DBNAME is unrouted
        assert probe.sd is unrouted
        assert probe.sd(4) == "save_04"
    finally:
        sys.modules.pop(name, None)


def test_multi_slot_route_keeps_its_own_copy_of_the_mapping() -> None:
    """Changing the caller's mapping after the route changes nothing."""

    routes = {4: "qa640_left"}
    with pytest.MonkeyPatch.context() as patch:
        route_slots_to_disposable(patch.setattr, routes)
        routes[4] = "save_04"
        routes[5] = "save_05"
        assert slot_utils.slot_dbname(4) == "qa640_left"
        with pytest.raises(RuntimeError, match="Slot 5 is not routed"):
            slot_utils.slot_dbname(5)


def test_single_slot_route_is_the_one_slot_mapping() -> None:
    """``route_slot_to_disposable`` installs exactly ``{slot: dbname}``."""

    with pytest.MonkeyPatch.context() as patch:
        route_slot_to_disposable(patch.setattr, slot=3, dbname="qa640_one")
        assert dict(active_slot_routes() or {}) == {3: "qa640_one"}
        assert slot_utils.VALID_DBNAMES == {"qa640_one"}


@pytest.mark.parametrize(
    ("routes", "message"),
    [
        ({}, "needs at least one slot"),
        ({4: "qa640_left", 9: "qa640_right"}, "Cannot route slot 9"),
        *(
            ({4: "qa640_left", 5: owner}, re.escape(repr(owner)))
            for owner in OWNER_DATABASES
        ),
    ],
)
def test_multi_slot_route_refuses_before_patching(
    routes: dict[int, str], message: str
) -> None:
    """An empty mapping, an unknown slot or an owner clone patches nothing."""

    resolver = slot_utils.slot_dbname
    valid = slot_utils.VALID_DBNAMES
    with pytest.MonkeyPatch.context() as patch:
        with pytest.raises(RuntimeError, match=message):
            route_slots_to_disposable(patch.setattr, routes)
        assert slot_utils.slot_dbname is resolver
        assert slot_utils.VALID_DBNAMES is valid
        assert active_slot_routes() is None


@pytest.mark.parametrize("dbname", OWNER_DATABASES)
def test_admission_refuses_an_owner_name_before_patching(dbname: str) -> None:
    """``admit_disposable_database`` never admits an owner database."""

    valid = slot_utils.VALID_DBNAMES
    with pytest.MonkeyPatch.context() as patch:
        with pytest.raises(RuntimeError, match="Refusing to seed owner database"):
            admit_disposable_database(patch.setattr, dbname)
        assert slot_utils.VALID_DBNAMES is valid


def test_admission_adds_one_name_and_routes_no_slot() -> None:
    """Admission widens ``VALID_DBNAMES`` by the one name until teardown."""

    valid = slot_utils.VALID_DBNAMES
    resolver = slot_utils.slot_dbname
    with pytest.MonkeyPatch.context() as patch:
        admit_disposable_database(patch.setattr, "qa885_admitted")
        assert slot_utils.VALID_DBNAMES == valid | {"qa885_admitted"}
        assert slot_utils.require_slot_dbname("qa885_admitted") == "qa885_admitted"
        assert slot_utils.slot_dbname is resolver
        assert active_slot_routes() is None
    assert slot_utils.VALID_DBNAMES is valid


def _sessions(cur: Any, dbname: str) -> int:
    """Return how many sessions PostgreSQL has established to ``dbname``."""

    cur.execute("SELECT sessions FROM pg_stat_database WHERE datname = %s", (dbname,))
    row = cur.fetchone()
    assert row is not None, f"pg_stat_database has no row for {dbname}"
    return int(row[0])


@pytest.mark.requires_postgres
def test_seed_helper_refuses_save_05_before_connecting() -> None:
    """A seed aimed at ``save_05`` raises before the server sees a session.

    ``pg_stat_activity`` lists only open backends, and a helper closes its
    connection before an exception leaves it, so the check reads the
    cumulative ``pg_stat_database.sessions``, which counts a session before
    ``connect`` returns; the control connection proves the counter moves. The
    call could not write even without its guard: no tag matches, so the
    ``INSERT ... SELECT`` would insert nothing.
    """

    with closing(connect("postgres")) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            control_before = _sessions(cur, "postgres")
            connect("postgres").close()
            assert _sessions(cur, "postgres") > control_before, (
                "pg_stat_database.sessions did not count a new connection, so "
                "an unchanged save_05 count would prove nothing"
            )
            before = _sessions(cur, "save_05")
            with pytest.raises(RuntimeError, match=re.escape(repr("save_05"))):
                seed_entity_tag("save_05", entity_id=0, tag="no_such_tag")
            after = _sessions(cur, "save_05")
    assert after == before, (
        f"PostgreSQL recorded {after - before} new save_05 session(s) during a "
        "refused seed"
    )


# Every transaction-scoped writer with valid arguments after its cursor. The
# guard runs first, so none of these values reaches a database.
TRANSACTION_WRITER_CALLS: dict[str, tuple[Callable[..., Any], tuple[Any, ...]]] = {
    "insert_transaction_relationship": (insert_transaction_relationship, (1, 2)),
    "insert_transaction_character": (insert_transaction_character, ("refused",)),
    "insert_transaction_faction": (insert_transaction_faction, ("refused",)),
    "insert_transaction_chain": (insert_transaction_chain, (2,)),
    "_insert_chunk": (_insert_chunk, ()),
    "_insert_pair_tag": (_insert_pair_tag, (1, 2, "ally")),
    "_insert_claim": (
        partial(_insert_claim, chunk_id=1, source_entity_id=1, birth_world_time=None),
        (),
    ),
}


def test_transaction_writer_calls_cover_every_writer() -> None:
    """A new transaction-scoped writer must join ``TRANSACTION_WRITER_CALLS``.

    Every function of the support module that writes rows through a caller's
    cursor (``insert_transaction_*`` and the ``_insert_*`` row helpers) is
    proven to refuse an owner cursor by the test below.
    """

    defined = {
        name
        for name, function in inspect.getmembers(
            claim_accounts_test_support, inspect.isfunction
        )
        if name.startswith(("insert_transaction_", "_insert_"))
        and function.__module__ == claim_accounts_test_support.__name__
    }
    assert defined == set(TRANSACTION_WRITER_CALLS)


def _refuse_execute(*args: object, **kwargs: object) -> NoReturn:
    """Fail the test the moment a transaction-scoped writer runs a statement."""

    pytest.fail(
        "A transaction-scoped writer ran a statement before refusing its target.",
        pytrace=False,
    )


def _owner_cursor(dbname: str) -> Any:
    """Return a cursor stand-in whose connection names ``dbname``.

    The writers read their target client side (``cur.connection.info.dbname``,
    libpq's ``PQdb``), so this stand-in reaches the refusal without any
    connection to the owner database, and its ``execute`` fails the test if a
    writer lost its guard.
    """

    return types.SimpleNamespace(
        connection=types.SimpleNamespace(info=types.SimpleNamespace(dbname=dbname)),
        execute=_refuse_execute,
    )


def _owner_sessions(cur: Any) -> dict[str, int]:
    """Return ``pg_stat_database.sessions`` for every owner database present."""

    cur.execute(
        "SELECT datname, sessions FROM pg_stat_database WHERE datname = ANY(%s)",
        (list(OWNER_DATABASES),),
    )
    return {str(row[0]): int(row[1]) for row in cur.fetchall()}


@pytest.mark.requires_postgres
def test_transaction_writers_refuse_owner_cursors_before_connecting() -> None:
    """Each writer raises on every owner name, and no owner session opens.

    The stand-in cursor never executes, and ``psycopg2.connect`` is a tripwire
    while the writers run. ``pg_stat_database.sessions`` counts a session
    before ``connect`` returns, so an unchanged count for every owner database
    proves no writer dialed one; the control connection proves the counter
    moves.
    """

    with closing(connect("postgres")) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            control_before = _sessions(cur, "postgres")
            connect("postgres").close()
            assert _sessions(cur, "postgres") > control_before, (
                "pg_stat_database.sessions did not count a new connection, so "
                "unchanged owner counts would prove nothing"
            )
            before = _owner_sessions(cur)
            assert "save_05" in before, "pg_stat_database has no row for save_05"
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(psycopg2, "connect", _refuse_connection)
                for name, (writer, arguments) in TRANSACTION_WRITER_CALLS.items():
                    for dbname in OWNER_DATABASES:
                        with pytest.raises(RuntimeError, match=re.escape(repr(dbname))):
                            writer(_owner_cursor(dbname), *arguments)
            after = _owner_sessions(cur)
    assert after == before, (
        f"PostgreSQL recorded new owner sessions during refused writes: "
        f"{before} -> {after}"
    )


@pytest.mark.requires_postgres
def test_transaction_relationship_writer_writes_on_a_clone() -> None:
    """On a clone, the writer attributes the public row and fills the shadow.

    The public row carries migration 115's ``manual`` producer in
    ``relationship_versions``, the ``pg_temp`` twin carries the derived
    ``valence_current``, and the caller's rollback removes both.
    """

    with disposable_slot_database("qa885_transaction_writer") as dbname:
        seed_story_clock(dbname, world_time=datetime(2100, 1, 1, tzinfo=timezone.utc))
        teller, _ = seed_character(dbname, name="Transaction Writer Teller")
        listener, _ = seed_character(dbname, name="Transaction Writer Listener")
        with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
            try:
                with conn.cursor() as cur:
                    _install_valence_shadow(cur)
                    insert_transaction_relationship(cur, teller, listener)
                    cur.execute(
                        """
                        SELECT relationship_type::text AS relationship_type,
                               emotional_valence
                        FROM public.character_relationships
                        WHERE character1_id = %s AND character2_id = %s
                        """,
                        (teller, listener),
                    )
                    assert cur.fetchall() == [
                        {
                            "relationship_type": "associate",
                            "emotional_valence": "+3|trusting",
                        }
                    ]
                    cur.execute(
                        """
                        SELECT producer
                        FROM relationship_versions
                        WHERE relationship_table = 'character_relationships'
                          AND operation = 'insert'
                          AND (old_row ->> 'character1_id')::bigint = %s
                          AND (old_row ->> 'character2_id')::bigint = %s
                        """,
                        (teller, listener),
                    )
                    assert cur.fetchall() == [{"producer": "manual"}]
                    cur.execute(
                        """
                        SELECT valence_current
                        FROM pg_temp.character_relationships
                        WHERE character1_id = %s AND character2_id = %s
                        """,
                        (teller, listener),
                    )
                    assert cur.fetchall() == [
                        {"valence_current": Decimal(3) / Decimal("5.5")}
                    ]
            finally:
                conn.rollback()
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM character_relationships "
                "WHERE character1_id = %s AND character2_id = %s",
                (teller, listener),
            )
            assert cur.fetchone()[0] == 0, "the caller's rollback removes the row"
