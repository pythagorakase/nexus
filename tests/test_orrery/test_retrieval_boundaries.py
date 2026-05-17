"""Regression tests for Orrery off-screen narration retrieval boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.memnon.utils.search import SearchManager


class FakeResult:
    """Tiny SQLAlchemy result stand-in."""

    def __init__(self, rows: list[Any] | None = None):
        self._rows = rows or []

    def fetchall(self) -> list[Any]:
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class CapturingSession:
    """Session stand-in that records SQL issued against retrieval surfaces."""

    def __init__(self, rows: list[Any] | None = None):
        self.rows = rows or []
        self.executed: list[tuple[str, dict[str, Any] | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        return FakeResult(self.rows)


class RecordingSearchManager:
    """SearchManager stand-in that records vector collection requests."""

    def __init__(self):
        self.vector_calls: list[dict[str, Any]] = []

    def query_vector_search(self, *, query_text, collections, filters, top_k):
        self.vector_calls.append(
            {
                "query_text": query_text,
                "collections": collections,
                "filters": filters,
                "top_k": top_k,
            }
        )
        return []


class QueryAnalyzerStub:
    """Query analyzer stand-in for MEMNON.query_memory."""

    def analyze_query(self, _query):
        return {"type": "general"}


def test_warm_slice_recent_chunks_reads_only_narrative_chunks() -> None:
    """Warm slice retrieval must not pull off-screen narration rows."""

    row = SimpleNamespace(
        id=101,
        raw_text="On-screen narrative.",
        season=1,
        episode=1,
        scene_number=3,
        world_layer="physical",
    )
    session = CapturingSession(rows=[row])
    memnon = SimpleNamespace(Session=lambda: session)

    result = MEMNON.get_recent_chunks(memnon, limit=5)

    assert result["results"][0]["id"] == 101
    issued_sql = "\n".join(sql.lower() for sql, _ in session.executed)
    assert "from narrative_chunks" in issued_sql
    assert "offscreen_narrations" not in issued_sql


def test_text_search_reads_only_narrative_chunks() -> None:
    """Text search stays on accepted narrative chunks, not Orrery prose."""

    session = CapturingSession()

    results = SearchManager.query_text_search(
        SimpleNamespace(),
        query_text="distant sirens",
        session=session,
        filters={"world_layer": "physical"},
        limit=5,
    )

    issued_sql = "\n".join(sql.lower() for sql, _ in session.executed)
    assert results == []
    assert "narrative_chunks" in issued_sql
    assert "offscreen_narrations" not in issued_sql


def test_text_search_like_fallback_reads_only_narrative_chunks() -> None:
    """Single-token LIKE fallback stays on accepted narrative chunks."""

    session = CapturingSession()

    results = SearchManager.query_text_search(
        SimpleNamespace(),
        query_text="sirens",
        session=session,
        filters={"world_layer": "physical"},
        limit=5,
    )

    issued_sql = "\n".join(sql.lower() for sql, _ in session.executed)
    assert results == []
    assert len(session.executed) == 2
    assert "ilike" in issued_sql
    assert issued_sql.count("narrative_chunks") >= 2
    assert "offscreen_narrations" not in issued_sql


def test_query_memory_vector_search_uses_only_narrative_collection() -> None:
    """The vector-search fallback cannot request an off-screen collection."""

    # TODO: add a hybrid-path boundary test if hybrid search becomes enabled
    # by default; that path uses SearchManager.perform_hybrid_search instead
    # of explicit vector collection routing.
    search_manager = RecordingSearchManager()
    memnon = SimpleNamespace(
        retrieval_settings={"default_top_k": 5},
        query_analyzer=QueryAnalyzerStub(),
        search_manager=search_manager,
        debug=False,
    )

    result = MEMNON.query_memory(
        memnon,
        query="Mara pursuit",
        k=3,
        use_hybrid=False,
    )

    assert result["metadata"]["result_count"] == 0
    assert search_manager.vector_calls == [
        {
            "query_text": "Mara pursuit",
            "collections": ["narrative_chunks"],
            "filters": None,
            "top_k": 3,
        }
    ]
