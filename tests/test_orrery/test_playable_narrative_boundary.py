"""Pure contract tests for playable-story ordering and Retrograde anchors."""

from __future__ import annotations

from contextlib import closing
from typing import Any

from tests.pg_fixtures import connect, disposable_slot_database

import pytest

from nexus.agents.orrery.coverage import sample_anchor_ids
from nexus.agents.orrery.reconstruction import (
    interval_checkpoint_due,
    playable_narrative_predicate,
)
from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from nexus.api import chunk_workflow, slot_utils
from nexus.api.chunk_workflow import ChunkState, ChunkWorkflow
from nexus.api.orrery_dev_endpoints import _default_anchor_chunk_id


class _ScalarResult:
    def __init__(self, values: list[int]):
        self._values = values

    def scalars(self) -> list[int]:
        return self._values


class _MappingResult:
    def __init__(self, row: dict[str, int | None]):
        self._row = row

    def mappings(self) -> "_MappingResult":
        return self

    def first(self) -> dict[str, int | None]:
        return self._row


class _CapturingSession:
    def __init__(self, result: Any):
        self.result = result
        self.executed: list[tuple[str, dict[str, Any] | None]] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        self.executed.append((str(statement), params))
        return self.result


def test_playable_predicate_excludes_only_the_synthetic_prologue() -> None:
    """Summary-marker compatibility does not survive the storage migration."""

    predicate = playable_narrative_predicate()

    assert RETROGRADE_PROLOGUE_MARKER in predicate
    assert "orrery:retrograde_event_summary" not in predicate
    assert "nc.authorial_directives" in predicate


def test_playable_predicate_rejects_an_unsafe_alias() -> None:
    """The helper never turns caller text into executable SQL syntax."""

    with pytest.raises(ValueError, match="Unsafe narrative table alias"):
        playable_narrative_predicate("nc; DELETE FROM narrative_chunks")


@pytest.mark.requires_postgres
def test_legacy_accept_embeds_the_previous_playable_chunk(monkeypatch) -> None:
    """Real acceptance queues predecessor 7, excluding the synthetic row at 8."""
    with disposable_slot_database(
        "qa640_800b_boundary", source_db="save_04", include_data=True
    ) as dbname:
        monkeypatch.setattr(chunk_workflow, "VALID_DATABASES", {dbname})
        monkeypatch.setattr(slot_utils, "VALID_DBNAMES", {dbname})
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM narrative_embedding_jobs")
            cur.execute(
                "SELECT authorial_directives FROM narrative_chunks "
                "WHERE authorial_directives @> %s::jsonb LIMIT 1",
                ('["' + RETROGRADE_PROLOGUE_MARKER + '"]',),
            )
            prologue_directives = cur.fetchone()[0]
            import json

            cur.execute(
                "UPDATE narrative_chunks SET authorial_directives=%s::jsonb WHERE id=8",
                (json.dumps(prologue_directives),),
            )
            cur.execute(
                "UPDATE narrative_chunks SET authorial_directives='[]', "
                "embedding_generated_at=NULL, state='finalized' WHERE id=7"
            )
            cur.execute("UPDATE narrative_chunks SET state='pending_review' WHERE id=9")
        response = ChunkWorkflow(dbname).accept_chunk(9, "boundary-test")
        assert response.state is ChunkState.FINALIZED
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, chunk_id, state::text FROM narrative_embedding_jobs"
            )
            assert cur.fetchall() == [(int(response.embedding_job_id), 7, "queued")]


def test_coverage_samples_only_playable_narrative_anchors() -> None:
    session = _CapturingSession(_ScalarResult([9, 5, 1]))

    anchors = sample_anchor_ids(session, count=3, stride=2, end_chunk_id=9)

    assert anchors == [1, 5, 9]
    sql, params = session.executed[0]
    assert RETROGRADE_PROLOGUE_MARKER in sql
    assert "AND nc.id <= :end_chunk_id" in sql
    assert params == {"stride": 2, "limit": 3, "end_chunk_id": 9}


def test_dev_default_anchor_is_latest_playable_narrative_chunk() -> None:
    session = _CapturingSession(_MappingResult({"max_id": 41}))

    anchor = _default_anchor_chunk_id(session)

    assert anchor == 41
    sql, params = session.executed[0]
    assert RETROGRADE_PROLOGUE_MARKER in sql
    assert "max(nc.id)" in sql
    assert params is None


@pytest.mark.parametrize(
    ("playable_ordinal", "expected"),
    [(1, False), (9, False), (10, True), (20, True), (21, False)],
)
def test_checkpoint_cadence_uses_playable_ordinal(
    playable_ordinal: int, expected: bool
) -> None:
    """Cadence is independent of sparse narrative_chunks primary keys."""

    assert (
        interval_checkpoint_due(playable_ordinal=playable_ordinal, interval=10)
        is expected
    )


def test_disabled_checkpoint_cadence_never_fires() -> None:
    assert interval_checkpoint_due(playable_ordinal=1, interval=0) is False


def test_checkpoint_cadence_rejects_a_nonpositive_playable_ordinal() -> None:
    with pytest.raises(ValueError, match="playable_ordinal must be positive"):
        interval_checkpoint_due(playable_ordinal=0, interval=10)
