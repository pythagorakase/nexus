"""Real loopback requests from consumers using the guarded TEST SDK route."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from pydantic_ai import Agent

from nexus.api.conversations import ConversationsClient
from nexus.api.pydantic_ai_utils import build_pydantic_ai_model_with_provider
from scripts.api_openai import OpenAIProvider
from tests.scheduler_helpers import test_provider_config as configure_test
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401


def test_pydantic_consumer_test_request(monkeypatch, tmp_path, mock_openai_server):
    """Use the repository TEST server and real async SDK through Pydantic AI."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    configure_test(tmp_path, mock_openai_server, monkeypatch)
    model, provider = build_pydantic_ai_model_with_provider("TEST")
    assert provider == "test"
    result = Agent(model).run_sync("Say hello.")
    assert result.output
    assert result.usage().requests == 1


def test_conversations_test_request(monkeypatch):
    """Exercise the Conversations SDK path over a real TEST loopback socket.

    TEST normally stores conversation history in memory. Select its existing
    SDK branch explicitly, as the protocol test does, with a guarded real client.
    """
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, self.headers.get("Authorization")))
            body = json.dumps(
                {"id": "conv_guard", "object": "conversation", "created_at": 1}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    wrapper = OpenAIProvider(
        model="TEST",
        api_key="test-key",
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
    )
    try:
        consumer = ConversationsClient("TEST")
        consumer._store_mode = "openai"
        consumer.client = wrapper.client
        assert consumer.create_thread() == "conv_guard"
        assert received == [("/v1/conversations", "Bearer test-key")]
    finally:
        if wrapper._client is not None:
            wrapper.client.close()
        server.shutdown()
        server.server_close()
        thread.join()


def test_openrouter_http_loads_credential_without_sdk(monkeypatch):
    """The direct HTTP route sends a loaded credential on a real TEST request."""
    from nexus.util.secret_manager import get_secret
    from scripts.api_openrouter import OpenRouterProvider

    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-router-key")
    get_secret.cache_clear()
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((self.path, self.headers.get("Authorization"), payload))
            body = json.dumps(
                {
                    "choices": [{"message": {"content": "TEST reply"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    wrapper = OpenRouterProvider(model="TEST", reasoning_effort="low")
    wrapper.API_BASE = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        assert wrapper.api_key is None
        assert wrapper.get_completion("guarded HTTP proof").content == "TEST reply"
        assert wrapper._client is None
        assert len(received) == 1
        path, authorization, payload = received[0]
        assert path == "/v1/chat/completions"
        assert authorization == "Bearer test-router-key"
        assert payload["model"] == "TEST"
        assert payload["reasoning"]["effort"] == "low"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        get_secret.cache_clear()
