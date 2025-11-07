"""Session management for the NEXUS Storyteller REST API."""
from __future__ import annotations

import json
import shutil
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class SessionMetadata:
    """Metadata describing a single storytelling session."""

    session_id: str
    session_name: Optional[str]
    created_at: str
    last_accessed: str
    turn_count: int
    current_phase: str
    initial_context: Optional[str]
    last_turn_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Return metadata as a serializable dictionary."""
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "turn_count": self.turn_count,
            "current_phase": self.current_phase,
            "initial_context": self.initial_context,
            "last_turn_id": self.last_turn_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMetadata":
        """Create metadata from a dictionary."""
        return cls(
            session_id=data["session_id"],
            session_name=data.get("session_name"),
            created_at=data.get("created_at", ""),
            last_accessed=data.get("last_accessed", ""),
            turn_count=int(data.get("turn_count", 0)),
            current_phase=data.get("current_phase", "idle"),
            initial_context=data.get("initial_context"),
            last_turn_id=data.get("last_turn_id"),
        )


class SessionManager:
    """File-backed storage for story sessions and their turn history."""

    def __init__(self, base_path: Path, *, max_context_files: int = 50) -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.max_context_files = max_context_files
        self._locks: Dict[str, threading.RLock] = {}
        self._locks_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Session lifecycle helpers
    # ------------------------------------------------------------------
    def create_session(
        self,
        session_name: Optional[str] = None,
        initial_context: Optional[str] = None,
    ) -> SessionMetadata:
        """Create a new session directory and metadata."""
        session_id = str(uuid4())
        session_dir = self.base_path / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "context").mkdir(parents=True, exist_ok=True)

        now = self._now()
        metadata = SessionMetadata(
            session_id=session_id,
            session_name=session_name,
            created_at=now,
            last_accessed=now,
            turn_count=0,
            current_phase="idle",
            initial_context=initial_context,
            last_turn_id=None,
        )

        self._register_lock(session_id)
        self._write_metadata(metadata)
        self._write_json(session_dir / "turns.json", [])
        return metadata

    def session_exists(self, session_id: str) -> bool:
        """Return True if the session directory exists."""
        return (self.base_path / session_id).is_dir()

    def delete_session(self, session_id: str) -> None:
        """Delete a session and all associated files."""
        session_dir = self.base_path / session_id
        if not session_dir.exists():
            return

        with self._session_lock(session_id):
            shutil.rmtree(session_dir, ignore_errors=True)
            with self._locks_lock:
                self._locks.pop(session_id, None)

    # ------------------------------------------------------------------
    # Metadata operations
    # ------------------------------------------------------------------
    def get_metadata(self, session_id: str) -> SessionMetadata:
        """Load session metadata."""
        metadata_path = self.base_path / session_id / "metadata.json"
        data = self._read_json(metadata_path)
        if data is None:
            raise FileNotFoundError(f"Session {session_id} not found")
        return SessionMetadata.from_dict(data)

    def update_phase(self, session_id: str, phase: str) -> SessionMetadata:
        """Update current phase and last accessed timestamp."""
        with self._session_lock(session_id):
            metadata = self.get_metadata(session_id)
            metadata.current_phase = phase
            metadata.last_accessed = self._now()
            self._write_metadata(metadata)
            return metadata

    def touch_session(self, session_id: str) -> SessionMetadata:
        """Update last accessed timestamp without changing the phase."""
        with self._session_lock(session_id):
            metadata = self.get_metadata(session_id)
            metadata.last_accessed = self._now()
            self._write_metadata(metadata)
            return metadata

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return metadata for all sessions sorted by last access."""
        sessions: List[Dict[str, Any]] = []
        for metadata_path in self.base_path.glob("*/metadata.json"):
            data = self._read_json(metadata_path)
            if data:
                sessions.append(data)
        sessions.sort(key=lambda item: item.get("last_accessed", ""), reverse=True)
        return sessions

    # ------------------------------------------------------------------
    # Turn persistence
    # ------------------------------------------------------------------
    def record_turn(
        self,
        session_id: str,
        turn_record: Dict[str, Any],
        *,
        replace_last: bool = False,
    ) -> SessionMetadata:
        """Persist a turn record and update metadata."""
        session_dir = self.base_path / session_id
        turns_path = session_dir / "turns.json"

        with self._session_lock(session_id):
            history: List[Dict[str, Any]] = self._read_json(turns_path) or []
            if replace_last and history:
                history[-1] = turn_record
            else:
                history.append(turn_record)

            self._write_json(turns_path, history)

            metadata = self.get_metadata(session_id)
            metadata.turn_count = len(history)
            metadata.last_turn_id = turn_record.get("turn_id")
            metadata.current_phase = "idle"
            metadata.last_accessed = self._now()
            self._write_metadata(metadata)
            return metadata

    def load_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Load entire turn history for a session."""
        turns_path = self.base_path / session_id / "turns.json"
        history = self._read_json(turns_path)
        return history or []

    def get_history_slice(
        self,
        session_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return paginated slice of turn history."""
        history = self.load_history(session_id)
        if offset < 0:
            offset = 0
        if limit < 0:
            limit = 0
        return history[offset : offset + limit] if limit else history[offset:]

    # ------------------------------------------------------------------
    # Context persistence
    # ------------------------------------------------------------------
    def save_context(self, session_id: str, turn_id: str, context: Dict[str, Any]) -> Path:
        """Persist assembled context payload for a turn."""
        context_dir = self.base_path / session_id / "context"
        context_dir.mkdir(parents=True, exist_ok=True)
        context_path = context_dir / f"{turn_id}.json"
        self._write_json(context_path, context)
        self.prune_session_context(session_id)
        return context_path

    def get_latest_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent context payload for a session."""
        with self._session_lock(session_id):
            metadata = self.get_metadata(session_id)
            turn_id = metadata.last_turn_id
            if not turn_id:
                return None
            context_path = self.base_path / session_id / "context" / f"{turn_id}.json"
            return self._read_json(context_path)

    def prune_session_context(self, session_id: str) -> None:
        """Trim context directory to keep recent files only."""
        context_dir = self.base_path / session_id / "context"
        if not context_dir.exists():
            return

        files = sorted(
            context_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale_path in files[self.max_context_files :]:
            try:
                stale_path.unlink(missing_ok=True)
            except OSError:
                continue

    # ------------------------------------------------------------------
    # Session state helpers
    # ------------------------------------------------------------------
    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """Return metadata, latest turn and current context."""
        with self._session_lock(session_id):
            metadata = self.get_metadata(session_id)
            history = self.load_history(session_id)
            last_turn = history[-1] if history else None
            context = self.get_latest_context(session_id)
            return {
                "metadata": metadata.to_dict(),
                "last_turn": last_turn,
                "current_context": context,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _register_lock(self, session_id: str) -> None:
        with self._locks_lock:
            self._locks.setdefault(session_id, threading.RLock())

    @contextmanager
    def _session_lock(self, session_id: str):
        self._register_lock(session_id)
        lock = self._locks[session_id]
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def _write_metadata(self, metadata: SessionMetadata) -> None:
        metadata_path = self.base_path / metadata.session_id / "metadata.json"
        self._write_json(metadata_path, metadata.to_dict())

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat()

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, set):
            return sorted(value)
        raise TypeError(f"Type {type(value)!r} is not JSON serializable")

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, default=self._json_default)

    @staticmethod
    def _read_json(path: Path) -> Optional[Any]:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
