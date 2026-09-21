"""Verify the wizard's Conversations protocol with the real OpenAI SDK."""

from __future__ import annotations

import json

import httpx
import openai
import pytest

from nexus.api.conversations import ConversationsClient
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
