"""
Conversation storage wrapper for new-story setup flows.

The registry provider of the wizard model selects the store: the hosted OpenAI
Conversations API for ``openai`` models, in-memory storage for the ``test``
provider, and local file storage for every other registered provider
(Anthropic and OpenAI-compatible servers such as the local llama-server or
OpenRouter, none of which exposes a Conversations endpoint).
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, NotRequired, Optional, TypedDict

import openai

from scripts.api_openai import OpenAIProvider
from nexus.api.wizard_transcript import (
    MessageOrigin,
    decode_wizard_message,
    encode_wizard_message,
)
from nexus.config.loader import load_settings
from nexus.config.settings_models import Settings
from nexus.runtime.home import resolve_runtime_home

logger = logging.getLogger("nexus.api.conversations")

ConversationStoreMode = Literal["openai", "memory", "file"]

# Only the hosted OpenAI API serves the Conversations endpoint.
HOSTED_CONVERSATIONS_PROVIDER = "openai"
# The registry's mock provider keeps wizard history in process memory.
MEMORY_CONVERSATIONS_PROVIDER = "test"

WIZARD_THREADS_DIRNAME = "wizard_threads"


def wizard_threads_dir(settings: Settings) -> Path:
    """Locate file-backed wizard threads under state_dir (Decision 820-Q6)."""
    return resolve_runtime_home(settings).state_dir / WIZARD_THREADS_DIRNAME


class ConversationThreadNotFoundError(LookupError):
    """A wizard thread ID has no record in a local conversation store.

    ``create_thread`` always registers the thread in the file or memory store,
    so a missing record means the ID belongs to another store (for example, a
    hosted ``conv_*`` ID after a switch to a file-backed provider), the thread
    was deleted, or an in-memory thread was lost when the process restarted.
    """


class Message(TypedDict):
    """Type definition for conversation messages."""

    role: str
    content: str
    origin: NotRequired[MessageOrigin]


def _normalized_message(role: str, content: str) -> Message:
    """Return model-facing text and retain optional wizard provenance."""
    message: Message = {"role": role, "content": content}
    if role == "user":
        text, origin = decode_wizard_message(content)
        message["content"] = text
        if origin is not None:
            message["origin"] = origin
    return message


def conversation_store_mode(
    provider: str, settings: Settings | None = None
) -> ConversationStoreMode:
    """Choose wizard conversation storage from a registry provider name.

    Args:
        provider: A provider section name from ``[global.model.api_models]``.
        settings: Settings whose registry defines the providers; the active
            runtime configuration when omitted.

    Returns:
        ``"openai"`` for the hosted Conversations API, ``"memory"`` for the
        TEST provider, and ``"file"`` for every other registered provider.

    Raises:
        ValueError: If the provider is not registered.
    """
    registry = (settings or load_settings()).global_.model.api_models
    if provider not in registry:
        raise ValueError(
            f"Provider {provider!r} is not registered in "
            f"[global.model.api_models] ({sorted(registry)}); cannot choose "
            "wizard conversation storage"
        )
    if provider == HOSTED_CONVERSATIONS_PROVIDER:
        return "openai"
    if provider == MEMORY_CONVERSATIONS_PROVIDER:
        return "memory"
    return "file"


def _hosted_conversations_client(model: str, settings: Settings) -> Any:
    """Return the hosted OpenAI SDK client for an ``openai`` registry model.

    Raises:
        ValueError: If the model belongs to any other provider. Its requests
            would otherwise reach the hosted API with the OpenAI credential.
    """
    provider = settings.provider_for_model(model)
    if provider != HOSTED_CONVERSATIONS_PROVIDER:
        raise ValueError(
            f"Hosted OpenAI Conversations storage requested for model {model!r} "
            f"of provider {provider!r}; only provider "
            f"{HOSTED_CONVERSATIONS_PROVIDER!r} serves that endpoint"
        )
    return OpenAIProvider(model=model).client


class ConversationsClient:
    """
    Minimal Conversations client (thread create/send/list/delete).

    The wizard model's registry provider selects the store (see
    ``conversation_store_mode``). OpenAI models use the hosted Conversations
    API; the application keeps the name ``thread_id`` for its stored
    conversation ID. The TEST provider stores history in process memory, and
    every other provider stores it in local files without constructing a
    hosted client.
    """

    def __init__(self, model: str) -> None:
        """Initialize the Conversations client with the specified model.

        Args:
            model: Model name (a concrete ID from the api_models registry).
                Models of the ``test`` registry provider select in-memory
                storage and make no API calls.

        Raises:
            ValueError: If the model or its provider is absent from the registry.
        """
        from nexus.config.story_model import resolve_seat

        settings = load_settings()
        seat = resolve_seat("wizard", settings=settings, override=model)
        self.model = seat.model
        self.provider = seat.provider
        self._store_mode: ConversationStoreMode = conversation_store_mode(
            seat.provider, settings
        )
        self._memory_store: Optional[_MemoryConversationStore] = None
        self._file_store: Optional[_FileConversationStore] = None
        self.client: Any = None

        if self._store_mode == "memory":
            self._memory_store = _MEMORY_STORE
            logger.info("[TEST MODE] ConversationsClient using in-memory storage")
        elif self._store_mode == "file":
            self._file_store = _FileConversationStore(wizard_threads_dir(settings))
            logger.info(
                "ConversationsClient using file storage for %s (provider %s)",
                self.model,
                self.provider,
            )
        else:
            # Hosted Conversations replaced Assistants Threads (retired on
            # August 26, 2026).
            self.client = _hosted_conversations_client(self.model, settings)

    @property
    def store_mode(self) -> ConversationStoreMode:
        """The conversation store this client reads and writes."""
        return self._store_mode

    def _require_memory_store(self) -> _MemoryConversationStore:
        """Return the shared memory store, failing loudly if it was never set."""
        if self._memory_store is None:
            raise RuntimeError(
                f"ConversationsClient for {self.model!r} is in memory storage mode "
                "without a memory store"
            )
        return self._memory_store

    def _require_file_store(self) -> _FileConversationStore:
        """Return the local file store, failing loudly if it was never built."""
        if self._file_store is None:
            raise RuntimeError(
                f"ConversationsClient for {self.model!r} is in file storage mode "
                "without a file store"
            )
        return self._file_store

    def _require_hosted_client(self) -> Any:
        """Return the hosted Conversations client, failing on any other store."""
        if self._store_mode != "openai" or self.client is None:
            raise RuntimeError(
                f"ConversationsClient for {self.model!r} has store mode "
                f"{self._store_mode!r} and no hosted Conversations client"
            )
        return self.client

    def create_thread(self) -> str:
        """Create a new conversation thread and return its ID."""
        if self._store_mode == "memory":
            thread_id = self._require_memory_store().create_thread()
            logger.info("[TEST MODE] Created in-memory thread %s", thread_id)
            return thread_id
        if self._store_mode == "file":
            thread_id = self._require_file_store().create_thread()
            logger.info("Created local thread %s", thread_id)
            return thread_id

        thread = self._require_hosted_client().conversations.create()
        thread_id = thread.id
        logger.info("Created conversations thread %s", thread_id)
        return thread_id

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        *,
        origin: MessageOrigin | None = None,
    ) -> str:
        """
        Add a message to an existing thread.

        Args:
            thread_id: The ID of the thread to add the message to
            role: The role of the message sender (user/assistant)
            content: The message content
            origin: Explicit provenance for a wizard input. Its envelope is
                storage-only; list_messages returns the original content.

        Returns:
            The ID of the created message

        Raises:
            ConversationThreadNotFoundError: If a file or memory thread is absent.
        """
        if origin is not None:
            if role != "user":
                raise ValueError("Wizard input provenance requires role=user")
            content = encode_wizard_message(content, origin)
        if self._store_mode == "memory":
            msg_id = self._require_memory_store().add_message(thread_id, role, content)
            logger.debug("[TEST MODE] Added %s message to thread %s", role, thread_id)
            return msg_id
        if self._store_mode == "file":
            msg_id = self._require_file_store().add_message(thread_id, role, content)
            logger.debug("Added %s message to local thread %s", role, thread_id)
            return msg_id

        items = self._require_hosted_client().conversations.items.create(
            conversation_id=thread_id,
            items=[{"type": "message", "role": role, "content": content}],
        )
        logger.debug("Added %s message to thread %s", role, thread_id)
        return items.data[0].id

    def list_messages(self, thread_id: str, limit: int = 20) -> List[Message]:
        """
        List messages in a thread.

        Args:
            thread_id: The ID of the thread
            limit: Maximum number of messages to return (default: 20)

        Returns:
            List of Message TypedDicts with 'role' and 'content' fields

        Raises:
            ConversationThreadNotFoundError: If a file or memory thread is absent.
        """
        if self._store_mode == "memory":
            return self._require_memory_store().list_messages(thread_id, limit=limit)
        if self._store_mode == "file":
            return self._require_file_store().list_messages(thread_id, limit=limit)

        items = self._require_hosted_client().conversations.items.list(
            conversation_id=thread_id,
            order="desc",
            limit=min(limit, 100) if limit else 100,
        )

        history = []
        # SDK iteration follows pagination. Conversations can also contain
        # tool items; only messages count toward the wizard history limit.
        for item in items:
            if item.type != "message":
                continue
            content = "".join(
                part.text
                for part in item.content
                if part.type in {"input_text", "output_text"}
            )
            history.append(_normalized_message(item.role, content))
            if limit and len(history) >= limit:
                break

        return history

    def delete_message(self, thread_id: str, message_id: str) -> None:
        """
        Delete one message from a thread.

        Hosted conversations keep their items after the conversation itself is
        deleted, so a copied transcript must be removed item by item.

        Args:
            thread_id: The ID of the thread holding the message
            message_id: The ID returned by add_message

        Raises:
            ConversationThreadNotFoundError: If a file or memory thread is absent.
            LookupError: If a file or memory thread has no such message.
        """
        if self._store_mode == "memory":
            self._require_memory_store().delete_message(thread_id, message_id)
        elif self._store_mode == "file":
            self._require_file_store().delete_message(thread_id, message_id)
        else:
            self._require_hosted_client().conversations.items.delete(
                message_id, conversation_id=thread_id
            )
        logger.debug("Deleted message %s from thread %s", message_id, thread_id)

    def delete_thread(self, thread_id: str) -> bool:
        """
        Delete a conversation thread.

        Args:
            thread_id: The ID of the thread to delete

        Returns:
            True if successful, False otherwise

        Raises:
            ConversationThreadNotFoundError: If a file or memory thread is absent.
        """
        if self._store_mode == "memory":
            self._require_memory_store().delete_thread(thread_id)
            logger.info("[TEST MODE] Deleted in-memory thread %s", thread_id)
            return True
        if self._store_mode == "file":
            self._require_file_store().delete_thread(thread_id)
            logger.info("Deleted local thread %s", thread_id)
            return True

        client = self._require_hosted_client()
        try:
            client.conversations.delete(thread_id)
            logger.info("Deleted thread %s", thread_id)
            return True
        except openai.OpenAIError as exc:
            logger.warning("Failed to delete thread %s: %s", thread_id, exc)
            return False


def _without_message(
    messages: List[Dict[str, str]], thread_id: str, message_id: str
) -> List[Dict[str, str]]:
    """Return a local thread's messages minus one, raising if it is absent."""
    kept = [message for message in messages if message["id"] != message_id]
    if len(kept) == len(messages):
        raise LookupError(
            f"Wizard conversation thread {thread_id!r} has no message {message_id!r}"
        )
    return kept


class _MemoryConversationStore:
    """Process-wide in-memory conversation store for the TEST provider.

    Every client in the process shares one instance, as file-backed clients
    share one directory, so a thread created by one request is visible to the
    next. Threads do not survive a process restart.
    """

    def __init__(self) -> None:
        self.threads: Dict[str, List[Dict[str, str]]] = {}
        self._lock = threading.Lock()

    def _existing(self, thread_id: str) -> List[Dict[str, str]]:
        """Return a created thread's messages, raising when the store lacks it."""
        messages = self.threads.get(thread_id)
        if messages is None:
            raise ConversationThreadNotFoundError(
                f"Wizard conversation thread {thread_id!r} does not exist in the "
                "in-memory TEST store; it was created in another conversation "
                "store, deleted, or lost when the process restarted"
            )
        return messages

    def create_thread(self) -> str:
        thread_id = f"test_thread_{uuid.uuid4().hex[:16]}"
        with self._lock:
            self.threads[thread_id] = []
        return thread_id

    def add_message(self, thread_id: str, role: str, content: str) -> str:
        msg_id = f"test_msg_{uuid.uuid4().hex[:16]}"
        with self._lock:
            self._existing(thread_id).append(
                {"id": msg_id, "role": role, "content": content}
            )
        return msg_id

    def list_messages(self, thread_id: str, limit: int = 20) -> List[Message]:
        with self._lock:
            messages = list(self._existing(thread_id))
        limited = messages[-limit:] if limit else messages
        limited = list(reversed(limited))
        return [_normalized_message(m["role"], m["content"]) for m in limited]

    def delete_message(self, thread_id: str, message_id: str) -> None:
        with self._lock:
            messages = self._existing(thread_id)
            messages[:] = _without_message(messages, thread_id, message_id)

    def delete_thread(self, thread_id: str) -> bool:
        with self._lock:
            self._existing(thread_id)
            del self.threads[thread_id]
        return True


_MEMORY_STORE = _MemoryConversationStore()


class _FileConversationStore:
    """File-backed conversation store for providers without hosted storage."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _thread_path(self, thread_id: str) -> Path:
        return self._base_dir / f"{thread_id}.json"

    def _existing_thread_path(self, thread_id: str) -> Path:
        """Return a created thread's file, raising when the store lacks it."""
        path = self._thread_path(thread_id)
        if not path.exists():
            raise ConversationThreadNotFoundError(
                f"Wizard conversation thread {thread_id!r} does not exist in the "
                f"local file store {self._base_dir}; it was created in another "
                "conversation store or deleted"
            )
        return path

    def _load(self, thread_id: str) -> List[Dict[str, str]]:
        path = self._existing_thread_path(thread_id)
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
        return [_normalized_message(m["role"], m["content"]) for m in limited]

    def delete_message(self, thread_id: str, message_id: str) -> None:
        with self._lock:
            messages = self._load(thread_id)
            self._save(thread_id, _without_message(messages, thread_id, message_id))

    def delete_thread(self, thread_id: str) -> bool:
        with self._lock:
            self._existing_thread_path(thread_id).unlink()
        return True
