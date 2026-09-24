"""Slot-specific query classification against disposable PostgreSQL casts.

Requires characters and character_aliases from the canonical template.
"""

from contextlib import closing
from types import SimpleNamespace

import psycopg2
import pytest

from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.memnon.utils.query_analysis import QueryAnalyzer
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_protagonist,
    sqlalchemy_url,
)


@pytest.mark.parametrize("db_url", [None, "", "postgresql://localhost/"])
def test_query_patterns_require_explicit_database(db_url: str | None) -> None:
    """An absent database never selects a default slot or cast."""
    with pytest.raises(ValueError, match="explicit database"):
        QueryAnalyzer(db_url=db_url)


@pytest.mark.requires_postgres
def test_query_patterns_follow_seeded_cast_and_aliases() -> None:
    """Names and escaped aliases classify and extract only the selected cast."""
    with disposable_slot_database("qa640_908_cast") as dbname:
        character_id, _ = seed_protagonist(dbname, name="Mira Vale")
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO character_aliases (character_id, alias) VALUES (%s, %s)",
                [(character_id, alias) for alias in ["Ember", "C++", "Dr. [V]", " "]],
            )
        analyzer = QueryAnalyzer(db_url=sqlalchemy_url(dbname))
        lore = SimpleNamespace(settings={}, memnon=None)
        turn_cycle = TurnCycleManager(lore)
        lore.memnon = SimpleNamespace(query_analyzer=analyzer)
        assert turn_cycle._classify_query_type("Ember") == "character"
        for name in ["Mira Vale", "EMBER", "C++", "Dr. [V]"]:
            query = f"Tell me about {name}."
            assert analyzer.analyze_query(query)["type"] == "character"
            entity = analyzer.extract_entities(query)[0]
            assert query[entity["start"] : entity["end"]].casefold() == name.casefold()
        for query in [
            "Emberstone",
            "DrX V",
            "Alex",
            "Emilia",
            "Pete",
            "Alina",
            "Dr. Nyati",
        ]:
            assert analyzer.analyze_query(query)["type"] == "general"
            assert analyzer.extract_entities(query) == []
        assert analyzer.analyze_query("Who is the stranger?")["type"] == "character"
        assert (
            analyzer.analyze_query("Ember's relationship with Mira Vale")["type"]
            == "relationship"
        )
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM character_aliases WHERE character_id = %s", (character_id,)
            )
            cursor.execute(
                "UPDATE characters SET name = 'Orin Quill' WHERE id = %s",
                (character_id,),
            )
        other = QueryAnalyzer(db_url=sqlalchemy_url(dbname))
        assert other.analyze_query("Orin Quill")["type"] == "character"
        assert other.analyze_query("Mira Vale and Ember")["type"] == "general"
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE characters SET name = '' WHERE id = %s", (character_id,)
            )
        empty = QueryAnalyzer(db_url=sqlalchemy_url(dbname))
        assert empty.character_names == []
        assert empty.analyze_query("anything")["type"] == "general"
        assert empty.extract_entities("anything") == []
    with pytest.raises(psycopg2.OperationalError, match="does not exist"):
        QueryAnalyzer(db_url=sqlalchemy_url(dbname))


@pytest.mark.requires_postgres
def test_query_alias_patterns_use_database_and_propagate_failure() -> None:
    """Real MEMNON alias loading follows the cast and rejects a broken table."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import ProgrammingError
    from sqlalchemy.orm import sessionmaker

    from nexus.agents.memnon.memnon import MEMNON
    from nexus.agents.memnon.utils.alias_search import alias_terms

    with disposable_slot_database("qa640_908_aliases") as dbname:
        character_id, _ = seed_protagonist(dbname, name="Mira Vale")
        engine = create_engine(sqlalchemy_url(dbname))
        # Exercise the production loader without initializing embedding models.
        memnon = MEMNON.__new__(MEMNON)
        memnon.Session = sessionmaker(bind=engine)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO character_aliases (character_id, alias) VALUES (:id, 'Ember'), (:id, ' ')"
                    ),
                    {"id": character_id},
                )
            aliases = memnon._load_aliases()
            assert set(aliases) == {"mira vale"}
            assert set(aliases["mira vale"]) == {
                "Mira Vale",
                "Ember",
                "You",
                "Your",
                "Yours",
                "Yourself",
            }
            for query in ("Ember", "your journey", "You", "yourself"):
                assert set(alias_terms(query, aliases)) == set(aliases["mira vale"])
            for query in ("Alex", "Emilia", "Pete", "Alina", "Dr. Nyati", "yourselves"):
                assert alias_terms(query, aliases) == []
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE characters SET name = 'Orin Quill' WHERE id = :id"),
                    {"id": character_id},
                )
                conn.execute(text("DELETE FROM character_aliases"))
            changed = memnon._load_aliases()
            assert set(changed) == {"orin quill"}
            assert alias_terms("Mira Vale and Ember", changed) == []
            assert "Orin Quill" in alias_terms("your journey", changed)
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE character_aliases RENAME TO hidden_aliases")
                )
            with pytest.raises(ProgrammingError, match="does not exist"):
                memnon._load_aliases()
        finally:
            engine.dispose()
