"""
New story structured output generator using OpenAI or Anthropic structured outputs.

This module handles the generation of structured story components during
the new story initialization phase (new_story=true).
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Tuple, Type
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from nexus.api.new_story_schemas import (
    SettingCard,
    CharacterSheet,
    StorySeed,
    LayerDefinition,
    ZoneDefinition,
    PlaceProfile,
    TransitionData,
)
from nexus.api.resilient_openai import create_resilient_client
from scripts.api_openai import OpenAIProvider
from scripts.api_anthropic import AnthropicProvider
from nexus.config.loader import get_provider_for_model

logger = logging.getLogger("nexus.api.new_story_generator")


class StoryComponentGenerator:
    """
    Generates structured story components using OpenAI or Anthropic structured outputs.

    This class handles all the structured generation needed during new story
    initialization, using Pydantic models for type safety and validation.
    """

    def __init__(self, model: str = "gpt-5.1", use_resilient: bool = True):
        """
        Initialize the story generator.

        Args:
            model: Model name to use (default: gpt-5.1)
            use_resilient: Whether to use resilient OpenAI client with retry logic
        """
        self.model = model

        self.provider = get_provider_for_model(model)

        if self.provider == "anthropic":
            self.client = AnthropicProvider(model=model)
        else:
            # Get API key using the standard provider
            provider = OpenAIProvider(model=model)
            api_key = provider.api_key

            # Create client (resilient or standard)
            if use_resilient:
                logger.info("Using resilient OpenAI client with retry logic")
                self.client = create_resilient_client(api_key, async_client=False)
            else:
                import openai

                self.client = openai.OpenAI(api_key=api_key)

    def _split_anthropic_prompt(
        self, messages: List[Dict[str, str]]
    ) -> Tuple[Optional[str], str]:
        system_parts: List[str] = []
        user_parts: List[str] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                user_parts.append(f"[{role.upper()}]\n{content}")
        system_prompt = "\n\n".join(system_parts).strip() or None
        user_prompt = "\n\n".join(user_parts).strip()
        return system_prompt, user_prompt

    def _generate_structured(
        self,
        messages: List[Dict[str, str]],
        schema_model: Type[BaseModel],
    ) -> BaseModel:
        if self.provider == "anthropic":
            system_prompt, user_prompt = self._split_anthropic_prompt(messages)
            self.client.system_prompt = system_prompt
            result, _ = self.client.get_structured_completion(
                user_prompt, schema_model
            )
            return result

        response = self.client.responses.parse(
            model=self.model,
            input=messages,
            text_format=schema_model,
        )
        return response.output_parsed

    def generate_setting_card(
        self,
        user_preferences: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ) -> SettingCard:
        """
        Generate a complete setting card based on user preferences.

        Args:
            user_preferences: User's description of desired setting
            conversation_context: Optional conversation history

        Returns:
            A validated SettingCard object
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a creative world-builder for an interactive narrative system. "
                    "Create rich, consistent settings that provide fertile ground for storytelling. "
                    "Ensure all details work together cohesively."
                ),
            }
        ]

        # Add conversation context if provided
        if conversation_context:
            messages.extend(conversation_context)

        messages.append(
            {
                "role": "user",
                "content": (
                    f"Based on these preferences, create a complete setting for the story:\n\n"
                    f"{user_preferences}\n\n"
                    f"Generate a detailed SettingCard with all required fields. "
                    f"Make the world feel lived-in and authentic to its genre."
                ),
            }
        )

        try:
            result = self._generate_structured(messages, SettingCard)
            logger.info(f"Generated setting: {result.world_name} ({result.genre})")
            return result

        except Exception as e:
            logger.error(f"Failed to generate setting card: {e}")
            raise

    def generate_character_sheet(
        self,
        setting: SettingCard,
        character_concept: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ) -> CharacterSheet:
        """
        Generate a complete character sheet based on setting and user input.

        Args:
            setting: The established setting card
            character_concept: User's character concept/preferences
            conversation_context: Optional conversation history

        Returns:
            A validated CharacterSheet object
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a character designer for an interactive narrative system. "
                    "Create compelling protagonists with clear motivations, flaws, and growth potential. "
                    "Characters should feel authentic to their setting while being interesting to play."
                ),
            }
        ]

        if conversation_context:
            messages.extend(conversation_context)

        # Include setting context
        setting_context = (
            f"Setting: {setting.world_name}\n"
            f"Genre: {setting.genre}\n"
            f"Time Period: {setting.time_period}\n"
            f"Tech Level: {setting.tech_level}\n"
            f"Major Conflict: {setting.major_conflict}\n"
            f"Tone: {setting.tone}"
        )

        messages.append(
            {
                "role": "user",
                "content": (
                    f"Create a protagonist for this setting:\n\n"
                    f"{setting_context}\n\n"
                    f"Character Concept:\n{character_concept}\n\n"
                    f"Generate a complete CharacterSheet with rich detail. "
                    f"The character should have clear strengths, weaknesses, and room for growth. "
                    f"Make them feel like a real person with history and relationships. "
                    f"Include trait_1, trait_2, and trait_3 (name + description) from the trait menu, "
                    f"plus the required wildcard trait."
                ),
            }
        )

        try:
            result = self._generate_structured(messages, CharacterSheet)
            logger.info(f"Generated character: {result.name} ({result.background})")
            return result

        except Exception as e:
            logger.error(f"Failed to generate character sheet: {e}")
            raise

    def generate_story_seeds(
        self, setting: SettingCard, character: CharacterSheet
    ) -> List[StorySeed]:
        """
        Generate multiple story seed options for the user to choose from.

        Args:
            setting: The established setting
            character: The created character

        Returns:
            List of StorySeed objects
        """

        # Create a wrapper model for multiple seeds
        class StorySeedCollection(BaseModel):
            """Collection of story seeds"""

            seeds: List[StorySeed] = Field(
                min_length=2,
                max_length=4,
                description="2-4 unique story seeds",
            )

            class Config:
                extra = "forbid"

        # Extract selected traits (exactly 3 entries)
        selected_traits = [
            f"{trait.name.title()}: {trait.description}"
            for trait in character.get_trait_entries()
        ]

        # Format traits for the prompt
        traits_text = (
            "\n".join(selected_traits) if selected_traits else "None specified"
        )
        wildcard_text = f"{character.wildcard_name}: {character.wildcard_description}"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a narrative designer creating compelling story openings. "
                    "Each seed should offer different types of experiences and player choices. "
                    "Openings should provide immediate engagement while setting up longer arcs."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create 2-4 unique story openings for:\n\n"
                    f"Setting: {setting.world_name} ({setting.genre})\n"
                    f"Protagonist: {character.name}\n"
                    f"Summary: {character.summary}\n"
                    f"Background: {character.background}\n"
                    f"Personality: {character.personality}\n\n"
                    f"Character Traits:\n{traits_text}\n\n"
                    f"Wildcard: {wildcard_text}\n\n"
                    f"Each seed should:\n"
                    f"1. Start in a different type of situation\n"
                    f"2. Offer clear player agency\n"
                    f"3. Connect to the character's traits and background\n"
                    f"4. Set up interesting narrative possibilities\n"
                    f"5. Feel appropriate to the {setting.tone} tone\n\n"
                    "Generate 2-4 StorySeed objects with all required fields."
                ),
            },
        ]

        try:
            result = self._generate_structured(messages, StorySeedCollection)
            logger.info(f"Generated {len(result.seeds)} story seeds")
            return result.seeds

        except Exception as e:
            logger.error(f"Failed to generate story seeds: {e}")
            raise

    def generate_location_hierarchy(
        self, setting: SettingCard, seed: StorySeed, character: CharacterSheet
    ) -> tuple[LayerDefinition, ZoneDefinition, PlaceProfile]:
        """
        Generate the complete location hierarchy based on chosen seed.

        Args:
            setting: The established setting
            seed: The chosen story seed
            character: The protagonist

        Returns:
            Tuple of (LayerDefinition, ZoneDefinition, PlaceProfile)
        """

        # Create a wrapper for the complete hierarchy
        class LocationHierarchy(BaseModel):
            """Complete location hierarchy from layer down to place"""

            layer: LayerDefinition = Field(description="World layer (planet/dimension)")
            zone: ZoneDefinition = Field(description="Geographic zone")
            place: PlaceProfile = Field(
                description="The specific place with latitude/longitude"
            )

            class Config:
                extra = "forbid"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a location designer for an interactive narrative. "
                    "Create vivid, atmospheric locations that serve both as settings "
                    "and as active participants in the story."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Create the starting location for this story opening:\n\n"
                    f"Setting: {setting.world_name} ({setting.time_period})\n"
                    f"Opening: {seed.title}\n"
                    f"Situation: {seed.situation}\n"
                    f"Create the complete location hierarchy:\n"
                    f"1. A LayerDefinition for the world/planet\n"
                    f"2. A ZoneDefinition for the geographic region\n"
                    f"3. A PlaceProfile for the specific starting location WITH latitude/longitude\n\n"
                    f"CRITICAL: The PlaceProfile MUST include valid latitude and longitude fields.\n"
                    f"Use real Earth latitude/longitude even for fantasy settings. "
                    f"Treat fantasy worlds as 'mirror-Earth' - place locations where analogous real places would be. "
                    f"For example, a fantasy kingdom could use coordinates for Germany (51.5, 10.5), "
                    f"a desert city could use coordinates for Cairo (30.0, 31.2), etc.\n\n"
                    f"The place should be where {character.name} begins their story, with exact latitude/longitude."
                ),
            },
        ]

        try:
            result = self._generate_structured(messages, LocationHierarchy)

            logger.info(
                f"Generated location hierarchy: {result.layer.name} -> "
                f"{result.zone.name} -> {result.place.name} at "
                f"({result.place.latitude}, {result.place.longitude})"
            )
            return result.layer, result.zone, result.place

        except Exception as e:
            logger.error(f"Failed to generate place and zone: {e}")
            raise

    def generate_transition_data(
        self,
        thread_id: str,
        setting: SettingCard,
        character: CharacterSheet,
        seed: StorySeed,
        layer: LayerDefinition,
        zone: ZoneDefinition,
        location: PlaceProfile,
        setup_start_time: Optional[datetime] = None,
    ) -> TransitionData:
        """
        Assemble complete transition data package.

        Args:
            thread_id: OpenAI conversation thread ID
            setting: Completed setting card
            character: Completed character sheet
            seed: Chosen story seed
            location: Starting location
            zone: Starting zone
            setup_start_time: When setup began (for duration calc)

        Returns:
            Complete TransitionData ready for narrative mode
        """
        # Calculate setup duration if start time provided
        setup_duration = None
        if setup_start_time:
            duration = datetime.now(timezone.utc) - setup_start_time
            setup_duration = int(duration.total_seconds() / 60)

        # Create transition data
        # Use the seed's atomized timestamp if available, otherwise fall back to now()
        base_timestamp = (
            seed.get_base_datetime() if seed else datetime.now(timezone.utc)
        )
        transition = TransitionData(
            setting=setting,
            character=character,
            seed=seed,
            layer=layer,
            zone=zone,
            location=location,
            base_timestamp=base_timestamp,
            thread_id=thread_id,
            setup_duration_minutes=setup_duration,
        )

        # Validate completeness
        if transition.validate_completeness():
            logger.info("Transition data validated and ready")
        else:
            logger.warning("Transition data incomplete - may need additional fields")

        return transition


class InteractiveSetupFlow:
    """
    Manages the interactive flow of new story setup.

    This coordinates the conversation phases and structured generation.
    """

    def __init__(self, generator: StoryComponentGenerator):
        """
        Initialize the setup flow.

        Args:
            generator: The story component generator to use
        """
        self.generator = generator
        self.conversation_history: List[Dict[str, str]] = []
        self.setup_start = datetime.now(timezone.utc)

        # Component storage
        self.setting: Optional[SettingCard] = None
        self.character: Optional[CharacterSheet] = None
        self.seeds: List[StorySeed] = []
        self.chosen_seed: Optional[StorySeed] = None
        self.layer: Optional[LayerDefinition] = None
        self.zone: Optional[ZoneDefinition] = None
        self.location: Optional[PlaceProfile] = None

    def add_to_history(self, role: str, content: str):
        """Add a message to conversation history."""
        self.conversation_history.append({"role": role, "content": content})

    def phase1_generate_setting(self, user_input: str) -> SettingCard:
        """Phase 1: Generate setting based on user preferences."""
        self.add_to_history("user", user_input)
        self.setting = self.generator.generate_setting_card(
            user_input, self.conversation_history
        )
        self.add_to_history("assistant", f"Created setting: {self.setting.world_name}")
        return self.setting

    def phase2_generate_character(self, user_input: str) -> CharacterSheet:
        """Phase 2: Generate character based on user concept."""
        if not self.setting:
            raise ValueError("Setting must be generated before character")

        self.add_to_history("user", user_input)
        self.character = self.generator.generate_character_sheet(
            self.setting, user_input, self.conversation_history
        )
        self.add_to_history("assistant", f"Created character: {self.character.name}")
        return self.character

    def phase3_generate_seeds(self) -> List[StorySeed]:
        """Phase 3: Generate story seed options."""
        if not self.setting or not self.character:
            raise ValueError("Setting and character required for seeds")

        self.seeds = self.generator.generate_story_seeds(self.setting, self.character)
        self.add_to_history(
            "assistant",
            f"Generated {len(self.seeds)} story options: "
            + ", ".join([s.title for s in self.seeds]),
        )
        return self.seeds

    def phase3_choose_seed(self, seed_index: int) -> StorySeed:
        """User selects a seed from the options."""
        if 0 <= seed_index < len(self.seeds):
            self.chosen_seed = self.seeds[seed_index]
            self.add_to_history("user", f"Chose: {self.chosen_seed.title}")
            return self.chosen_seed
        else:
            raise ValueError(f"Invalid seed index: {seed_index}")

    def phase4_generate_location(
        self,
    ) -> tuple[LayerDefinition, ZoneDefinition, PlaceProfile]:
        """Phase 4: Generate complete location hierarchy."""
        if not self.chosen_seed:
            raise ValueError("Must choose seed before generating location")

        layer, zone, location = self.generator.generate_location_hierarchy(
            self.setting, self.chosen_seed, self.character
        )

        self.layer = layer
        self.zone = zone
        self.location = location
        self.add_to_history(
            "assistant",
            f"Created location hierarchy: {layer.name} -> {zone.name} -> {location.name}",
        )
        return layer, zone, location

    def finalize_transition(self, thread_id: str) -> TransitionData:
        """
        Finalize all data for transition to narrative mode.

        Args:
            thread_id: OpenAI conversation thread ID

        Returns:
            Complete transition data package
        """
        if not all(
            [
                self.setting,
                self.character,
                self.chosen_seed,
                self.layer,
                self.zone,
                self.location,
            ]
        ):
            raise ValueError("All components must be generated before transition")

        return self.generator.generate_transition_data(
            thread_id=thread_id,
            setting=self.setting,
            character=self.character,
            seed=self.chosen_seed,
            layer=self.layer,
            zone=self.zone,
            location=self.location,
            setup_start_time=self.setup_start,
        )
