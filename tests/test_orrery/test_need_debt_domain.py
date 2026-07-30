"""Unit regressions for Orrery need-debt persistence limits."""

from datetime import datetime, timezone
from typing import Any

import pytest

from nexus.agents.orrery.events import (
    NeedDebtScoreDomainError,
    OrreryWorldClockUnavailableError,
    _apply_need_fulfillment_async,
    _apply_need_fulfillment_sync,
    _tick_world_time_async,
    _tick_world_time_sync,
    _validate_need_debt_score_domain,
)
from nexus.agents.orrery.needs import load_need_tuning


WORLD_TIME = datetime(2189, 10, 17, 22, 12, tzinfo=timezone.utc)


class _DomainCursor:
    """Focused sync double for clock selection and pre-write validation."""

    def __init__(
        self,
        *,
        source_world_time: datetime | None = WORLD_TIME,
        canonical_world_time: datetime | None = WORLD_TIME,
        debt_score: float = 0.0,
    ) -> None:
        self.source_world_time = source_world_time
        self.canonical_world_time = canonical_world_time
        self.debt_score = debt_score
        self.executed: list[tuple[str, Any]] = []
        self._fetchone: Any = None
        self._fetchall: list[Any] = []

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        normalized = " ".join(str(sql).split())
        self._fetchone = None
        self._fetchall = []
        if normalized.startswith(
            "SELECT world_time FROM chunk_metadata WHERE chunk_id"
        ):
            self._fetchone = {"world_time": self.source_world_time}
        elif "SELECT COALESCE(" in normalized and "MAX(world_time)" in normalized:
            self._fetchone = {"world_time": self.canonical_world_time}
        elif "SELECT etc.tag FROM entity_tags_current" in normalized:
            self._fetchall = []
        elif "SELECT debt_score, last_evaluated_at" in normalized:
            self._fetchone = {
                "debt_score": self.debt_score,
                "last_evaluated_at": WORLD_TIME,
            }

    def fetchone(self) -> Any:
        return self._fetchone

    def fetchall(self) -> list[Any]:
        return self._fetchall


class _AsyncDomainConnection:
    """Async twin of :class:`_DomainCursor`."""

    def __init__(
        self,
        *,
        source_world_time: datetime | None = WORLD_TIME,
        canonical_world_time: datetime | None = WORLD_TIME,
        debt_score: float = 0.0,
    ) -> None:
        self.source_world_time = source_world_time
        self.canonical_world_time = canonical_world_time
        self.debt_score = debt_score
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    async def fetchval(self, sql: str, *params: Any) -> Any:
        self.executed.append((sql, params))
        normalized = " ".join(str(sql).split())
        if normalized.startswith(
            "SELECT world_time FROM chunk_metadata WHERE chunk_id"
        ):
            return self.source_world_time
        if "SELECT COALESCE(" in normalized and "MAX(world_time)" in normalized:
            return self.canonical_world_time
        raise AssertionError(f"Unexpected fetchval SQL: {normalized}")

    async def fetch(self, sql: str, *params: Any) -> list[Any]:
        self.executed.append((sql, params))
        assert "SELECT etc.tag FROM entity_tags_current" in " ".join(str(sql).split())
        return []

    async def fetchrow(self, sql: str, *params: Any) -> Any:
        self.executed.append((sql, params))
        assert "SELECT debt_score, last_evaluated_at" in " ".join(str(sql).split())
        return {
            "debt_score": self.debt_score,
            "last_evaluated_at": WORLD_TIME,
        }

    async def execute(self, sql: str, *params: Any) -> None:
        self.executed.append((sql, params))


def test_need_debt_domain_guard_matches_postgres_numeric_rounding() -> None:
    """Reject values that numeric(8,2) would round out of range."""

    _validate_need_debt_score_domain(
        actor_entity_id=17,
        need_type="thirst",
        debt_score=999999.994,
    )

    with pytest.raises(
        NeedDebtScoreDomainError,
        match=(
            r"need debt score outside numeric\(8,2\) domain: "
            r"character=17, need=thirst, value=999999.995"
        ),
    ):
        _validate_need_debt_score_domain(
            actor_entity_id=17,
            need_type="thirst",
            debt_score=999999.995,
        )


def test_tick_world_time_uses_primary_clock_for_atemporal_chunk() -> None:
    """A NULL layer clock resolves to the primary canon, never wall time."""

    cursor = _DomainCursor(source_world_time=None)

    assert _tick_world_time_sync(cursor, 41) == WORLD_TIME
    assert not any("now()" in sql.lower() for sql, _params in cursor.executed)


@pytest.mark.asyncio
async def test_tick_world_time_async_uses_primary_clock_for_atemporal_chunk() -> None:
    """The async writer follows the same deterministic fallback chain."""

    conn = _AsyncDomainConnection(source_world_time=None)

    assert await _tick_world_time_async(conn, 41) == WORLD_TIME
    assert not any("now()" in sql.lower() for sql, _params in conn.executed)


def test_tick_world_time_raises_named_error_without_canonical_clock() -> None:
    """Missing both primary clock sources fails closed with a named error."""

    cursor = _DomainCursor(
        source_world_time=None,
        canonical_world_time=None,
    )

    with pytest.raises(
        OrreryWorldClockUnavailableError,
        match="no primary world_time or base_timestamp",
    ):
        _tick_world_time_sync(cursor, 41)


@pytest.mark.asyncio
async def test_tick_world_time_async_raises_without_canonical_clock() -> None:
    """The async writer raises the same named missing-clock diagnostic."""

    conn = _AsyncDomainConnection(
        source_world_time=None,
        canonical_world_time=None,
    )

    with pytest.raises(
        OrreryWorldClockUnavailableError,
        match="no primary world_time or base_timestamp",
    ):
        await _tick_world_time_async(conn, 41)


def test_need_domain_guard_precedes_first_sync_write() -> None:
    """The sync fulfillment arm validates before its load-or-create INSERT."""

    cursor = _DomainCursor(debt_score=999999.995)

    with pytest.raises(NeedDebtScoreDomainError):
        _apply_need_fulfillment_sync(
            cursor,
            actor_entity_id=17,
            fulfillment={"type": "thirst", "discharge_debt": 0},
            template_id="domain_ordering_sync",
            source_chunk_id=41,
            need_tuning=load_need_tuning(),
        )

    assert not any(
        sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for sql, _params in cursor.executed
    )


@pytest.mark.asyncio
async def test_need_domain_guard_precedes_first_async_write() -> None:
    """The async fulfillment arm validates before its load-or-create INSERT."""

    conn = _AsyncDomainConnection(debt_score=999999.995)

    with pytest.raises(NeedDebtScoreDomainError):
        await _apply_need_fulfillment_async(
            conn,
            actor_entity_id=17,
            fulfillment={"type": "thirst", "discharge_debt": 0},
            template_id="domain_ordering_async",
            source_chunk_id=41,
            need_tuning=load_need_tuning(),
        )

    assert not any(
        sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for sql, _params in conn.executed
    )
