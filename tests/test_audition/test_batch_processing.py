import importlib.util
import sys
import types
from pathlib import Path

if "sqlalchemy" not in sys.modules:
    sqlalchemy_stub = types.ModuleType("sqlalchemy")

    def _unsupported(*_args, **_kwargs):  # pragma: no cover - test shim
        raise RuntimeError("sqlalchemy is unavailable in unit tests")

    sqlalchemy_stub.create_engine = _unsupported
    sys.modules["sqlalchemy"] = sqlalchemy_stub

from scripts.api_anthropic import AnthropicProvider


def _load_batch_orchestrator_module():
    module_path = Path(__file__).resolve().parents[2] / "nexus" / "audition" / "batch_orchestrator.py"
    spec = importlib.util.spec_from_file_location("_test_batch_orchestrator", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules.setdefault("_test_batch_orchestrator", module)
    spec.loader.exec_module(module)
    return module


batch_orchestrator = _load_batch_orchestrator_module()
BatchOrchestrator = batch_orchestrator.BatchOrchestrator
RateLimits = batch_orchestrator.RateLimits


def _make_anthropic_provider_stub() -> AnthropicProvider:
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.system_prompt = None
    return provider


def test_format_messages_with_cache_preserves_headers():
    provider = _make_anthropic_provider_stub()
    prompt = "\n".join(
        [
            "=== RECENT STORYTELLER CONTEXT ===",
            "Line 1",
            "=== ENTITY DOSSIER ===",
            "Line 2",
        ]
    )

    messages = provider._format_messages_with_cache(prompt)
    assert messages[0]["role"] == "user"
    content_blocks = messages[0]["content"]
    assert content_blocks[0]["text"].startswith("=== RECENT STORYTELLER CONTEXT ===")
    assert content_blocks[1]["text"].startswith("=== ENTITY DOSSIER ===")


def test_get_limits_case_insensitive_lookup():
    orchestrator = BatchOrchestrator()
    orchestrator.limits = {
        "anthropic:claude-test": RateLimits(tokens_per_minute=1000, requests_per_minute=50)
    }

    limits = orchestrator.get_limits("Anthropic", "Claude-Test")
    assert limits.tokens_per_minute == 1000
    assert orchestrator.get_tracker("ANTHROPIC", "CLAUDE-TEST") is orchestrator.get_tracker(
        "anthropic", "claude-test"
    )
