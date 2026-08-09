"""Unit contracts for presence-weighted temporal retrieval plumbing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2

from nexus.agents.memnon.utils import continuous_temporal_search
from nexus.agents.memnon.utils import db_access
from scripts.measure_presence_boost import ReadOnlyIDFDictionary


class _Cursor:
    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, statement: str) -> None:
        assert "MAX(id)" in statement

    def fetchone(self) -> tuple[int]:
        return (10,)


class _Connection:
    def __init__(self) -> None:
        self.closed = False

    def set_session(self, *, readonly: bool) -> None:
        assert readonly

    def cursor(self) -> _Cursor:
        return _Cursor()

    def close(self) -> None:
        self.closed = True


class _IDFCursor:
    def __init__(self) -> None:
        self.statement = ""

    def __enter__(self) -> "_IDFCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, statement: str) -> None:
        self.statement = statement

    def fetchone(self) -> tuple[int]:
        return (1,)

    def fetchall(self) -> list[tuple[str, int]]:
        return [("fixture", 0)]


class _IDFConnection:
    def __enter__(self) -> "_IDFConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def cursor(self) -> _IDFCursor:
        return _IDFCursor()


def test_measurement_idf_does_not_create_home_cache(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Harness IDF construction and build leave an empty HOME untouched."""

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(psycopg2, "connect", lambda *_args, **_kwargs: _IDFConnection())

    dictionary = ReadOnlyIDFDictionary("postgresql://test@localhost/disposable")
    assert dictionary.build_dictionary(force_rebuild=True) == {"fixture": 0.0}
    assert list(tmp_path.iterdir()) == []


def test_time_aware_search_forwards_presence_boost(
    monkeypatch: Any,
) -> None:
    """Temporal reranking retains the same roster and configured bonus."""

    captured: dict[str, Any] = {}

    def fake_hybrid_search(**kwargs: Any) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return [
            {
                "id": "4",
                "chunk_id": "4",
                "content_type": "narrative",
                "score": 0.7,
            }
        ]

    monkeypatch.setattr(psycopg2, "connect", lambda **_kwargs: _Connection())
    monkeypatch.setattr(
        continuous_temporal_search,
        "analyze_temporal_intent",
        lambda _query_text: 0.9,
    )
    monkeypatch.setattr(
        db_access,
        "execute_multi_model_hybrid_search",
        fake_hybrid_search,
    )

    results = continuous_temporal_search.execute_multi_model_time_aware_search(
        db_url="postgresql://test@localhost/disposable",
        query_text="What happened recently?",
        query_embeddings={"fixture": [1.0, 0.0, 0.0]},
        model_weights={"fixture": 1.0},
        temporal_boost_factor=0.4,
        top_k=2,
        present_character_ids=[9, 3],
        presence_boost_factor=0.25,
    )

    assert captured["present_character_ids"] == [9, 3]
    assert captured["presence_boost_factor"] == 0.25
    assert captured["top_k"] == 4
    assert results[0]["source"] == "multi_model_time_aware_search"
