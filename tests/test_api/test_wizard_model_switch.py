"""Wizard model switches must keep the conversation in a store the model reads.

Only the hosted OpenAI SDK transport and the slot database are replaced here:
the chat handlers, ConversationsClient, the file and memory stores, and the
real OpenAI SDK request and response handling all run unchanged.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import openai
import pytest

from nexus.api import (
    conversations,
    new_story_flow,
    slot_state,
    wizard_agent,
    wizard_chat,
)
from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_cache import (
    WizardCache,
    init_cache,
    read_cache,
    repoint_wizard_conversation,
)
from nexus.api.new_story_schemas import WizardResponse
from nexus.api.save_slots import get_slot_model, set_slot_model
from nexus.api.slot_state import SlotState, WizardState
from nexus.api.wizard_confirmation import WizardStateConflict
from nexus.database import AmbiguousCommit
from tests.model_registry_helpers import registry_model

OPENING = [("assistant", "Welcome"), ("assistant", "Pick a genre")]
PLAYER = "A harbor city"
REPLY = "The harbor wakes."
DEBUG_REPLY = "Debug: the harbor is set."


class HostedConversations:
    """The hosted Conversations HTTP API, answered in process for the real SDK.

    As on the real service, deleting a conversation leaves its items stored;
    only an item deletion removes an item.
    """

    def __init__(self) -> None:
        self.threads: dict[str, list[str]] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self.reads = 0
        self.writes = 0
        self.fail_reads_after: Optional[int] = None
        self.fail_writes_after: Optional[int] = None

    def _error(self, status: int, message: str) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "error": {
                    "message": message,
                    "type": "invalid_request_error",
                    "param": None,
                    "code": None,
                }
            },
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v1/conversations")
        if path == "" and request.method == "POST":
            conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
            self.threads[conversation_id] = []
            return httpx.Response(
                200,
                json={"id": conversation_id, "object": "conversation", "created_at": 1},
            )
        conversation_id, _, rest = path.strip("/").partition("/")
        item_ids = self.threads.get(conversation_id)
        if item_ids is None:
            return self._error(404, f"Conversation {conversation_id} not found")
        if rest == "" and request.method == "DELETE":
            del self.threads[conversation_id]
            return httpx.Response(
                200,
                json={
                    "id": conversation_id,
                    "object": "conversation.deleted",
                    "deleted": True,
                },
            )
        if rest.startswith("items/") and request.method == "DELETE":
            item_id = rest.removeprefix("items/")
            if item_id not in item_ids:
                return self._error(404, f"Item {item_id} not found")
            item_ids.remove(item_id)
            del self.items[item_id]
            return httpx.Response(
                200,
                json={"id": conversation_id, "object": "conversation", "created_at": 1},
            )
        if rest == "items" and request.method == "POST":
            self.writes += 1
            if (
                self.fail_writes_after is not None
                and self.writes > self.fail_writes_after
            ):
                return self._error(400, "Item rejected")
            (item,) = json.loads(request.content)["items"]
            item_id = f"msg_{uuid.uuid4().hex[:12]}"
            kind = "output_text" if item["role"] == "assistant" else "input_text"
            self.items[item_id] = {
                "id": item_id,
                "type": "message",
                "role": item["role"],
                "content": [{"type": kind, "text": item["content"]}],
            }
            item_ids.append(item_id)
            return httpx.Response(200, json={"data": [{"id": item_id}]})
        if rest == "items" and request.method == "GET":
            self.reads += 1
            if self.fail_reads_after is not None and self.reads > self.fail_reads_after:
                return self._error(401, "Incorrect API key provided")
            assert request.url.params["order"] == "desc"
            newest = [self.items[item_id] for item_id in reversed(item_ids)]
            after = request.url.params.get("after")
            if after:
                newest = newest[[item["id"] for item in newest].index(after) + 1 :]
            limit = int(request.url.params["limit"])
            page = newest[:limit]
            return httpx.Response(
                200,
                json={
                    "data": page,
                    "object": "list",
                    "has_more": len(newest) > limit,
                    "first_id": page[0]["id"] if page else "",
                    "last_id": page[-1]["id"] if page else "",
                },
            )
        pytest.fail(f"Unexpected Conversations request: {request.method} {path}")


@pytest.fixture
def hosted(
    monkeypatch: pytest.MonkeyPatch, offline_registry: Path
) -> HostedConversations:
    """Serve hosted Conversations in process; every other boundary stays real."""
    api = HostedConversations()

    class HostedProvider:
        """Supply the SDK client with an in-process transport and no credential."""

        def __init__(self, model: str) -> None:
            self.client = openai.OpenAI(
                api_key="test-key",
                http_client=httpx.Client(transport=httpx.MockTransport(api)),
            )

    monkeypatch.setattr(conversations, "OpenAIProvider", HostedProvider)
    return api


@dataclass
class SlotRecord:
    """The slot-database values a wizard model switch reads and writes."""

    model: str
    thread_id: str
    choice_threads: list[Optional[str]] = field(default_factory=list)
    before_repoint: Optional[Callable[[], None]] = None


def mount_wizard(
    monkeypatch: pytest.MonkeyPatch, record: SlotRecord, seen: list[str]
) -> TestClient:
    """Mount both production chat routes over an in-memory slot database."""

    def get_slot_state(slot: int) -> SlotState:
        return SlotState(
            slot=slot,
            is_empty=False,
            is_wizard_mode=True,
            narrative_state=None,
            model=record.model,
            wizard_state=WizardState(
                phase="setting",
                thread_id=record.thread_id,
                choices=[],
                has_concept=False,
                has_traits=False,
                has_wildcard=False,
            ),
        )

    def repoint(
        dbname: str,
        *,
        expected_thread_id: str,
        thread_id: str,
        expected_model: str,
        model: str,
    ) -> None:
        """Apply the same fenced, all-or-nothing write as the SQL function."""
        if record.before_repoint is not None:
            record.before_repoint()
        if (record.thread_id, record.model) != (expected_thread_id, expected_model):
            raise WizardStateConflict("The wizard changed before the switch saved.")
        record.thread_id, record.model = thread_id, model

    def write_choices(
        choices: list[str], dbname: str, *, expected_thread_id: Optional[str] = None
    ) -> None:
        record.choice_threads.append(expected_thread_id)

    def history_text(kwargs: dict[str, Any]) -> None:
        seen.extend(
            part.content
            for message in kwargs["message_history"]
            for part in message.parts
        )

    output = WizardResponse(message=REPLY, choices=["North pier", "South pier"])

    class Turn:
        async def stream_output(self) -> Any:
            yield output

        async def get_output(self) -> WizardResponse:
            return output

    class Agent:
        async def run(self, *args: Any, **kwargs: Any) -> Any:
            history_text(kwargs)
            return SimpleNamespace(output=output)

        async def run_stream(self, *args: Any, **kwargs: Any) -> Any:
            history_text(kwargs)
            yield Turn()

    class DebugAgent:
        async def run(self, *args: Any, **kwargs: Any) -> Any:
            history_text(kwargs)
            return SimpleNamespace(output=DEBUG_REPLY)

    monkeypatch.setattr(slot_state, "get_slot_state", get_slot_state)
    monkeypatch.setattr(wizard_chat, "require_writable_slot", lambda slot: None)
    for module in (wizard_chat, wizard_agent):
        monkeypatch.setattr(
            module, "read_cache", lambda dbname: WizardCache(thread_id=record.thread_id)
        )
    monkeypatch.setattr(new_story_flow, "repoint_wizard_conversation", repoint)
    monkeypatch.setattr(wizard_chat, "write_wizard_choices", write_choices)
    monkeypatch.setattr(wizard_chat, "get_wizard_agent", lambda context: Agent())
    monkeypatch.setattr(wizard_chat, "wizard_debug_agent", DebugAgent())
    monkeypatch.setattr(wizard_chat, "get_wizard_streaming_enabled", lambda: True)
    monkeypatch.setattr(
        wizard_chat,
        "build_pydantic_ai_model_with_provider",
        lambda model: (None, "test"),
    )
    monkeypatch.setattr(wizard_chat, "record_pydantic_ai_result", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(wizard_chat.router)
    return TestClient(app, raise_server_exceptions=False)


def opened_thread(model: str) -> str:
    """Create a thread in the model's store holding the pre-player opening."""
    client = ConversationsClient(model)
    thread_id = client.create_thread()
    for role, content in OPENING:
        client.add_message(thread_id, role, content)
    return thread_id


def transcript(model: str, thread_id: str) -> list[tuple[str, str]]:
    """Read a thread oldest first from the store the model selects."""
    messages = ConversationsClient(model).list_messages(thread_id, limit=0)
    return [(message["role"], message["content"]) for message in reversed(messages)]


def thread_files(thread_dir: Path) -> list[str]:
    """List file-store threads; the directory appears with the first file client."""
    return (
        sorted(path.name for path in thread_dir.iterdir())
        if thread_dir.exists()
        else []
    )


def chat(
    client: TestClient, streaming: bool, model: str, *, dev: bool = False
) -> httpx.Response:
    """Send the first player message with an explicit model override."""
    endpoint = "/api/story/new/chat/stream" if streaming else "/api/story/new/chat"
    return client.post(
        endpoint, json={"slot": 4, "message": PLAYER, "model": model, "dev": dev}
    )


def returned_thread_id(response: httpx.Response, streaming: bool) -> Any:
    """Read the thread ID a successful turn tells the client to continue in."""
    if not streaming:
        return response.json()["thread_id"]
    records = [json.loads(line) for line in response.text.splitlines()]
    assert records[-1]["type"] in {"final", "message"}, records
    return records[-1]["thread_id"]


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "source,target",
    [
        ("local", "openai"),
        ("openai", "openrouter"),
        ("test", "local"),
        ("anthropic", "test"),
    ],
)
def test_cross_store_switch_moves_the_opening_to_the_new_store(
    monkeypatch: pytest.MonkeyPatch,
    hosted: HostedConversations,
    source: str,
    target: str,
    streaming: bool,
) -> None:
    """The new model reads the copied opening under a new, persisted thread ID."""
    source_model, target_model = registry_model(source), registry_model(target)
    old_thread = opened_thread(source_model)
    record = SlotRecord(model=source_model, thread_id=old_thread)
    seen: list[str] = []

    response = chat(mount_wizard(monkeypatch, record, seen), streaming, target_model)

    assert response.status_code == 200, response.text
    assert record.model == target_model
    assert record.thread_id != old_thread
    assert returned_thread_id(response, streaming) == record.thread_id
    assert record.choice_threads == [record.thread_id]
    assert transcript(target_model, record.thread_id) == [
        *OPENING,
        ("user", PLAYER),
        ("assistant", REPLY),
    ]
    assert seen[: len(OPENING)] == [content for _, content in OPENING]
    # The source copy is left intact; only the slot's pointer moved.
    assert transcript(source_model, old_thread) == OPENING


@pytest.mark.parametrize("streaming", [False, True])
def test_dev_turn_returns_the_moved_thread(
    monkeypatch: pytest.MonkeyPatch, hosted: HostedConversations, streaming: bool
) -> None:
    """A debug turn after a cross-store switch also names the new thread."""
    source_model, target_model = registry_model("local"), registry_model("openai")
    old_thread = opened_thread(source_model)
    record = SlotRecord(model=source_model, thread_id=old_thread)

    response = chat(
        mount_wizard(monkeypatch, record, []), streaming, target_model, dev=True
    )

    assert response.status_code == 200, response.text
    assert record.thread_id != old_thread
    assert returned_thread_id(response, streaming) == record.thread_id
    assert transcript(target_model, record.thread_id) == [
        *OPENING,
        ("user", PLAYER),
        ("assistant", DEBUG_REPLY),
    ]


@pytest.mark.parametrize("streaming", [False, True])
def test_same_store_switch_keeps_the_thread(
    monkeypatch: pytest.MonkeyPatch,
    hosted: HostedConversations,
    offline_registry: Path,
    streaming: bool,
) -> None:
    """Providers sharing the file store keep one thread and only change model."""
    source_model, target_model = registry_model("local"), registry_model("openrouter")
    thread_id = opened_thread(source_model)
    record = SlotRecord(model=source_model, thread_id=thread_id)

    response = chat(mount_wizard(monkeypatch, record, []), streaming, target_model)

    assert response.status_code == 200, response.text
    assert (record.model, record.thread_id) == (target_model, thread_id)
    assert returned_thread_id(response, streaming) == thread_id
    assert transcript(target_model, thread_id) == [
        *OPENING,
        ("user", PLAYER),
        ("assistant", REPLY),
    ]
    assert thread_files(offline_registry) == [f"{thread_id}.json"]


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "failure", ["source_unreadable", "target_write_rejected", "concurrent_change"]
)
def test_failed_cross_store_switch_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
    hosted: HostedConversations,
    offline_registry: Path,
    failure: str,
    streaming: bool,
) -> None:
    """A failed move keeps the slot model, thread ID, and both stores as they were."""
    hosted_model, file_model = registry_model("openai"), registry_model("local")
    source_model, target_model = (
        (hosted_model, file_model)
        if failure == "source_unreadable"
        else (file_model, hosted_model)
    )
    old_thread = opened_thread(source_model)
    record = SlotRecord(model=source_model, thread_id=old_thread)
    files_before = thread_files(offline_registry)
    hosted_before = set(hosted.threads)
    items_before = set(hosted.items)
    if failure == "source_unreadable":
        # The lock check reads first; the credential fails on the move's read.
        hosted.fail_reads_after = hosted.reads + 1
    elif failure == "target_write_rejected":
        # One message is copied before the second is rejected.
        hosted.fail_writes_after = hosted.writes + 1
    else:

        def concurrent_setup() -> None:
            record.thread_id = "concurrent-thread"

        record.before_repoint = concurrent_setup

    response = chat(mount_wizard(monkeypatch, record, []), streaming, target_model)

    expected_status = 409 if failure == "concurrent_change" else 500
    assert response.status_code == expected_status, response.text
    if failure == "source_unreadable":
        detail = response.json()["detail"]
        assert "from openai storage" in detail and "to file storage" in detail
    expected_thread = (
        "concurrent-thread" if failure == "concurrent_change" else old_thread
    )
    assert (record.model, record.thread_id) == (source_model, expected_thread)
    assert record.choice_threads == []
    assert thread_files(offline_registry) == files_before
    assert set(hosted.threads) == hosted_before
    # Deleting a hosted conversation keeps its items; each copy is deleted too.
    assert set(hosted.items) == items_before
    hosted.fail_reads_after = None
    assert transcript(source_model, old_thread) == OPENING


@pytest.mark.parametrize("streaming", [False, True])
def test_ambiguous_save_keeps_the_copied_thread(
    monkeypatch: pytest.MonkeyPatch,
    hosted: HostedConversations,
    offline_registry: Path,
    streaming: bool,
) -> None:
    """A save with an unknown outcome fails the request but keeps the new thread."""
    source_model, target_model = registry_model("local"), registry_model("openai")
    old_thread = opened_thread(source_model)
    record = SlotRecord(model=source_model, thread_id=old_thread)
    hosted_before = set(hosted.threads)

    def connection_lost() -> None:
        raise AmbiguousCommit("connection lost while committing the model switch")

    record.before_repoint = connection_lost

    response = chat(mount_wizard(monkeypatch, record, []), streaming, target_model)

    assert response.status_code == 500, response.text
    assert (record.model, record.thread_id) == (source_model, old_thread)
    assert record.choice_threads == []
    new_threads = set(hosted.threads) - hosted_before
    assert len(new_threads) == 1
    assert transcript(target_model, new_threads.pop()) == OPENING
    assert transcript(source_model, old_thread) == OPENING


def test_switch_replays_player_provenance_in_order(
    monkeypatch: pytest.MonkeyPatch, hosted: HostedConversations
) -> None:
    """Copied user turns keep their origin, including a literal envelope."""
    source_model, target_model = registry_model("local"), registry_model("openai")
    source = ConversationsClient(source_model)
    thread_id = source.create_thread()
    source.add_message(thread_id, "assistant", "Welcome")
    source.add_message(thread_id, "user", "Continue", origin="wizard_control")
    source.add_message(thread_id, "user", "A harbor", origin="user")
    stored = json.loads(
        (conversations._FILE_STORE_DIR / f"{thread_id}.json").read_text()
    )
    source.add_message(thread_id, "user", stored[-1]["content"], origin="user")
    expected = source.list_messages(thread_id, limit=0)
    record = SlotRecord(model=source_model, thread_id=thread_id)
    mount_wizard(monkeypatch, record, [])

    new_thread = new_story_flow.switch_wizard_model(
        4, thread_id=thread_id, slot_model=source_model, model=target_model
    )

    assert (record.thread_id, record.model) == (new_thread, target_model)
    assert ConversationsClient(target_model).list_messages(new_thread, limit=0) == (
        expected
    )


@pytest.mark.requires_postgres
def test_repoint_commits_model_and_thread_together(offline_gate_db: str) -> None:
    """The SQL switch writes both slot rows or neither, fenced on what was read."""
    init_cache(offline_gate_db, "thread-before", 4)
    set_slot_model(4, "TEST", offline_gate_db)
    target = registry_model("local")

    def persisted() -> tuple[Optional[str], Optional[str]]:
        cache = read_cache(offline_gate_db)
        assert cache is not None
        return cache.thread_id, get_slot_model(4, dbname=offline_gate_db)

    # The thread row updates first; the stale model fence must roll it back.
    with pytest.raises(WizardStateConflict, match="slot model changed"):
        repoint_wizard_conversation(
            offline_gate_db,
            expected_thread_id="thread-before",
            thread_id="thread-after",
            expected_model=target,
            model="TEST",
        )
    assert persisted() == ("thread-before", "TEST")
    with pytest.raises(WizardStateConflict, match="conversation changed"):
        repoint_wizard_conversation(
            offline_gate_db,
            expected_thread_id="thread-elsewhere",
            thread_id="thread-after",
            expected_model="TEST",
            model=target,
        )
    assert persisted() == ("thread-before", "TEST")
    repoint_wizard_conversation(
        offline_gate_db,
        expected_thread_id="thread-before",
        thread_id="thread-after",
        expected_model="TEST",
        model=target,
    )
    assert persisted() == ("thread-after", target)
