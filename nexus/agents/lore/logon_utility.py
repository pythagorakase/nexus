"""
LOGON Utility - API Communication Handler for LORE

Manages communication with Apex AI providers (OpenAI, Anthropic, xAI).
"""

import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
import sys
import psycopg2

# Add scripts directory to path for API imports
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from scripts.api_openai import OpenAIProvider, LLMResponse
from scripts.api_anthropic import AnthropicProvider
from nexus.agents.logon.apex_schema import (
    StoryTurnResponse,
    StorytellerResponseExtended,
    create_minimal_response,
)
from nexus.api.slot_utils import require_slot_dbname

logger = logging.getLogger("nexus.lore.logon")


class LogonUtility:
    """Wrapper for Apex AI API calls using existing providers"""

    def __init__(self, settings: Dict[str, Any], dbname: Optional[str] = None):
        """
        Initialize LOGON utility with configured provider.

        Args:
            settings: Application settings dictionary
            dbname: Database name (save_01 through save_05).
                    If not provided, uses NEXUS_SLOT env var.
        """
        self.settings = settings
        self.dbname = dbname
        self.provider: Optional[object] = None
        self._system_prompt: Optional[str] = None

    def _load_system_prompt(self) -> str:
        """Load and combine the storyteller core prompt with setting context"""
        # Load storyteller core prompt
        core_prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "storyteller_core.md"

        try:
            with open(core_prompt_path, 'r') as f:
                core_prompt = f.read()
            logger.info(f"Loaded storyteller core prompt ({len(core_prompt)} chars)")
        except FileNotFoundError:
            logger.warning(f"Core prompt not found at {core_prompt_path}, using minimal fallback")
            core_prompt = "You are a narrative intelligence system generating interactive fiction."

        # Query setting from global_variables
        try:
            # Use slot-aware database connection
            db = require_slot_dbname(dbname=self.dbname)
            conn = psycopg2.connect(
                host="localhost",
                database=db,
                user="pythagor"
            )
            with conn.cursor() as cur:
                cur.execute("SELECT setting FROM global_variables WHERE id = true")
                result = cur.fetchone()

                if result and result[0]:
                    setting_data = result[0]
                    # Extract the markdown content from the JSON
                    setting_content = setting_data.get("content", "")
                    setting_title = setting_data.get("title", "Setting Context")

                    # Combine core prompt with setting
                    combined_prompt = f"{core_prompt}\n\n## {setting_title}\n\n{setting_content}"
                    logger.info(f"Combined prompt with setting context ({len(setting_content)} chars)")
                    return combined_prompt
                else:
                    logger.warning("No setting data found in global_variables, using core prompt only")
                    return core_prompt

        except Exception as e:
            logger.error(f"Failed to load setting from database: {e}")
            return core_prompt
        finally:
            if 'conn' in locals():
                conn.close()

    def _initialize_provider(self) -> None:
        """Initialize the appropriate API provider based on settings"""
        apex_settings = self.settings.get("API Settings", {}).get("apex", {})
        provider_type = apex_settings.get("provider", "openai")
        model = apex_settings.get("model", "gpt-4o")

        # Load system prompt
        system_prompt = self._load_system_prompt()

        if provider_type == "openai":
            self.provider = OpenAIProvider(
                model=model,
                temperature=apex_settings.get("temperature", 0.7),
                max_output_tokens=apex_settings.get("max_output_tokens", 25000),
                reasoning_effort=apex_settings.get("reasoning_effort", "medium"),
                system_prompt=system_prompt
            )
        elif provider_type == "anthropic":
            self.provider = AnthropicProvider(
                model=model,
                temperature=apex_settings.get("temperature", 0.7),
                max_tokens=apex_settings.get("max_tokens", 4000),
                system_prompt=system_prompt
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

        logger.info(f"LOGON initialized with {provider_type} provider using model {model}")
        logger.info(f"System prompt loaded: {len(system_prompt)} chars")
    
    def _ensure_provider(self) -> None:
        """Ensure the provider is initialized before use."""
        if self.provider is None:
            self._initialize_provider()

    def ensure_provider(self) -> None:
        """Public wrapper for provider initialization."""
        self._ensure_provider()
    
    def generate_narrative(self, context_payload: Dict) -> StoryTurnResponse:
        """Generate narrative from context payload with structured output"""
        self._ensure_provider()
        # Format the context into a prompt
        prompt = self._format_context_prompt(context_payload)

        # Get structured completion from provider
        # This returns a tuple of (parsed_object, llm_response)
        try:
            parsed_response, llm_response = self.provider.get_structured_completion(
                prompt,
                StorytellerResponseExtended,
            )
            logger.debug(f"Received structured response with narrative length: {len(parsed_response.narrative)}")
            return parsed_response  # Return the StoryTurnResponse object
        except Exception as e:
            logger.error(f"Failed to get structured response: {e}")
            # Fall back to plain text if structured output fails
            response = self.provider.get_completion(prompt)
            # Create a minimal StoryTurnResponse from plain text
            return create_minimal_response(response.content)
    
    def _format_context_prompt(self, context: Dict) -> str:
        """Format context payload into a prompt for the Apex AI"""
        sections = []

        # Add warm slice
        if context.get("warm_slice"):
            sections.append("=== RECENT NARRATIVE ===")
            for chunk in context["warm_slice"]["chunks"]:
                sections.append(chunk.get("text", ""))

        # Add user input
        sections.append("\n=== USER INPUT ===")
        sections.append(context.get("user_input", ""))

        # Add entity data with hierarchical support
        entity_data = context.get("entity_data", {})
        if entity_data:
            sections.append("\n=== ENTITY DOSSIER ===")

            # Check if using hierarchical structure
            characters = entity_data.get("characters", [])
            is_hierarchical = isinstance(characters, dict) and ("baseline" in characters or "featured" in characters)

            if is_hierarchical:
                # New hierarchical format
                # Baseline characters (minimal 1-line summaries)
                baseline_chars = characters.get("baseline", [])
                if baseline_chars:
                    sections.append("\nAll Characters (brief status):")
                    for char in baseline_chars:
                        name = char.get("name", "Unknown")
                        location = char.get("current_location", "unknown location")
                        activity = char.get("current_activity", "status unknown")
                        sections.append(f"- {name}: at {location}, {activity}")

                # Featured characters (full details)
                featured_chars = characters.get("featured", [])
                if featured_chars:
                    sections.append("\nFeatured Characters (full details):")
                    for char in featured_chars:
                        name = char.get("name", "Unknown")
                        ref_type = char.get("reference_type", "")
                        summary = char.get("summary", "")
                        sections.append(f"- {name} [{ref_type}]: {summary}")

                        # Add detailed fields if present
                        if char.get("personality"):
                            sections.append(f"  Personality: {char['personality']}")
                        if char.get("emotional_state"):
                            sections.append(f"  Emotional State: {char['emotional_state']}")

                # Locations (hierarchical)
                locations = entity_data.get("locations", {})
                baseline_locs = locations.get("baseline", [])
                featured_locs = locations.get("featured", [])

                if baseline_locs:
                    sections.append("\nAll Locations (brief):")
                    for loc in baseline_locs:
                        name = loc.get("name", "Unknown")
                        status = loc.get("current_status", "")
                        sections.append(f"- {name}: {status}")

                if featured_locs:
                    sections.append("\nFeatured Locations (full details):")
                    for loc in featured_locs:
                        name = loc.get("name", "Unknown")
                        ref_type = loc.get("reference_type", "")
                        summary = loc.get("summary", "")
                        sections.append(f"- {name} [{ref_type}]: {summary}")

                # Factions (hierarchical)
                factions = entity_data.get("factions", {})
                baseline_factions = factions.get("baseline", [])
                featured_factions = factions.get("featured", [])

                if baseline_factions:
                    sections.append("\nAll Factions (brief):")
                    for faction in baseline_factions:
                        name = faction.get("name", "Unknown")
                        activity = faction.get("current_activity", "")
                        sections.append(f"- {name}: {activity}")

                if featured_factions:
                    sections.append("\nFeatured Factions (full details):")
                    for faction in featured_factions:
                        name = faction.get("name", "Unknown")
                        summary = faction.get("summary", "")
                        sections.append(f"- {name}: {summary}")
            else:
                # Flat format (backward compatibility)
                if characters:
                    sections.append("\nCharacters:")
                    for char in characters:
                        sections.append(f"- {char.get('name', 'Unknown')}: {char.get('summary', '')}")

                locations = entity_data.get("locations", [])
                if locations:
                    sections.append("\nLocations:")
                    for loc in locations:
                        sections.append(f"- {loc.get('name', 'Unknown')}: {loc.get('description', '') or loc.get('summary', '')}")

            # Relationships, events, threats (same for both formats)
            relationships = entity_data.get("relationships", [])
            if relationships:
                sections.append("\nRelationships:")
                for rel in relationships[:5]:  # Limit to top 5
                    char1 = rel.get("character1_name", "Unknown")
                    char2 = rel.get("character2_name", "Unknown")
                    rel_type = rel.get("relationship_type", "unknown")
                    sections.append(f"- {char1} → {char2}: {rel_type}")

            events = entity_data.get("events", [])
            if events:
                sections.append("\nActive Events:")
                for event in events[:5]:  # Limit to top 5
                    name = event.get("name", "Unknown")
                    summary = event.get("summary", "")
                    sections.append(f"- {name}: {summary}")

            threats = entity_data.get("threats", [])
            if threats:
                sections.append("\nActive Threats:")
                for threat in threats[:5]:  # Limit to top 5
                    name = threat.get("name", "Unknown")
                    description = threat.get("description", "")
                    sections.append(f"- {name}: {description}")

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
