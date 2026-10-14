"""The slot database holds the wizard transcript for every provider."""

import uuid
from typing import List, Literal

from nexus.api.new_story_cache import add_wizard_message, list_wizard_messages
from nexus.api.wizard_transcript import MessageOrigin, WizardMessage

Message = WizardMessage


def new_conversation_id() -> str:
    """Mint the UUID stored with a new wizard cache and its transcript."""
    return str(uuid.uuid4())


class ConversationsClient:
    """Read and append messages in one slot database's wizard transcript."""

    def __init__(self, dbname: str) -> None:
        """Bind all transcript operations to the selected slot database."""
        self.dbname = dbname

    def add_message(
        self,
        thread_id: str,
        role: Literal["user", "assistant"],
        content: str,
        *,
        origin: MessageOrigin | None = None,
    ) -> int:
        """Append a message while holding the current wizard cache row lock."""
        return add_wizard_message(
            self.dbname,
            expected_thread_id=thread_id,
            role=role,
            content=content,
            origin=origin,
        )

    def list_messages(self, thread_id: str, limit: int = 20) -> List[Message]:
        """Read unsuperseded messages newest first; zero requests all rows."""
        return list_wizard_messages(self.dbname, thread_id, limit=limit)
