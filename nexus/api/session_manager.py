"""Session management utilities for the Storyteller REST API.

Handles file-based persistence for story sessions, including:

* Metadata tracking (creation timestamps, access times, current phase)
* Turn history storage
* Context payload snapshots per turn

Sessions are stored in the repository-level ``sessions`` directory, which is
gitignored to keep runtime state out of version control.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


class SessionNotFoundError(FileNotFoundError):
    """Raised when a requested session does not exist."""


@dataclass
class SessionMetadata:
    """Metadata describing a storyteller session."""

    session_id: str
    created_at: datetime
    last_accessed: datetime
    turn_count: int = 0
    current_phase: str = "idle"
    session_name: Optional[str] = None
    initial_context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata to a JSON-friendly dictionary."""

        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "turn_count": self.turn_count,
            "current_phase": self.current_phase,
            "session_name": self.session_name,
            "initial_context": self.initial_context,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMetadata":
        """Rehydrate metadata from a dictionary."""

        return cls(
            session_id=data["session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            turn_count=int(data.get("turn_count", 0)),
            current_phase=data.get("current_phase", "idle"),
            session_name=data.get("session_name"),
            initial_context=data.get("initial_context"),
        )


@dataclass
class TurnRecord:
    """A single turn entry for a session history."""

    turn_id: str
    user_input: str
    response: Dict[str, Any]
    created_at: datetime
    options: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the turn record to JSON-serializable data."""

        return {
            "turn_id": self.turn_id,
            "user_input": self.user_input,
            "response": self.response,
            "created_at": self.created_at.isoformat(),
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TurnRecord":
        """Rehydrate a turn record from serialized data."""

        return cls(
            turn_id=data["turn_id"],
            user_input=data.get("user_input", ""),
            response=data.get("response", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            options=data.get("options", {}),
        )


class SessionManager:
    """File-backed session persistence manager."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Session directory helpers
    # ------------------------------------------------------------------
    def _session_path(self, session_id: str) -> Path:
        return self.base_path / session_id

    def _metadata_path(self, session_id: str) -> Path:
        return self._session_path(session_id) / "metadata.json"

    def _turns_path(self, session_id: str) -> Path:
        return self._session_path(session_id) / "turns.json"

    def _context_dir(self, session_id: str) -> Path:
        return self._session_path(session_id) / "context"

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def create_session(
        self,
        session_name: Optional[str] = None,
        initial_context: Optional[str] = None,
    ) -> SessionMetadata:
        """Create a new session on disk and return its metadata."""

        session_id = uuid4().hex
        session_dir = self._session_path(session_id)
        session_dir.mkdir(parents=True, exist_ok=False)
        self._context_dir(session_id).mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow()
        metadata = SessionMetadata(
            session_id=session_id,
            created_at=now,
            last_accessed=now,
            session_name=session_name,
            initial_context=initial_context,
            current_phase="ready",
        )

        self._write_json(self._metadata_path(session_id), metadata.to_dict())
        self._write_json(self._turns_path(session_id), [])
        return metadata

    def session_exists(self, session_id: str) -> bool:
        """Return True if the session directory exists."""

        return self._session_path(session_id).is_dir()

    def load_metadata(self, session_id: str) -> SessionMetadata:
        """Load session metadata from disk."""

        path = self._metadata_path(session_id)
        if not path.exists():
            raise SessionNotFoundError(f"Session {session_id} not found")

        return SessionMetadata.from_dict(self._read_json(path))

    def save_metadata(self, metadata: SessionMetadata) -> None:
        """Persist updated metadata to disk."""

        path = self._metadata_path(metadata.session_id)
        if not path.exists():
            raise SessionNotFoundError(f"Session {metadata.session_id} not found")

        metadata.last_accessed = datetime.utcnow()
        self._write_json(path, metadata.to_dict())

    def update_phase(self, session_id: str, phase: str) -> SessionMetadata:
        """Update the current phase for a session."""

        metadata = self.load_metadata(session_id)
        metadata.current_phase = phase
        self.save_metadata(metadata)
        return metadata

    def append_turn(self, session_id: str, record: TurnRecord) -> None:
        """Append a turn record to the session history."""

        history = self.load_turn_history(session_id)
        history.append(record)
        self._write_history(session_id, history)

        metadata = self.load_metadata(session_id)
        metadata.turn_count = len(history)
        metadata.current_phase = "idle"
        self.save_metadata(metadata)

    def replace_last_turn(self, session_id: str, record: TurnRecord) -> None:
        """Replace the most recent turn with a new record (for regenerations)."""

        history = self.load_turn_history(session_id)
        if not history:
            raise ValueError("Cannot replace turn in empty history")

        history[-1] = record
        self._write_history(session_id, history)

        metadata = self.load_metadata(session_id)
        metadata.turn_count = len(history)
        metadata.current_phase = "idle"
        self.save_metadata(metadata)

    def delete_session(self, session_id: str) -> None:
        """Delete a session directory and all stored data."""

        session_dir = self._session_path(session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)

    # ------------------------------------------------------------------
    # Data retrieval helpers
    # ------------------------------------------------------------------
    def list_sessions(self) -> List[SessionMetadata]:
        """Return metadata for all sessions sorted by last accessed."""

        sessions: List[SessionMetadata] = []
        for path in self.base_path.iterdir():
            if not path.is_dir():
                continue
            metadata_path = path / "metadata.json"
            if not metadata_path.exists():
                continue
            try:
                sessions.append(
                    SessionMetadata.from_dict(self._read_json(metadata_path))
                )
            except Exception:
                continue

        sessions.sort(key=lambda meta: meta.last_accessed, reverse=True)
        return sessions

    def load_turn_history(self, session_id: str) -> List[TurnRecord]:
        """Load the entire turn history for a session."""

        path = self._turns_path(session_id)
        if not path.exists():
            raise SessionNotFoundError(f"Session {session_id} not found")

        raw_history = self._read_json(path)
        return [TurnRecord.from_dict(entry) for entry in raw_history]

    def get_turn_history_slice(
        self,
        session_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> List[TurnRecord]:
        """Return a slice of turn history with pagination."""

        history = self.load_turn_history(session_id)
        start = max(offset, 0)
        end = start + max(limit, 0)
        return history[start:end]

    def get_last_turn(self, session_id: str) -> Optional[TurnRecord]:
        """Return the most recent turn, if available."""

        history = self.load_turn_history(session_id)
        if not history:
            return None
        return history[-1]

    def save_turn_context(
        self,
        session_id: str,
        turn_id: str,
        context: Dict[str, Any],
    ) -> None:
        """Persist the context payload for a specific turn."""

        context_dir = self._context_dir(session_id)
        context_dir.mkdir(parents=True, exist_ok=True)
        path = context_dir / f"{turn_id}.json"
        self._write_json(path, context)

    def load_turn_context(
        self,
        session_id: str,
        turn_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Load a stored context payload for a turn."""

        context_dir = self._context_dir(session_id)
        if not context_dir.exists():
            return None

        if turn_id is None:
            candidates = sorted(context_dir.glob("*.json"))
            if not candidates:
                return None
            path = candidates[-1]
        else:
            path = context_dir / f"{turn_id}.json"
            if not path.exists():
                return None

        return self._read_json(path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _read_json(self, path: Path) -> Any:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, data: Any) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def _write_history(self, session_id: str, history: List[TurnRecord]) -> None:
        path = self._turns_path(session_id)
        payload = [record.to_dict() for record in history]
        self._write_json(path, payload)


__all__ = [
    "SessionManager",
    "SessionMetadata",
    "TurnRecord",
    "SessionNotFoundError",
]

