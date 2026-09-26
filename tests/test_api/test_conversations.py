"""Verify the wizard's Conversations protocol with the real OpenAI SDK."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest

from nexus.api.conversations import ConversationsClient, _FileConversationStore
from nexus.config import load_settings


def test_openai_conversation_protocol() -> None:
    """Create, write, page newest-first history, and delete via supported routes."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/v1/conversations" and request.method == "POST":
            return httpx.Response(
                200, json={"id": "conv_test", "object": "conversation", "created_at": 1}
            )
        if path == "/v1/conversations/conv_test/items":
            if request.method == "POST":
                assert json.loads(request.content) == {
                    "items": [
                        {"type": "message", "role": "assistant", "content": "Welcome"}
                    ]
                }
                return httpx.Response(200, json={"data": [{"id": "msg_welcome"}]})
            assert request.url.params["order"] == "desc"
            assert request.url.params["limit"] == "2"
            if "after" not in request.url.params:
                data = [
                    {"id": "tool_1", "type": "function_call", "name": "submit"},
                    {
                        "id": "msg_new",
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "New "},
                            {"type": "output_text", "text": "answer"},
                        ],
                    },
                ]
                has_more = True
            else:
                assert request.url.params["after"] == "msg_new"
                data = [
                    {
                        "id": "msg_old",
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Question"}],
                    }
                ]
                has_more = False
            return httpx.Response(
                200,
                json={
                    "data": data,
                    "object": "list",
                    "has_more": has_more,
                    "first_id": data[0]["id"],
                    "last_id": data[-1]["id"],
                },
            )
        if path == "/v1/conversations/conv_test" and request.method == "DELETE":
            return httpx.Response(200, json={"id": "conv_test", "deleted": True})
        pytest.fail(f"Unexpected API request: {request.method} {request.url}")

    # Only the HTTP transport is simulated; SDK serialization and response
    # models are real. The live test below verifies the provider contract too.
    with openai.OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as sdk:
        client = ConversationsClient("TEST")
        client._store_mode = "openai"
        client.client = sdk
        assert client.create_thread() == "conv_test"
        assert client.add_message("conv_test", "assistant", "Welcome") == "msg_welcome"
        assert client.list_messages("conv_test", limit=2) == [
            {"role": "assistant", "content": "New answer"},
            {"role": "user", "content": "Question"},
        ]
        assert client.delete_thread("conv_test")
    assert len(requests) == 5


def _write_origin_examples(
    client: ConversationsClient, thread_id: str
) -> list[dict[str, str]]:
    """Write identical player/control text alongside untouched legacy records."""
    control = (
        "[SYSTEM] Phase setting complete. Proceeding to character. "
        "Please introduce the next phase."
    )
    messages = [
        {"role": "assistant", "content": "Welcome"},
        {"role": "user", "content": control},
        {"role": "user", "content": control, "origin": "wizard_control"},
        {"role": "user", "content": control, "origin": "user"},
    ]
    for message in messages:
        if "origin" in message:
            client.add_message(
                thread_id,
                message["role"],
                message["content"],
                origin=message["origin"],
            )
        else:
            client.add_message(thread_id, message["role"], message["content"])
    return messages


@pytest.mark.parametrize("backend", ["memory", "file"])
def test_local_conversation_origins_and_literal_envelope_round_trip(
    tmp_path: Path, backend: str
) -> None:
    """Retain provenance and decode a player's literal envelope only once."""
    client = ConversationsClient("TEST")
    if backend == "file":
        client._store_mode = "file"
        client._file_store = _FileConversationStore(tmp_path)
    thread_id = client.create_thread()
    messages = _write_origin_examples(client, thread_id)

    # Read the actual opaque stored value, without depending on its wire format.
    path = tmp_path / f"{thread_id}.json"
    stored = (
        json.loads(path.read_text())
        if backend == "file"
        else client._test_threads[thread_id]
    )
    assert stored[1]["content"] == messages[1]["content"]
    literal = stored[2]["content"]
    assert literal != messages[2]["content"]
    client.add_message(thread_id, "user", literal, origin="user")
    messages.append({"role": "user", "content": literal, "origin": "user"})

    if backend == "file":
        before_read = path.read_bytes()
        # A fresh wrapper and store must recover provenance from disk alone.
        client = ConversationsClient("TEST")
        client._store_mode = "file"
        client._file_store = _FileConversationStore(tmp_path)

    assert client.list_messages(thread_id, limit=0) == list(reversed(messages))
    assert client.list_messages(thread_id, limit=1) == [messages[-1]]
    if backend == "file":
        assert path.read_bytes() == before_read


def test_openai_conversation_origins_survive_storage_and_new_client() -> None:
    """Real SDK serialization preserves origin without changing request roles."""
    stored: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/conversations/conv_origins/items"
        if request.method == "POST":
            item = json.loads(request.content)["items"][0]
            assert item["type"] == "message"
            assert item["role"] == ("assistant" if not stored else "user")
            assert isinstance(item["content"], str)
            assert "origin" not in item  # Not an OpenAI item metadata field.
            item["id"] = f"msg_{len(stored)}"
            stored.append(item)
            return httpx.Response(200, json={"data": [{"id": item["id"]}]})
        assert request.method == "GET"
        assert request.url.params["order"] == "desc"
        selected = list(reversed(stored))[: int(request.url.params["limit"])]
        data = []
        for item in selected:
            text = item["content"]
            midpoint = len(text) // 2
            content_type = (
                "output_text" if item["role"] == "assistant" else "input_text"
            )
            data.append(
                {
                    **item,
                    "content": [
                        {"type": content_type, "text": text[:midpoint]},
                        {"type": content_type, "text": text[midpoint:]},
                    ],
                }
            )
        return httpx.Response(
            200,
            json={
                "data": data,
                "object": "list",
                "has_more": False,
                "first_id": data[0]["id"],
                "last_id": data[-1]["id"],
            },
        )

    with openai.OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as sdk:
        client = ConversationsClient("TEST")
        client._store_mode = "openai"
        client.client = sdk
        messages = _write_origin_examples(client, "conv_origins")
        assert stored[1]["content"] == messages[1]["content"]
        literal = stored[2]["content"]
        assert literal != messages[2]["content"]
        client.add_message("conv_origins", "user", literal, origin="user")
        messages.append({"role": "user", "content": literal, "origin": "user"})

    with openai.OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as sdk:
        resumed = ConversationsClient("TEST")
        resumed._store_mode = "openai"
        resumed.client = sdk
        assert resumed.list_messages("conv_origins", limit=0) == list(
            reversed(messages)
        )
        assert resumed.list_messages("conv_origins", limit=1) == [messages[-1]]


@pytest.mark.live_llm
def test_live_openai_wizard_history_round_trip() -> None:
    """Persist both roles across clients without touching any save database."""
    model = load_settings().global_.model.api_models["openai"].models[0].id
    client = ConversationsClient(model)
    thread_id = client.create_thread()
    message_ids: list[str] = []
    try:
        assert thread_id.startswith("conv_")
        message_ids.append(client.add_message(thread_id, "assistant", "Welcome to QA."))
        message_ids.append(client.add_message(thread_id, "user", "A moonlit harbor."))
        resumed = ConversationsClient(model)
        try:
            assert resumed.list_messages(thread_id, limit=1) == [
                {"role": "user", "content": "A moonlit harbor."}
            ]
            assert resumed.list_messages(thread_id, limit=0) == [
                {"role": "user", "content": "A moonlit harbor."},
                {"role": "assistant", "content": "Welcome to QA."},
            ]
        finally:
            resumed.client.close()
    finally:
        # Deleting a conversation alone does not delete its items.
        for message_id in message_ids:
            client.client.conversations.items.delete(
                message_id, conversation_id=thread_id
            )
        assert client.delete_thread(thread_id)
        client.client.close()
