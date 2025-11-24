"""
Thin wrapper around the OpenAI Conversations API for new-story setup flows.
"""

from __future__ import annotations

import logging
from typing import List, Optional, TypedDict

import openai

from scripts.api_openai import OpenAIProvider

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
    """

    def __init__(self, model: str = "gpt-5.1"):
        """Initialize the Conversations client with the specified model."""
        self.model = model
        provider = OpenAIProvider(model=model)
        # Use the raw OpenAI client to access beta endpoints
        self.client = openai.OpenAI(api_key=provider.api_key)

    def create_thread(self) -> str:
        """Create a new conversation thread and return its ID."""
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
        try:
            self.client.beta.threads.delete(thread_id)
            logger.info("Deleted thread %s", thread_id)
            return True
        except openai.OpenAIError as exc:
            logger.warning("Failed to delete thread %s: %s", thread_id, exc)
            return False
