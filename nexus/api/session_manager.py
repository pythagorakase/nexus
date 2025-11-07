"""Session persistence utilities for the Storyteller REST API.

Stores session metadata and turn history on disk so that story progress
survives process restarts. Each session gets its own directory containing:

```
sessions/{session_id}/
├── metadata.json
├── turns.json
└── context/
    └── {turn_id}.json
```

This module provides a thin abstraction for reading and writing those files
with basic concurrency protection. The FastAPI layer owns the higher-level
logic (calling LORE, streaming updates) while this module focuses solely on
persistence and retrieval.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utc_now() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(timezone.utc).isoformat()


class SessionManagerError(RuntimeError):
    """Base exception for session persistence failures."""


class SessionNotFoundError(SessionManagerError):
    """Raised when attempting to load a missing session."""


@dataclass
class SessionMetadata:
    """Metadata describing a story session."""

    session_id: str
    session_name: Optional[str] = None
    created_at: str = field(default_factory=_utc_now)
    last_accessed: str = field(default_factory=_utc_now)
    turn_count: int = 0
    current_phase: str = "idle"
    initial_context: Optional[str] = None


@dataclass
class TurnRecord:
    """A single user/AI exchange within a session."""

    turn_id: str
    timestamp: str
    user_input: str
    response: Dict[str, Any]
    options: Dict[str, Any] = field(default_factory=dict)
    phase_states: Dict[str, Any] = field(default_factory=dict)
    memory_state: Dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """Manage on-disk session persistence for the storyteller API."""

    def __init__(self, base_path: Optional[Path] = None) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self.base_path = Path(base_path) if base_path else repo_root / "sessions"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Session lifecycle helpers
    # ------------------------------------------------------------------
    def create_session(
        self,
        session_name: Optional[str] = None,
        initial_context: Optional[str] = None,
    ) -> SessionMetadata:
        """Create a new session and return its metadata."""

        session_id = str(uuid.uuid4())
        metadata = SessionMetadata(
            session_id=session_id,
            session_name=session_name,
            initial_context=initial_context,
        )

        session_dir = self._session_path(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "context").mkdir(exist_ok=True)

        self._write_json(session_dir / "metadata.json", asdict(metadata))
        self._write_json(session_dir / "turns.json", [])

        return metadata

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return metadata for all known sessions."""

        sessions: List[Dict[str, Any]] = []
        for path in sorted(self.base_path.glob("*/metadata.json")):
            try:
                metadata = self._read_json(path)
                sessions.append(metadata)
            except FileNotFoundError:
                continue
        return sessions

    def delete_session(self, session_id: str) -> None:
        """Remove a session and all associated files."""

        session_dir = self._session_path(session_id)
        if not session_dir.exists():
            raise SessionNotFoundError(f"Session {session_id} not found")

        def _remove_tree(path: Path) -> None:
            for child in path.iterdir():
                if child.is_dir():
                    _remove_tree(child)
                else:
                    child.unlink(missing_ok=True)
            path.rmdir()

        _remove_tree(session_dir)

    # ------------------------------------------------------------------
    # Session metadata
    # ------------------------------------------------------------------
    def load_metadata(self, session_id: str) -> SessionMetadata:
        """Load metadata for an existing session."""

        metadata_path = self._session_path(session_id) / "metadata.json"
        if not metadata_path.exists():
            raise SessionNotFoundError(f"Session {session_id} not found")

        data = self._read_json(metadata_path)
        return SessionMetadata(**data)

    def save_metadata(self, metadata: SessionMetadata) -> None:
        """Persist session metadata to disk."""

        metadata.last_accessed = _utc_now()
        metadata_path = self._session_path(metadata.session_id) / "metadata.json"
        self._write_json(metadata_path, asdict(metadata))

    def touch_session(self, session_id: str, phase: Optional[str] = None) -> SessionMetadata:
        """Update last accessed time and optionally current phase."""

        metadata = self.load_metadata(session_id)
        if phase is not None:
            metadata.current_phase = phase
        self.save_metadata(metadata)
        return metadata

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """Return metadata and summary for a session."""

        metadata = self.load_metadata(session_id)
        turns = self._load_turns(session_id)
        return {
            "metadata": asdict(metadata),
            "turn_count": len(turns),
            "last_turn": turns[-1] if turns else None,
        }

    # ------------------------------------------------------------------
    # Turn history
    # ------------------------------------------------------------------
    def append_turn(
        self,
        session_id: str,
        turn: TurnRecord,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append a new turn to the session history."""

        with self._session_lock(session_id):
            metadata = self.load_metadata(session_id)
            turns = self._load_turns(session_id)
            turns.append(asdict(turn))
            metadata.turn_count = len(turns)
            metadata.current_phase = "idle"
            self._write_turns(session_id, turns)
            self.save_metadata(metadata)

            if context_snapshot is not None:
                context_dir = self._session_path(session_id) / "context"
                context_dir.mkdir(exist_ok=True)
                context_path = context_dir / f"{turn.turn_id}.json"
                self._write_json(context_path, context_snapshot)

    def replace_last_turn(
        self,
        session_id: str,
        turn: TurnRecord,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Replace the most recent turn with a new record."""

        with self._session_lock(session_id):
            metadata = self.load_metadata(session_id)
            turns = self._load_turns(session_id)
            if not turns:
                raise SessionManagerError("Cannot regenerate turn: history is empty")

            turns[-1] = asdict(turn)
            metadata.turn_count = len(turns)
            metadata.current_phase = "idle"
            self._write_turns(session_id, turns)
            self.save_metadata(metadata)

            if context_snapshot is not None:
                context_dir = self._session_path(session_id) / "context"
                context_dir.mkdir(exist_ok=True)
                context_path = context_dir / f"{turn.turn_id}.json"
                self._write_json(context_path, context_snapshot)

    def get_history(self, session_id: str, limit: int, offset: int) -> List[Dict[str, Any]]:
        """Return a slice of the session history (newest first)."""

        turns = self._load_turns(session_id)
        total = len(turns)
        if total == 0:
            return []

        if offset < 0 or limit < 0:
            raise SessionManagerError("Limit and offset must be non-negative")

        start_index = max(total - offset - limit, 0)
        end_index = total - offset
        sliced = turns[start_index:end_index]
        return list(reversed(sliced))

    def load_latest_context(self, session_id: str) -> Dict[str, Any]:
        """Return the most recent context snapshot for debugging."""

        context_dir = self._session_path(session_id) / "context"
        if not context_dir.exists():
            raise SessionManagerError("No context available for session")

        candidates = sorted(context_dir.glob("*.json"))
        if not candidates:
            raise SessionManagerError("No context snapshots found")

        latest_path = max(candidates, key=lambda p: p.stat().st_mtime)
        data = self._read_json(latest_path)
        data["turn_id"] = latest_path.stem
        return data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _session_path(self, session_id: str) -> Path:
        return self.base_path / session_id

    def _session_lock(self, session_id: str) -> threading.Lock:
        with self._global_lock:
            if session_id not in self._locks:
                self._locks[session_id] = threading.Lock()
            return self._locks[session_id]

    def _load_turns(self, session_id: str) -> List[Dict[str, Any]]:
        turns_path = self._session_path(session_id) / "turns.json"
        if not turns_path.exists():
            raise SessionNotFoundError(f"Session {session_id} not found")
        data = self._read_json(turns_path)
        if isinstance(data, list):
            return data
        raise SessionManagerError("turns.json is malformed")

    def _write_turns(self, session_id: str, turns: Iterable[Dict[str, Any]]) -> None:
        turns_path = self._session_path(session_id) / "turns.json"
        self._write_json(turns_path, list(turns))

    @staticmethod
    def _read_json(path: Path) -> Any:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)


__all__ = [
    "SessionManager",
    "SessionManagerError",
    "SessionMetadata",
    "SessionNotFoundError",
    "TurnRecord",
]

