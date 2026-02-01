"""Integration tests for LLM backends (requires real services)."""

import pytest
from nexus.llm import LLMRouter
from nexus.llm.remote import RemoteLMStudioBackend


@pytest.mark.asyncio
@pytest.mark.integration
async def test_remote_lmstudio_completion():
    """Test actual completion via remote LM Studio."""
    backend = RemoteLMStudioBackend(
        base_url="http://100.67.181.95:1234/v1",
        model=None,  # Use server default
    )
    
    if not backend.is_available():
        pytest.skip("Remote LM Studio not available")
    
    response = await backend.complete("Say 'hello' and nothing else.")
    
    assert response.content
    assert "hello" in response.content.lower()
    print(f"Response: {response.content}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_router_with_real_backends():
    """Test router fallback with real backend configuration."""
    router = LLMRouter(settings_path="nexus.toml")
    
    if not router.is_available():
        pytest.skip("No LLM backends available")
    
    response = await router.complete("What is 2+2? Answer with just the number.")
    
    assert response.content
    assert "4" in response.content
    print(f"Router response: {response.content}")
