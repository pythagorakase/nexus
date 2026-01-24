"""
Conversation storage wrapper for new-story setup flows.

Uses OpenAI Threads for OpenAI models, file-backed storage for Anthropic models,
and in-memory storage for TEST mode.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

import openai

from scripts.api_openai import OpenAIProvider
from nexus.config.loader import get_provider_for_model

logger = logging.getLogger("nexus.api.conversations")


class Message(TypedDict):
    """Type definition for conversation messages."""
    role: str
    content: str


class ConversationsClient:
    """
    Minimal Conversations client (thread create/send/list/delete).

    Provides a lightweight wrapper around OpenAI's beta Conversations API
    for managing new-story setup flows.

    In TEST mode, uses in-memory storage instead of OpenAI Threads API
    to enable instant testing without API credentials.
    """

    def __init__(self, model: str = "gpt-5.1"):
        """Initialize the Conversations client with the specified model.

        Args:
            model: Model name. Use "TEST" for in-memory mode without API calls.
        """
        self.model = model
        self._store_mode = "openai"
        self._file_store: Optional[_FileConversationStore] = None

        provider = get_provider_for_model(model) or "openai"

        # TEST mode: use in-memory storage, skip OpenAI entirely
        if model == "TEST" or provider == "test":
            self._test_mode = True
            self._test_threads: Dict[str, List[Dict[str, str]]] = {}
            self.client = None  # No real client needed
            self._store_mode = "memory"
            logger.info("[TEST MODE] ConversationsClient using in-memory storage")
            return

        if provider == "anthropic":
            self._test_mode = False
            self._store_mode = "file"
            self._file_store = _FileConversationStore()
            self.client = None
            logger.info("ConversationsClient using file storage for %s", model)
            return

        # Production mode: use OpenAI Threads API
        self._test_mode = False
        provider_client = OpenAIProvider(model=model)
        # Use the raw OpenAI client to access beta endpoints
        self.client = openai.OpenAI(api_key=provider_client.api_key)

    def create_thread(self) -> str:
        """Create a new conversation thread and return its ID."""
        if self._store_mode == "memory":
            thread_id = f"test_thread_{uuid.uuid4().hex[:16]}"
            self._test_threads[thread_id] = []
            logger.info("[TEST MODE] Created in-memory thread %s", thread_id)
            return thread_id
        if self._store_mode == "file" and self._file_store:
            thread_id = self._file_store.create_thread()
            logger.info("Created local thread %s", thread_id)
            return thread_id

        thread = self.client.beta.threads.create()
        thread_id = thread.id
        logger.info("Created conversations thread %s", thread_id)
        return thread_id

    def add_message(self, thread_id: str, role: str, content: str) -> str:
        """
        Add a message to an existing thread.

        Args:
            thread_id: The ID of the thread to add the message to
            role: The role of the message sender (user/assistant)
            content: The message content

        Returns:
            The ID of the created message
        """
        if self._store_mode == "memory":
            msg_id = f"test_msg_{uuid.uuid4().hex[:16]}"
            # Initialize thread if it doesn't exist (handle edge cases)
            if thread_id not in self._test_threads:
                self._test_threads[thread_id] = []
            self._test_threads[thread_id].append({
                "id": msg_id,
                "role": role,
                "content": content
            })
            logger.debug("[TEST MODE] Added %s message to thread %s", role, thread_id)
            return msg_id
        if self._store_mode == "file" and self._file_store:
            msg_id = self._file_store.add_message(thread_id, role, content)
            logger.debug("Added %s message to local thread %s", role, thread_id)
            return msg_id

        msg = self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role=role,
            content=content,
        )
        logger.debug("Added %s message to thread %s", role, thread_id)
        return msg.id

    def list_messages(self, thread_id: str, limit: int = 20) -> List[Message]:
        """
        List messages in a thread.

        Args:
            thread_id: The ID of the thread
            limit: Maximum number of messages to return (default: 20)

        Returns:
            List of Message TypedDicts with 'role' and 'content' fields
        """
        if self._store_mode == "memory":
            messages = self._test_threads.get(thread_id, [])
            # Return most recent messages, limited (newest first)
            limited = messages[-limit:] if limit else messages
            limited = list(reversed(limited))
            return [{"role": m["role"], "content": m["content"]} for m in limited]
        if self._store_mode == "file" and self._file_store:
            return self._file_store.list_messages(thread_id, limit=limit)

        messages = self.client.beta.threads.messages.list(thread_id=thread_id, limit=limit)

        history = []
        for msg in messages.data:
            content = ""
            if msg.content and len(msg.content) > 0:
                # Assuming text content for now
                if hasattr(msg.content[0], 'text'):
                    content = msg.content[0].text.value

            history.append({
                "role": msg.role,
                "content": content
            })

        return history

    def delete_thread(self, thread_id: str) -> bool:
        """
        Delete a conversation thread.

        Args:
            thread_id: The ID of the thread to delete

        Returns:
            True if successful, False otherwise
        """
        if self._store_mode == "memory":
            if thread_id in self._test_threads:
                del self._test_threads[thread_id]
                logger.info("[TEST MODE] Deleted in-memory thread %s", thread_id)
                return True
            logger.warning("[TEST MODE] Thread %s not found", thread_id)
            return False
        if self._store_mode == "file" and self._file_store:
            deleted = self._file_store.delete_thread(thread_id)
            if deleted:
                logger.info("Deleted local thread %s", thread_id)
            else:
                logger.warning("Local thread %s not found", thread_id)
            return deleted

        try:
            self.client.beta.threads.delete(thread_id)
            logger.info("Deleted thread %s", thread_id)
            return True
        except openai.OpenAIError as exc:
            logger.warning("Failed to delete thread %s: %s", thread_id, exc)
            return False


class _FileConversationStore:
    """File-backed conversation store for non-OpenAI providers."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._base_dir = base_dir or (Path(__file__).parent.parent.parent / "temp" / "wizard_threads")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _thread_path(self, thread_id: str) -> Path:
        return self._base_dir / f"{thread_id}.json"

    def _load(self, thread_id: str) -> List[Dict[str, str]]:
        path = self._thread_path(thread_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save(self, thread_id: str, messages: List[Dict[str, str]]) -> None:
        path = self._thread_path(thread_id)
        tmp_path = path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(messages, handle)
        tmp_path.replace(path)

    def create_thread(self) -> str:
        thread_id = f"local_thread_{uuid.uuid4().hex[:16]}"
        with self._lock:
            self._save(thread_id, [])
        return thread_id

    def add_message(self, thread_id: str, role: str, content: str) -> str:
        msg_id = f"local_msg_{uuid.uuid4().hex[:16]}"
        with self._lock:
            messages = self._load(thread_id)
            messages.append({"id": msg_id, "role": role, "content": content})
            self._save(thread_id, messages)
        return msg_id

    def list_messages(self, thread_id: str, limit: int = 20) -> List[Message]:
        with self._lock:
            messages = self._load(thread_id)
        limited = messages[-limit:] if limit else messages
        limited = list(reversed(limited))
        return [{"role": m["role"], "content": m["content"]} for m in limited]

    def delete_thread(self, thread_id: str) -> bool:
        path = self._thread_path(thread_id)
        if not path.exists():
            return False
        path.unlink()
        return True
