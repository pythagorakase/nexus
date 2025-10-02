"""Unit tests for Apex Audition batch processing components."""

import importlib.util
import sys
import types
from pathlib import Path

# Stub sqlalchemy to avoid database dependencies in unit tests
if "sqlalchemy" not in sys.modules:
    sqlalchemy_stub = types.ModuleType("sqlalchemy")

    def _unsupported(*_args, **_kwargs):  # pragma: no cover - test shim
        raise RuntimeError("sqlalchemy is unavailable in unit tests")

    sqlalchemy_stub.create_engine = _unsupported
    sys.modules["sqlalchemy"] = sqlalchemy_stub

from scripts.api_anthropic import AnthropicProvider


def _load_batch_orchestrator_module():
    """Load batch orchestrator module without triggering sqlalchemy imports."""
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
    """Create AnthropicProvider instance without initialization."""
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.system_prompt = None
    return provider


def test_format_messages_with_cache_preserves_headers():
    """Verify that cache formatting preserves section headers."""
    provider = _make_anthropic_provider_stub()
    prompt = "\n".join(
        [
            "=== RECENT STORYTELLER CONTEXT ===",
            "Line 1",
            "Line 2",
            "=== ENTITY DOSSIER ===",
            "Line 3",
            "Line 4",
        ]
    )

    messages = provider._format_messages_with_cache(prompt)

    # Check structure
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "content" in messages[0]

    content_blocks = messages[0]["content"]
    assert len(content_blocks) == 2

    # Verify section headers are preserved
    assert content_blocks[0]["text"].startswith("=== RECENT STORYTELLER CONTEXT ===")
    assert "Line 1" in content_blocks[0]["text"]
    assert "Line 2" in content_blocks[0]["text"]

    assert content_blocks[1]["text"].startswith("=== ENTITY DOSSIER ===")
    assert "Line 3" in content_blocks[1]["text"]
    assert "Line 4" in content_blocks[1]["text"]


def test_get_limits_case_insensitive_lookup():
    """Verify rate limit lookup is case-insensitive."""
    orchestrator = BatchOrchestrator()
    orchestrator.limits = {
        "anthropic:claude-test": RateLimits(tokens_per_minute=1000, requests_per_minute=50)
    }

    # Test various case combinations
    limits_lower = orchestrator.get_limits("anthropic", "claude-test")
    assert limits_lower.tokens_per_minute == 1000
    assert limits_lower.requests_per_minute == 50

    limits_mixed = orchestrator.get_limits("Anthropic", "Claude-Test")
    assert limits_mixed.tokens_per_minute == 1000
    assert limits_mixed.requests_per_minute == 50

    limits_upper = orchestrator.get_limits("ANTHROPIC", "CLAUDE-TEST")
    assert limits_upper.tokens_per_minute == 1000
    assert limits_upper.requests_per_minute == 50


def test_get_tracker_case_insensitive():
    """Verify tracker instances are shared across case variations."""
    orchestrator = BatchOrchestrator()

    tracker1 = orchestrator.get_tracker("anthropic", "claude-test")
    tracker2 = orchestrator.get_tracker("ANTHROPIC", "CLAUDE-TEST")
    tracker3 = orchestrator.get_tracker("Anthropic", "Claude-Test")

    # All should return the same tracker instance
    assert tracker1 is tracker2
    assert tracker2 is tracker3
