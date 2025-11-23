"""
Thin wrapper around the OpenAI Conversations API for new-story setup flows.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import openai

from scripts.api_openai import OpenAIProvider

logger = logging.getLogger("nexus.api.conversations")


class ConversationsClient:
    """Minimal Conversations client (thread create/send/list/delete)."""

    def __init__(self, model: str = "gpt-5.1"):
        self.model = model
        provider = OpenAIProvider(model=model)
        # Use the raw OpenAI client to access beta endpoints
        self.client = openai.OpenAI(api_key=provider.api_key)

    def create_thread(self) -> str:
        thread = self.client.beta.threads.create()
        thread_id = thread.id
        logger.info("Created conversations thread %s", thread_id)
        return thread_id

    def add_message(self, thread_id: str, role: str, content: str) -> str:
        msg = self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role=role,
            content=content,
        )
        logger.debug("Added %s message to thread %s", role, thread_id)
        return msg.id

    def list_messages(self, thread_id: str, limit: int = 20) -> List[str]:
        messages = self.client.beta.threads.messages.list(thread_id=thread_id, limit=limit)
        return [m.id for m in messages.data]

    def delete_thread(self, thread_id: str) -> bool:
        try:
            self.client.beta.threads.delete(thread_id)
            logger.info("Deleted thread %s", thread_id)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to delete thread %s: %s", thread_id, exc)
            return False
