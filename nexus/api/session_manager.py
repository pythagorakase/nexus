"""Session management utilities for the Storyteller REST API.

This module provides file-backed persistence for story sessions. Each session
stores metadata, turn history, and serialized context snapshots to support
recovery between requests.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

logger = logging.getLogger("nexus.api.session_manager")


def _utcnow() -> datetime:
    """Return the current UTC time with timezone information."""

    return datetime.now(timezone.utc)


def _serialize_datetime(value: datetime) -> str:
    """Serialize a timezone-aware datetime to ISO format."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO formatted datetime string."""

    return datetime.fromisoformat(value)


class SessionNotFoundError(Exception):
    """Raised when a session cannot be located on disk."""


@dataclass
class SessionMetadata:
    """Metadata describing a session's lifecycle."""

    session_id: str
    session_name: Optional[str]
    created_at: datetime
    last_accessed: datetime
    turn_count: int
    current_phase: str
    initial_context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to a JSON serializable dictionary."""

        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "created_at": _serialize_datetime(self.created_at),
            "last_accessed": _serialize_datetime(self.last_accessed),
            "turn_count": self.turn_count,
            "current_phase": self.current_phase,
            "initial_context": self.initial_context,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SessionMetadata":
        """Construct metadata from a dictionary payload."""

        return cls(
            session_id=payload["session_id"],
            session_name=payload.get("session_name"),
            created_at=_parse_datetime(payload["created_at"]),
            last_accessed=_parse_datetime(payload["last_accessed"]),
            turn_count=int(payload.get("turn_count", 0)),
            current_phase=payload.get("current_phase", "idle"),
            initial_context=payload.get("initial_context"),
        )


@dataclass
class SessionTurn:
    """Record for a single story turn."""

    turn_id: str
    user_input: str
    response: Dict[str, Any]
    created_at: datetime
    options: Optional[Dict[str, Any]] = None
    context_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the turn to a serializable dictionary."""

        return {
            "turn_id": self.turn_id,
            "user_input": self.user_input,
            "response": self.response,
            "created_at": _serialize_datetime(self.created_at),
            "options": self.options or {},
            "context_path": self.context_path,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SessionTurn":
        """Construct a turn record from a serialized dictionary."""

        return cls(
            turn_id=payload["turn_id"],
            user_input=payload.get("user_input", ""),
            response=payload.get("response", {}),
            created_at=_parse_datetime(payload["created_at"]),
            options=payload.get("options") or None,
            context_path=payload.get("context_path"),
        )


@dataclass
class SessionState:
    """Represents the full persisted state for a session."""

    metadata: SessionMetadata
    turns: List[SessionTurn]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the session state for JSON responses."""

        return {
            "metadata": self.metadata.to_dict(),
            "turns": [turn.to_dict() for turn in self.turns],
        }


class SessionManager:
    """Manage story session persistence on the filesystem."""

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path(__file__).resolve().parents[2] / "sessions"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()
        self._recover_incomplete_sessions()

    def _recover_incomplete_sessions(self) -> None:
        """Reset sessions stuck in transient phases back to idle."""

        for metadata_path in self.base_path.glob("*/metadata.json"):
            try:
                with metadata_path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if payload.get("current_phase") not in {"idle", "error"}:
                    payload["current_phase"] = "idle"
                    with metadata_path.open("w", encoding="utf-8") as handle:
                        json.dump(payload, handle, indent=2)
            except Exception as exc:  # pragma: no cover - recovery best effort
                logger.warning("Failed to recover session metadata %s: %s", metadata_path, exc)

    async def _get_lock(self, session_id: str) -> asyncio.Lock:
        """Return the asyncio lock associated with a session."""

        async with self._locks_lock:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]

    def _session_path(self, session_id: str) -> Path:
        return self.base_path / session_id

    def _metadata_path(self, session_id: str) -> Path:
        return self._session_path(session_id) / "metadata.json"

    def _turns_path(self, session_id: str) -> Path:
        return self._session_path(session_id) / "turns.json"

    def _context_dir(self, session_id: str) -> Path:
        return self._session_path(session_id) / "context"

    async def create_session(
        self, session_name: Optional[str] = None, initial_context: Optional[str] = None
    ) -> SessionState:
        """Create a new session and persist its metadata."""

        session_id = str(uuid4())
        session_dir = self._session_path(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        self._context_dir(session_id).mkdir(parents=True, exist_ok=True)

        now = _utcnow()
        metadata = SessionMetadata(
            session_id=session_id,
            session_name=session_name,
            created_at=now,
            last_accessed=now,
            turn_count=0,
            current_phase="idle",
            initial_context=initial_context,
        )

        with self._metadata_path(session_id).open("w", encoding="utf-8") as handle:
            json.dump(metadata.to_dict(), handle, indent=2)

        with self._turns_path(session_id).open("w", encoding="utf-8") as handle:
            json.dump([], handle, indent=2)

        async with self._locks_lock:
            self._locks[session_id] = asyncio.Lock()

        return SessionState(metadata=metadata, turns=[])

    async def load_session(self, session_id: str) -> SessionState:
        """Load a session state from disk."""

        metadata_path = self._metadata_path(session_id)
        if not metadata_path.exists():
            raise SessionNotFoundError(session_id)

        with metadata_path.open("r", encoding="utf-8") as handle:
            metadata_payload = json.load(handle)
        metadata = SessionMetadata.from_dict(metadata_payload)

        turns_path = self._turns_path(session_id)
        if turns_path.exists():
            with turns_path.open("r", encoding="utf-8") as handle:
                turns_payload = json.load(handle)
            turns = [SessionTurn.from_dict(item) for item in turns_payload]
        else:
            turns = []

        return SessionState(metadata=metadata, turns=turns)

    async def list_sessions(self) -> List[SessionMetadata]:
        """Return metadata for all known sessions sorted by last access."""

        sessions: List[SessionMetadata] = []
        for metadata_path in self.base_path.glob("*/metadata.json"):
            try:
                with metadata_path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                sessions.append(SessionMetadata.from_dict(payload))
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to load metadata at %s: %s", metadata_path, exc)
        sessions.sort(key=lambda meta: meta.last_accessed, reverse=True)
        return sessions

    async def update_metadata(
        self,
        session_id: str,
        *,
        current_phase: Optional[str] = None,
        last_accessed: Optional[datetime] = None,
    ) -> SessionMetadata:
        """Update persisted metadata for the given session."""

        lock = await self._get_lock(session_id)
        async with lock:
            state = await self.load_session(session_id)
            metadata = state.metadata
            if current_phase is not None:
                metadata.current_phase = current_phase
            if last_accessed is not None:
                metadata.last_accessed = last_accessed
            with self._metadata_path(session_id).open("w", encoding="utf-8") as handle:
                json.dump(metadata.to_dict(), handle, indent=2)
            return metadata

    async def append_turn(
        self,
        session_id: str,
        *,
        user_input: str,
        response: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
        context_payload: Optional[Dict[str, Any]] = None,
    ) -> SessionTurn:
        """Append a turn to the session history."""

        lock = await self._get_lock(session_id)
        async with lock:
            state = await self.load_session(session_id)
            metadata = state.metadata
            turn_id = str(uuid4())
            created_at = _utcnow()

            context_path: Optional[str] = None
            if context_payload:
                context_dir = self._context_dir(session_id)
                context_dir.mkdir(parents=True, exist_ok=True)
                context_path = f"{turn_id}.json"
                with (context_dir / context_path).open("w", encoding="utf-8") as handle:
                    json.dump(context_payload, handle, indent=2, default=str)

            turn = SessionTurn(
                turn_id=turn_id,
                user_input=user_input,
                response=response,
                created_at=created_at,
                options=options,
                context_path=context_path,
            )

            turns_path = self._turns_path(session_id)
            turns: List[Dict[str, Any]]
            if turns_path.exists():
                with turns_path.open("r", encoding="utf-8") as handle:
                    turns = json.load(handle)
            else:
                turns = []

            turns.append(turn.to_dict())
            with turns_path.open("w", encoding="utf-8") as handle:
                json.dump(turns, handle, indent=2)

            metadata.turn_count = len(turns)
            metadata.last_accessed = created_at
            with self._metadata_path(session_id).open("w", encoding="utf-8") as handle:
                json.dump(metadata.to_dict(), handle, indent=2)

            return turn

    async def load_turn_history(
        self, session_id: str, *, limit: int, offset: int
    ) -> List[SessionTurn]:
        """Load a slice of the turn history for a session."""

        state = await self.load_session(session_id)
        turns = state.turns
        if offset >= len(turns):
            return []
        return turns[::-1][offset : offset + limit]

    async def load_context(self, session_id: str, turn_id: Optional[str] = None) -> Dict[str, Any]:
        """Return the stored context payload for the most recent or specified turn."""

        state = await self.load_session(session_id)
        turns = state.turns
        if not turns:
            return {}

        target_turn: Optional[SessionTurn] = None
        if turn_id is not None:
            for turn in turns:
                if turn.turn_id == turn_id:
                    target_turn = turn
                    break
        if target_turn is None:
            target_turn = turns[-1]

        if not target_turn.context_path:
            return {}

        context_file = self._context_dir(session_id) / target_turn.context_path
        if not context_file.exists():
            return {}

        with context_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    async def delete_session(self, session_id: str) -> None:
        """Delete a session directory and remove in-memory locks."""

        session_dir = self._session_path(session_id)
        if not session_dir.exists():
            raise SessionNotFoundError(session_id)

        for path in sorted(session_dir.glob("**/*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

        session_dir.rmdir()

        async with self._locks_lock:
            self._locks.pop(session_id, None)

    async def replace_last_turn(
        self,
        session_id: str,
        *,
        user_input: str,
        response: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
        context_payload: Optional[Dict[str, Any]] = None,
    ) -> SessionTurn:
        """Replace the most recent turn with a new response."""

        lock = await self._get_lock(session_id)
        async with lock:
            state = await self.load_session(session_id)
            if not state.turns:
                raise ValueError("No turns available to regenerate")

            turn_id = state.turns[-1].turn_id

            context_path: Optional[str] = None
            if context_payload:
                context_dir = self._context_dir(session_id)
                context_dir.mkdir(parents=True, exist_ok=True)
                context_path = f"{turn_id}.json"
                with (context_dir / context_path).open("w", encoding="utf-8") as handle:
                    json.dump(context_payload, handle, indent=2, default=str)

            new_turn = SessionTurn(
                turn_id=turn_id,
                user_input=user_input,
                response=response,
                created_at=_utcnow(),
                options=options,
                context_path=context_path,
            )

            turns_path = self._turns_path(session_id)
            with turns_path.open("r", encoding="utf-8") as handle:
                turns_payload = json.load(handle)

            if not turns_payload:
                raise ValueError("Turn history corrupted")

            turns_payload[-1] = new_turn.to_dict()
            with turns_path.open("w", encoding="utf-8") as handle:
                json.dump(turns_payload, handle, indent=2)

            metadata = state.metadata
            metadata.last_accessed = _utcnow()
            with self._metadata_path(session_id).open("w", encoding="utf-8") as handle:
                json.dump(metadata.to_dict(), handle, indent=2)

            return new_turn

    async def finalize_turn(self, session_id: str) -> None:
        """Background cleanup hook executed after a turn completes."""

        try:
            await self.update_metadata(session_id, last_accessed=_utcnow(), current_phase="idle")
        except SessionNotFoundError:
            logger.debug("Finalize skipped for deleted session %s", session_id)

    async def get_last_turn(self, session_id: str) -> SessionTurn:
        """Return the most recent turn for the session."""

        state = await self.load_session(session_id)
        if not state.turns:
            raise ValueError("Session has no recorded turns")
        return state.turns[-1]

    async def iter_sessions(self) -> Iterable[SessionMetadata]:
        """Yield metadata for all sessions without sorting."""

        for metadata_path in self.base_path.glob("*/metadata.json"):
            try:
                with metadata_path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                yield SessionMetadata.from_dict(payload)
            except Exception as exc:  # pragma: no cover
                logger.debug("Skipping metadata at %s: %s", metadata_path, exc)

