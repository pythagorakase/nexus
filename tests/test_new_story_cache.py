"""Tests for the normalized new-story setup cache."""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from typing import Any, cast

import pytest

from nexus.api.new_story_cache import (
    CharacterData,
    SuggestedTrait,
    WizardCache,
    _row_to_cache,
)
import nexus.api.new_story_cache as cache_module


class FakeCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.calls.append((sql, params))
        self.rowcount = 1


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def cursor(self):
        return self.cursor_obj


def _install_fake_connection(monkeypatch) -> FakeConnection:
    fake_conn = FakeConnection()
    monkeypatch.setattr(
        cache_module, "get_connection", lambda _dbname, **kwargs: fake_conn
    )
    return fake_conn


def test_character_dict_preserves_wildcard_orrery_tags() -> None:
    """Cached protagonist tags must survive through transition assembly."""

    bestowal = {
        "applied_tags": ["elf", "oath_bound"],
        "tags_to_clear": [],
    }
    cache = WizardCache(
        character=CharacterData(
            name="Selene",
            archetype="moon-haunted exile",
            background="A runaway heir with an altered bloodline.",
            appearance="Silver-eyed and marked by lunar sigils.",
            suggested_traits=[
                SuggestedTrait("allies", "A hidden circle shelters her."),
                SuggestedTrait("contacts", "Smugglers pass her messages."),
                SuggestedTrait("obligations", "An oath binds her to return."),
            ],
            selected_trait_count=3,
            traits_confirmed=True,
            wildcard_name="Moon-Touched Blood",
            wildcard_rationale="Her blood answers old lunar rites.",
            orrery_tags=bestowal,
        )
    )

    character = cache.get_character_dict()

    assert character is not None
    assert character["wildcard"]["orrery_tags"] == bestowal


def test_row_to_cache_reads_character_orrery_tags() -> None:
    """The normalized row mapper hydrates the wildcard tag payload."""

    bestowal = {
        "applied_tags": ["ritualist"],
        "tags_to_clear": [],
    }
    compile_result = {
        "dry_run": False,
        "counters": {"prose_only_remainders": 1},
    }

    cache = _row_to_cache(
        {
            "character_name": "Mira",
            "character_archetype": "ritual scholar",
            "character_background": "Raised in a sealed archive.",
            "character_appearance": "Ink-stained hands and observant eyes.",
            "character_orrery_tags": bestowal,
            "trait_compile_result": compile_result,
        },
        selected_traits=[
            SuggestedTrait("contacts", "Archivists trade favors."),
            SuggestedTrait("resources", "She owns rare grimoires."),
            SuggestedTrait("enemies", "A rival academy hunts her."),
        ],
        selected_trait_count=3,
        traits_confirmed=True,
        wildcard_row={
            "id": 11,
            "name": "Living Gloss",
            "rationale": "A curse annotates reality.",
        },
    )

    assert cache.character.orrery_tags == bestowal
    assert cache.character.trait_compile_result == compile_result
    character_dict = cache.get_character_dict()
    assert character_dict is not None
    assert character_dict["wildcard"]["orrery_tags"] == bestowal


def test_write_cache_marks_three_selected_traits_confirmed(monkeypatch) -> None:
    """Structured trait submissions should advance slot-state phase detection."""

    fake_conn = _install_fake_connection(monkeypatch)

    cache_module.write_cache(
        dbname="save_05",
        character_draft={
            "trait_selection": {
                "selected_traits": ["contacts", "enemies", "obligations"],
                "trait_rationales": {
                    "contacts": "Route-keepers still talk to her.",
                    "enemies": "Powerful people want her silenced.",
                    "obligations": "A dying archivist gave her one last charge.",
                },
                "trait_constraints": [
                    {
                        "trait": "enemies",
                        "cold_start_relationships": "forbidden",
                    }
                ],
            }
        },
    )

    assert any(
        "traits_confirmed = TRUE" in sql for sql, _params in fake_conn.cursor_obj.calls
    )
    assert any(
        params
        == (
            "Powerful people want her silenced.",
            "forbidden",
            "[]",
            "enemies",
        )
        for _sql, params in fake_conn.cursor_obj.calls
    )


def test_write_cache_canonicalizes_legacy_reputation_trait(monkeypatch) -> None:
    """The Fame rename should not make legacy reputation selections vanish."""

    fake_conn = _install_fake_connection(monkeypatch)

    cache_module.write_cache(
        dbname="save_05",
        character_draft={
            "trait_selection": {
                "selected_traits": ["contacts", "reputation", "resources"],
                "trait_rationales": {
                    "contacts": "Informants keep her aware.",
                    "reputation": "Her name has started to travel.",
                    "resources": "She has liquid reserves.",
                },
            }
        },
    )

    assert any(
        params == ("Her name has started to travel.", "allowed", "[]", "fame")
        for _sql, params in fake_conn.cursor_obj.calls
    )


def test_write_cache_preserves_rationale_across_fame_alias(
    monkeypatch,
) -> None:
    """Rationale lookup should tolerate Fame/Reputation transition skew."""

    fake_conn = _install_fake_connection(monkeypatch)

    cache_module.write_cache(
        dbname="save_05",
        character_draft={
            "trait_selection": {
                "selected_traits": ["contacts", "fame", "resources"],
                "trait_rationales": {
                    "contacts": "Informants keep her aware.",
                    "reputation": "Her name has started to travel.",
                    "resources": "She has liquid reserves.",
                },
            }
        },
    )

    assert any(
        params == ("Her name has started to travel.", "allowed", "[]", "fame")
        for _sql, params in fake_conn.cursor_obj.calls
    )


def test_write_suggested_traits_canonicalizes_legacy_reputation(
    monkeypatch,
) -> None:
    """Concept suggestions should also write the Fame storage row."""

    fake_conn = _install_fake_connection(monkeypatch)

    cache_module.write_suggested_traits(
        "save_05",
        [{"trait": "reputation", "rationale": "People know the name."}],
    )

    assert any(
        params == ("People know the name.", "fame")
        for _sql, params in fake_conn.cursor_obj.calls
    )


def test_write_cache_creates_row_before_wildcard_tags(monkeypatch) -> None:
    """First legacy cache writes must not drop wildcard Orrery tag payloads."""

    fake_conn = _install_fake_connection(monkeypatch)

    cache_module.write_cache(
        dbname="save_05",
        character_draft={
            "wildcard": {
                "wildcard_name": "Debts That Know Her Name",
                "wildcard_description": "Favors find her even underground.",
                "orrery_tags": {
                    "applied_tags": ["obligation_magnet"],
                    "tags_to_clear": [],
                },
            }
        },
    )

    calls = [sql for sql, _params in fake_conn.cursor_obj.calls]
    row_insert_index = next(
        index
        for index, sql in enumerate(calls)
        if "INSERT INTO assets.new_story_creator" in sql
    )
    tag_update_index = next(
        index
        for index, sql in enumerate(calls)
        if "character_orrery_tags = %s::jsonb" in sql
    )

    assert row_insert_index < tag_update_index


def test_phase_resets_clear_trait_compile_result(monkeypatch) -> None:
    fake_conn = _install_fake_connection(monkeypatch)

    cache_module.clear_character_phase("save_05")
    cache_module.clear_setting_phase("save_05")

    reset_sql = "\n".join(sql for sql, _params in fake_conn.cursor_obj.calls)
    assert reset_sql.count("trait_compile_result = NULL") == 2


def test_clear_cache_deletes_without_dead_trait_compile_update(monkeypatch) -> None:
    fake_conn = _install_fake_connection(monkeypatch)

    cache_module.clear_cache("save_05")

    calls = [sql for sql, _params in fake_conn.cursor_obj.calls]
    assert "DELETE FROM assets.new_story_creator WHERE id = TRUE" in calls
    assert not any(
        "trait_compile_result = NULL" in sql
        and "UPDATE assets.new_story_creator" in sql
        for sql in calls
    )


_COLUMN_COMMENT_SQL = """
    SELECT format_type(a.atttypid, a.atttypmod), col_description(c.oid, a.attnum)
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = %s AND c.relname = %s AND a.attname = %s
      AND NOT a.attisdropped
"""


# The slot the wizard cache tests address; ``_migrated_slot_clone`` routes it.
_CLONE_SLOT = 4


@contextmanager
def _migrated_slot_clone(prefix: str) -> Iterator[str]:
    """A template clone with every pending migration (132 included) applied.

    The clone is routed as slot 4 for the life of the context, so the cache
    writers' ``require_slot_dbname`` admits it; every other slot raises.
    """
    from nexus.api import slot_utils
    from scripts import migrate
    from tests.pg_fixtures import disposable_slot_database, route_slot_to_disposable

    with (
        disposable_slot_database(prefix) as dbname,
        pytest.MonkeyPatch.context() as patch,
    ):
        # The clone carries the template's stamps; apply what it lacks.
        _, failed = migrate.migrate_database(dbname, skip_locked=False)
        assert failed == 0
        route_slot_to_disposable(patch.setattr, slot=_CLONE_SLOT, dbname=dbname)
        assert slot_utils.require_slot_dbname(slot=_CLONE_SLOT) == dbname
        assert slot_utils.require_slot_dbname(dbname=dbname) == dbname
        yield dbname


@pytest.mark.requires_postgres
def test_weird_level_round_trips_and_only_a_new_wizard_clears_it() -> None:
    """Migration 132 on a template clone: documented, checked, retry-safe state."""
    import psycopg2  # type: ignore[import-untyped]

    from nexus.api.new_story_cache import (
        clear_cache,
        clear_character_phase,
        clear_seed_phase,
        clear_setting_phase,
        guarded_wizard_write,
        init_cache,
        read_cache,
        write_weird_level,
        write_wizard_choices,
    )
    from tests.pg_fixtures import connect

    with _migrated_slot_clone("qa838_weird_level") as dbname:
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            for schema, table, column, kind in (
                ("assets", "new_story_creator", "weird_level", "text"),
                ("public", "global_variables", "genesis_weird", "jsonb"),
            ):
                cur.execute(_COLUMN_COMMENT_SQL, (schema, table, column))
                row = cur.fetchone()
                assert row is not None, f"{schema}.{table}.{column} is missing"
                assert row[0] == kind
                assert row[1] and row[1].strip(), f"{column} has no COMMENT"

        init_cache(dbname, "thread-838", _CLONE_SLOT)
        before = read_cache(dbname)
        assert before is not None and before.weird_level is None

        with guarded_wizard_write(dbname, before):
            write_weird_level(dbname, "high")
        cache = read_cache(dbname)
        assert cache is not None and cache.weird_level == "high"

        # A reply fenced on the wizard read before the selection still lands.
        with guarded_wizard_write(dbname, before):
            write_wizard_choices(["Open the gate."], dbname)

        # The column's CHECK is the last line of defence behind the Literal.
        with pytest.raises(psycopg2.errors.CheckViolation):
            write_weird_level(dbname, cast(Any, "extreme"))

        for clear_phase in (
            clear_seed_phase,
            clear_character_phase,
            clear_setting_phase,
        ):
            clear_phase(dbname)
            cleared = read_cache(dbname)
            assert cleared is not None and cleared.weird_level == "high"

        clear_cache(dbname)
        assert read_cache(dbname) is None
        init_cache(dbname, "thread-838-next", _CLONE_SLOT)
        fresh = read_cache(dbname)
        assert fresh is not None and fresh.weird_level is None


@pytest.mark.requires_postgres
def test_genesis_provenance_writes_on_the_transition_cursor() -> None:
    """The transition hook stores the resolved profile, or clears a stale one.

    The stored JSON keeps the selected level beside the resolved one; a
    transition that ran on the default stores an explicit null selection.
    """
    from nexus.api import new_story_flow
    from tests.pg_fixtures import connect

    profile = {"level": "high", "genre": "fantasy", "raw_min": 0.55, "raw_max": 0.82}
    with _migrated_slot_clone("qa838_genesis_weird") as dbname:
        with closing(connect(dbname)) as conn:
            for selected in ("high", None):
                with conn, conn.cursor() as cur:
                    new_story_flow._record_genesis_weird(
                        cur, profile, selected_level=selected
                    )
                    cur.execute("SELECT genesis_weird FROM global_variables")
                    assert cur.fetchall() == [
                        ({**profile, "selected_level": selected},)
                    ]
            with conn, conn.cursor() as cur:
                new_story_flow._record_genesis_weird(cur, None, selected_level=None)
                cur.execute("SELECT genesis_weird FROM global_variables")
                assert cur.fetchall() == [(None,)]
