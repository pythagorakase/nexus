"""LOGON Utility - API Communication Handler for LORE."""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Add scripts directory to path for API imports
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from scripts.api_anthropic import AnthropicProvider
from scripts.api_openai import LLMResponse, OpenAIProvider

logger = logging.getLogger("nexus.lore.logon")


class LogonUtility:
    """Wrapper for Apex AI API calls using existing providers."""

    def __init__(self, settings: Dict[str, Any]):
        """Store settings and defer provider initialization."""
        self.settings = settings
        self.provider: Optional[Union[OpenAIProvider, AnthropicProvider]] = None

    def ensure_provider(self) -> None:
        """Public helper to ensure the provider is ready."""
        self._ensure_provider()

    def _ensure_provider(self) -> None:
        """Instantiate the provider on demand."""
        if self.provider is not None:
            return

        apex_settings = self.settings.get("API Settings", {}).get("apex", {})
        provider_type = apex_settings.get("provider", "openai")
        model = apex_settings.get("model", "gpt-4o")

        if provider_type == "openai":
            self.provider = OpenAIProvider(
                model=model,
                temperature=apex_settings.get("temperature", 0.7),
                max_tokens=apex_settings.get("max_tokens", 4000),
                reasoning_effort=apex_settings.get("reasoning_effort", "medium"),
            )
        elif provider_type == "anthropic":
            self.provider = AnthropicProvider(
                model=model,
                temperature=apex_settings.get("temperature", 0.7),
                max_tokens=apex_settings.get("max_tokens", 4000),
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

        logger.info(
            "LOGON initialized with %s provider using model %s",
            provider_type,
            model,
        )

    def generate_narrative(self, context_payload: Dict[str, Any]) -> LLMResponse:
        """Generate narrative from context payload."""
        self._ensure_provider()

        if not self.provider:
            raise RuntimeError("LOGON provider failed to initialize")

        prompt = self._format_context_prompt(context_payload)
        return self.provider.get_completion(prompt)
    
    def _format_context_prompt(self, context: Dict[str, Any]) -> str:
        """Format context payload into a prompt for the Apex AI."""
        sections = []
        
        # Add warm slice
        if context.get("warm_slice"):
            sections.append("=== RECENT NARRATIVE ===")
            for chunk in context["warm_slice"]["chunks"]:
                sections.append(chunk.get("text", ""))
        
        # Add user input
        sections.append("\n=== USER INPUT ===")
        sections.append(context.get("user_input", ""))
        
        # Add entity data
        if context.get("entity_data"):
            sections.append("\n=== RELEVANT ENTITIES ===")
            if context["entity_data"].get("characters"):
                sections.append("Characters:")
                for char in context["entity_data"]["characters"]:
                    sections.append(f"- {char.get('name', 'Unknown')}: {char.get('summary', '')}")
            
            if context["entity_data"].get("locations"):
                sections.append("Locations:")
                for loc in context["entity_data"]["locations"]:
                    sections.append(f"- {loc.get('name', 'Unknown')}: {loc.get('description', '')}")
        
        # Add retrieved passages
        if context.get("retrieved_passages"):
            sections.append("\n=== HISTORICAL CONTEXT ===")
            for passage in context["retrieved_passages"]["results"][:5]:  # Limit to top 5
                sections.append(f"[Score: {passage.get('score', 0):.2f}] {passage.get('text', '')}")
        
        # Add instructions
        sections.append("\n=== INSTRUCTIONS ===")
        sections.append("Continue the narrative based on the provided context and user input.")
        sections.append("Maintain consistency with established characters, locations, and plot.")

        return "\n".join(sections)
