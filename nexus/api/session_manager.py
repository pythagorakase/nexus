"""
Session Manager for NEXUS Storyteller API

Handles file-based session persistence, turn history tracking,
and session lifecycle management.
"""

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================


class SessionMetadata(BaseModel):
    """Session metadata stored in metadata.json"""

    session_id: str
    session_name: Optional[str] = None
    created_at: datetime
    last_accessed: datetime
    turn_count: int = 0
    current_phase: str = "ready"
    initial_context: Optional[str] = None


class TurnRecord(BaseModel):
    """A single turn in the story"""

    turn_id: str
    turn_number: int
    timestamp: datetime
    user_input: str
    response: Dict[str, Any]  # StoryTurnResponse serialized
    options: Optional[Dict[str, Any]] = None


class SessionState(BaseModel):
    """Complete session state"""

    metadata: SessionMetadata
    turns: List[TurnRecord] = Field(default_factory=list)
    last_turn: Optional[TurnRecord] = None


# ============================================================================
# Session Manager
# ============================================================================


class SessionManager:
    """
    Manages file-based session persistence for storyteller sessions.

    Sessions are stored in the following structure:
    sessions/
        {session_id}/
            metadata.json      # Session metadata
            turns.json         # Turn history
            context/           # Per-turn context snapshots (optional)
                {turn_id}.json
    """

    def __init__(self, sessions_dir: Path = None):
        """
        Initialize the session manager.

        Args:
            sessions_dir: Directory for storing sessions (defaults to ./sessions)
        """
        if sessions_dir is None:
            # Default to sessions/ directory in project root
            project_root = Path(__file__).parent.parent.parent
            sessions_dir = project_root / "sessions"

        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"SessionManager initialized with sessions_dir: {self.sessions_dir}")

    def create_session(
        self, session_name: Optional[str] = None, initial_context: Optional[str] = None
    ) -> SessionMetadata:
        """
        Create a new session.

        Args:
            session_name: Optional human-readable session name
            initial_context: Optional initial context/setup for the story

        Returns:
            SessionMetadata for the new session
        """
        session_id = str(uuid.uuid4())
        session_dir = self.sessions_dir / session_id

        # Create session directory structure
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "context").mkdir(exist_ok=True)

        # Create metadata
        now = datetime.now()
        metadata = SessionMetadata(
            session_id=session_id,
            session_name=session_name,
            created_at=now,
            last_accessed=now,
            turn_count=0,
            current_phase="ready",
            initial_context=initial_context,
        )

        # Save metadata
        self._save_metadata(session_id, metadata)

        # Initialize empty turns file
        self._save_turns(session_id, [])

        logger.info(f"Created session {session_id} (name: {session_name})")
        return metadata

    def get_session(self, session_id: str) -> SessionState:
        """
        Get complete session state.

        Args:
            session_id: Session ID

        Returns:
            SessionState

        Raises:
            FileNotFoundError: If session doesn't exist
        """
        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            raise FileNotFoundError(f"Session {session_id} not found")

        # Load metadata
        metadata = self._load_metadata(session_id)

        # Update last_accessed
        metadata.last_accessed = datetime.now()
        self._save_metadata(session_id, metadata)

        # Load turns
        turns = self._load_turns(session_id)

        # Get last turn
        last_turn = turns[-1] if turns else None

        return SessionState(metadata=metadata, turns=turns, last_turn=last_turn)

    def add_turn(
        self,
        session_id: str,
        user_input: str,
        response: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> TurnRecord:
        """
        Add a new turn to the session.

        Args:
            session_id: Session ID
            user_input: User's input for this turn
            response: StoryTurnResponse (serialized to dict)
            options: Optional generation options used
            context_snapshot: Optional context snapshot to save

        Returns:
            TurnRecord for the new turn

        Raises:
            FileNotFoundError: If session doesn't exist
        """
        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            raise FileNotFoundError(f"Session {session_id} not found")

        # Load existing turns and metadata
        turns = self._load_turns(session_id)
        metadata = self._load_metadata(session_id)

        # Create turn record
        turn_id = str(uuid.uuid4())
        turn_number = len(turns) + 1

        turn = TurnRecord(
            turn_id=turn_id,
            turn_number=turn_number,
            timestamp=datetime.now(),
            user_input=user_input,
            response=response,
            options=options,
        )

        # Add turn to history
        turns.append(turn)

        # Save turns
        self._save_turns(session_id, turns)

        # Update metadata
        metadata.turn_count = len(turns)
        metadata.last_accessed = datetime.now()
        self._save_metadata(session_id, metadata)

        # Save context snapshot if provided
        if context_snapshot:
            self._save_context_snapshot(session_id, turn_id, context_snapshot)

        logger.info(f"Added turn {turn_number} to session {session_id}")
        return turn

    def get_turn_history(
        self, session_id: str, limit: int = 10, offset: int = 0
    ) -> List[TurnRecord]:
        """
        Get turn history for a session.

        Args:
            session_id: Session ID
            limit: Maximum number of turns to return
            offset: Number of turns to skip from the end

        Returns:
            List of TurnRecords (most recent first)

        Raises:
            FileNotFoundError: If session doesn't exist
        """
        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            raise FileNotFoundError(f"Session {session_id} not found")

        turns = self._load_turns(session_id)

        # Return most recent first, with offset and limit
        return list(reversed(turns))[offset : offset + limit]

    def update_last_turn(
        self, session_id: str, response: Dict[str, Any], options: Optional[Dict[str, Any]] = None
    ) -> TurnRecord:
        """
        Update the last turn in the session (for regeneration).

        Args:
            session_id: Session ID
            response: New StoryTurnResponse (serialized to dict)
            options: Optional generation options used

        Returns:
            Updated TurnRecord

        Raises:
            FileNotFoundError: If session doesn't exist
            ValueError: If session has no turns
        """
        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            raise FileNotFoundError(f"Session {session_id} not found")

        turns = self._load_turns(session_id)

        if not turns:
            raise ValueError(f"Session {session_id} has no turns to update")

        # Update last turn
        last_turn = turns[-1]
        last_turn.response = response
        last_turn.options = options
        last_turn.timestamp = datetime.now()

        # Save turns
        self._save_turns(session_id, turns)

        # Update metadata
        metadata = self._load_metadata(session_id)
        metadata.last_accessed = datetime.now()
        self._save_metadata(session_id, metadata)

        logger.info(f"Updated last turn in session {session_id}")
        return last_turn

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all associated data.

        Args:
            session_id: Session ID

        Returns:
            True if session was deleted, False if it didn't exist
        """
        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            return False

        shutil.rmtree(session_dir)
        logger.info(f"Deleted session {session_id}")
        return True

    def list_sessions(self) -> List[SessionMetadata]:
        """
        List all sessions.

        Returns:
            List of SessionMetadata for all sessions (most recent first)
        """
        sessions = []

        for session_dir in self.sessions_dir.iterdir():
            if session_dir.is_dir():
                try:
                    metadata = self._load_metadata(session_dir.name)
                    sessions.append(metadata)
                except Exception as e:
                    logger.warning(f"Failed to load session {session_dir.name}: {e}")
                    continue

        # Sort by last_accessed (most recent first)
        sessions.sort(key=lambda s: s.last_accessed, reverse=True)

        return sessions

    def get_context_snapshot(self, session_id: str, turn_id: str) -> Optional[Dict[str, Any]]:
        """
        Get context snapshot for a specific turn.

        Args:
            session_id: Session ID
            turn_id: Turn ID

        Returns:
            Context snapshot dict, or None if not found
        """
        session_dir = self._get_session_dir(session_id)
        context_file = session_dir / "context" / f"{turn_id}.json"

        if not context_file.exists():
            return None

        try:
            with open(context_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load context snapshot {turn_id}: {e}")
            return None

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_session_dir(self, session_id: str) -> Path:
        """Get path to session directory"""
        return self.sessions_dir / session_id

    def _load_metadata(self, session_id: str) -> SessionMetadata:
        """Load session metadata from disk"""
        metadata_file = self._get_session_dir(session_id) / "metadata.json"

        with open(metadata_file, "r") as f:
            data = json.load(f)
            return SessionMetadata(**data)

    def _save_metadata(self, session_id: str, metadata: SessionMetadata) -> None:
        """Save session metadata to disk"""
        metadata_file = self._get_session_dir(session_id) / "metadata.json"

        with open(metadata_file, "w") as f:
            json.dump(metadata.model_dump(mode="json"), f, indent=2, default=str)

    def _load_turns(self, session_id: str) -> List[TurnRecord]:
        """Load turn history from disk"""
        turns_file = self._get_session_dir(session_id) / "turns.json"

        if not turns_file.exists():
            return []

        with open(turns_file, "r") as f:
            data = json.load(f)
            return [TurnRecord(**turn) for turn in data]

    def _save_turns(self, session_id: str, turns: List[TurnRecord]) -> None:
        """Save turn history to disk"""
        turns_file = self._get_session_dir(session_id) / "turns.json"

        with open(turns_file, "w") as f:
            turns_data = [turn.model_dump(mode="json") for turn in turns]
            json.dump(turns_data, f, indent=2, default=str)

    def _save_context_snapshot(
        self, session_id: str, turn_id: str, context: Dict[str, Any]
    ) -> None:
        """Save context snapshot for a turn"""
        context_dir = self._get_session_dir(session_id) / "context"
        context_dir.mkdir(exist_ok=True)

        context_file = context_dir / f"{turn_id}.json"

        with open(context_file, "w") as f:
            json.dump(context, f, indent=2, default=str)
