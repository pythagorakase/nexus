#!/usr/bin/env python3
"""
psyche.py: Character Psychologist Agent for Night City Stories

This module serves as the Character Psychologist agent in the agent-based narrative
intelligence system. It analyzes individual character psychology, interpersonal
relationships, and provides psychological insights for narrative generation.

The agent integrates with character analyzers for individual and relationship analysis,
interfaces with the entity state database, and provides psychological interpretations
of narrative events and character actions.

Usage:
    # Import and initialize the agent
    from agents.psyche import CharacterPsychologist
    psyche_agent = CharacterPsychologist()
    
    # Process message through maestro
    # Or run standalone for testing
    python psyche.py --test
"""

import os
import sys
import json
import logging
import argparse
import time
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any, Set

# Import BaseAgent
from agent_base import BaseAgent

# Try to import required modules
try:
    # Import configuration manager
    import config_manager as config
    
    # Import database modules
    import db_sqlite
    
    # Import memory manager
    import memnon
    
    # Import character analyzers
    try:
        from psyche_mono import CharacterAnalyzer
    except ImportError:
        CharacterAnalyzer = None
        
    try:
        from psyche_poly import RelationshipAnalyzer
    except ImportError:
        RelationshipAnalyzer = None
        
except ImportError as e:
    print(f"Warning: Failed to import a required module: {e}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("psyche.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("psyche")

# Default settings (can be overridden by config_manager)
DEFAULT_SETTINGS = {
    "psyche": {
        "character_analysis": {
            "use_character_analyzer": True,
            "trait_inference_threshold": 0.6,
            "include_growth_predictions": True,
            "max_results_per_character": 5
        },
        "relationship_analysis": {
            "use_relationship_analyzer": True,
            "relationship_depth": 2,
            "include_historical_patterns": True,
            "max_relationships_per_query": 5
        },
        "narrative_analysis": {
            "analyze_character_arcs": True,
            "analyze_relationship_dynamics": True,
            "analyze_psychological_themes": True,
            "max_analysis_token_length": 2000
        }
    }
}

class CharacterPsychologist(BaseAgent):
    """
    Character Psychologist agent that analyzes character psychology and relationships
    """
    
    def __init__(self, settings: Dict[str, Any] = None):
        """
        Initialize the Character Psychologist agent
        
        Args:
            settings: Optional settings dictionary
        """
        # Initialize BaseAgent with settings
        super().__init__(settings)
        
        # Load default settings
        self.settings = DEFAULT_SETTINGS.copy()
        
        # Update with provided settings if any
        if settings:
            self._update_settings(settings)
            
        # Load settings from config
        psyche_config = config.get_section("psyche")
        if psyche_config:
            self._update_settings({"psyche": psyche_config})
        
        # Initialize analyzers if available
        self.character_analyzer = None
        if CharacterAnalyzer and self.settings["psyche"]["character_analysis"]["use_character_analyzer"]:
            try:
                self.character_analyzer = CharacterAnalyzer(self.settings["psyche"]["character_analysis"])
                self.log("Initialized CharacterAnalyzer", logging.INFO)
            except Exception as e:
                self.log(f"Failed to initialize CharacterAnalyzer: {e}", logging.ERROR)
        
        self.relationship_analyzer = None
        if RelationshipAnalyzer and self.settings["psyche"]["relationship_analysis"]["use_relationship_analyzer"]:
            try:
                self.relationship_analyzer = RelationshipAnalyzer(self.settings["psyche"]["relationship_analysis"])
                self.log("Initialized RelationshipAnalyzer", logging.INFO)
            except Exception as e:
                self.log(f"Failed to initialize RelationshipAnalyzer: {e}", logging.ERROR)
        
        # Initialize counters for tracking
        self.update_state("character_analysis_count", 0)
        self.update_state("relationship_analysis_count", 0)
        self.update_state("narrative_analysis_count", 0)
        
        self.log("Character Psychologist initialized", logging.INFO)
    
    def _update_settings(self, settings: Dict[str, Any]) -> None:
        """
        Update settings with user-provided values
        
        Args:
            settings: New settings to apply
        """
        # Recursive dictionary update
        def update_dict(target, source):
            for key, value in source.items():
                if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                    update_dict(target[key], value)
                else:
                    target[key] = value
        
        update_dict(self.settings, settings)
    
    def process_message(self, message: Any) -> Dict[str, Any]:
        """
        Process a message from the Maestro orchestrator
        
        Args:
            message: Message object from Maestro
            
        Returns:
            Response dictionary
        """
        try:
            # Extract message content
            content = message.content
            message_type = message.message_type
            
            # Delegate to appropriate handler based on message type
            if message_type == "request":
                return self.handle_request(content)
            elif message_type == "response":
                return self.handle_response(content)
            elif message_type == "error":
                return self.handle_error(content)
            else:
                return {
                    "response": f"Unknown message type: {message_type}",
                    "error": "unsupported_message_type"
                }
                
        except Exception as e:
            self.log(f"Error processing message: {e}", logging.ERROR)
            import traceback
            self.log(traceback.format_exc(), logging.ERROR)
            
            return {
                "response": "Error processing message",
                "error": str(e)
            }
    
    def handle_request(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a request message type
        
        Args:
            content: The content of the message as a dictionary
            
        Returns:
            A dictionary with the processed response
        """
        request_type = content.get("type")
        
        if request_type == "character_analysis":
            # Handle character analysis request
            character_id = content.get("character_id")
            character_name = content.get("character_name")
            episode = content.get("episode", "S01E01")
            
            analysis = self.analyze_character(character_id, character_name, episode)
            
            return {
                "response": "Character analysis completed",
                "analysis": analysis
            }
            
        elif request_type == "relationship_analysis":
            # Handle relationship analysis request
            entity1 = content.get("entity1", {})
            entity2 = content.get("entity2", {})
            episode = content.get("episode", "S01E01")
            
            analysis = self.analyze_relationship(
                entity1.get("id"), entity1.get("name"), entity1.get("type", "character"),
                entity2.get("id"), entity2.get("name"), entity2.get("type", "character"),
                episode
            )
            
            return {
                "response": "Relationship analysis completed",
                "analysis": analysis
            }
            
        elif request_type == "narrative_psychological_analysis":
            # Handle narrative analysis request
            narrative_text = content.get("narrative_text", "")
            episode = content.get("episode", "S01E01")
            focus_entities = content.get("focus_entities", [])
            
            analysis = self.analyze_narrative_psychology(narrative_text, episode, focus_entities)
            
            return {
                "response": "Narrative psychological analysis completed",
                "analysis": analysis
            }
            
        elif request_type == "react_to_event":
            # Handle reaction prediction request
            character_id = content.get("character_id")
            character_name = content.get("character_name")
            event_description = content.get("event_description", "")
            episode = content.get("episode", "S01E01")
            
            reaction = self.predict_character_reaction(
                character_id, character_name, event_description, episode
            )
            
            return {
                "response": "Character reaction prediction completed",
                "reaction": reaction
            }
            
        else:
            return {
                "response": f"Unknown request type: {request_type}",
                "error": "unsupported_request_type"
            }
    
    def handle_response(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a response message type
        
        Args:
            content: The content of the message as a dictionary
            
        Returns:
            A dictionary with the processed response
        """
        return {
            "response": "Acknowledged",
            "original_response": content
        }
    
    def handle_error(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle an error message type
        
        Args:
            content: The content of the message as a dictionary
            
        Returns:
            A dictionary containing error details or remedial actions
        """
        self.log(f"Received error message: {content}", logging.ERROR)
        
        return {
            "response": "Error acknowledged",
            "error_details": content
        }
    
    def analyze_character(self, 
                         character_id: Optional[int] = None, 
                         character_name: Optional[str] = None,
                         episode: str = "S01E01") -> Dict[str, Any]:
        """
        Analyze a character's psychological profile
        
        Args:
            character_id: ID of the character (optional if name is provided)
            character_name: Name of the character (optional if ID is provided)
            episode: Episode for which to analyze the character
            
        Returns:
            Dictionary containing character psychological analysis
        """
        self.log(f"Analyzing character: {character_name or character_id} for episode {episode}", logging.INFO)
        
        # Try to get character ID if only name is provided
        if character_id is None and character_name and 'db_sqlite' in sys.modules:
            character = db_sqlite.get_character_by_name(character_name)
            if character:
                character_id = character["id"]
                character_name = character["name"]  # Ensure we have the correct name
        
        # Try to get character name if only ID is provided
        if character_name is None and character_id is not None and 'db_sqlite' in sys.modules:
            character = db_sqlite.get_character_by_id(character_id)
            if character:
                character_name = character["name"]
        
        # Check if we have either ID or name
        if character_id is None and character_name is None:
            self.log("Cannot analyze character: no ID or name provided", logging.ERROR)
            return {
                "error": "no_character_identifier",
                "message": "Either character ID or name must be provided"
            }
        
        # If we have the character analyzer, use it
        if self.character_analyzer:
            analysis = self.character_analyzer.analyze_character(
                character_id=character_id,
                character_name=character_name,
                episode=episode
            )
            
            # Track analysis count
            current_count = self.get_state("character_analysis_count") or 0
            self.update_state("character_analysis_count", current_count + 1)
            
            return analysis
        
        # If we don't have the analyzer, provide a simplified analysis
        return self._simplified_character_analysis(character_id, character_name, episode)
    
    def _simplified_character_analysis(self, 
                                    character_id: Optional[int], 
                                    character_name: Optional[str],
                                    episode: str) -> Dict[str, Any]:
        """
        Provide a simplified character analysis when the full analyzer is not available
        
        Args:
            character_id: ID of the character (optional)
            character_name: Name of the character (optional)
            episode: Episode for which to analyze the character
            
        Returns:
            Dictionary containing simplified character analysis
        """
        # Initialize profile with basic information
        profile = {
            "character_id": character_id,
            "character_name": character_name,
            "created_at": time.time(),
            "updated_at": time.time(),
            "analysis_method": "simplified",
            "personality_traits": {},
            "core_drives": {},
            "current_emotional_state": None,
            "current_physical_state": None,
            "interpersonal_style": None,
            "decision_making_style": None
        }
        
        # If we have database access, try to populate with info from the database
        if 'db_sqlite' in sys.modules:
            try:
                # Try to get character data
                if character_id is not None:
                    character = db_sqlite.get_character_by_id(character_id)
                elif character_name is not None:
                    character = db_sqlite.get_character_by_name(character_name)
                else:
                    character = None
                
                if character:
                    # We have character data, use it to populate the profile
                    character_id = character.get("id")
                    character_name = character.get("name")
                    
                    # Update basic info
                    profile["character_id"] = character_id
                    profile["character_name"] = character_name
                    
                    # Use database description and personality
                    profile["description"] = character.get("description", "")
                    profile["personality"] = character.get("personality", "")
                
                # Try to get current state from entity_state database
                if character_id is not None:
                    entity_states = db_sqlite.get_entity_state_at_episode(
                        "character", character_id, episode
                    )
                    
                    if entity_states:
                        # Update profile with current states
                        profile["current_emotional_state"] = entity_states.get("emotional")
                        profile["current_physical_state"] = entity_states.get("physical")
            except Exception as e:
                self.log(f"Error getting character data: {e}", logging.ERROR)
        
        # Track analysis count
        current_count = self.get_state("character_analysis_count") or 0
        self.update_state("character_analysis_count", current_count + 1)
        
        return profile
    
    def analyze_relationship(self,
                           entity1_id: Optional[int] = None,
                           entity1_name: Optional[str] = None,
                           entity1_type: str = "character",
                           entity2_id: Optional[int] = None,
                           entity2_name: Optional[str] = None,
                           entity2_type: str = "character",
                           episode: str = "S01E01") -> Dict[str, Any]:
        """
        Analyze the relationship between two entities
        
        Args:
            entity1_id: ID of the first entity (optional if name is provided)
            entity1_name: Name of the first entity (optional if ID is provided)
            entity1_type: Type of the first entity
            entity2_id: ID of the second entity (optional if name is provided)
            entity2_name: Name of the second entity (optional if ID is provided)
            entity2_type: Type of the second entity
            episode: Episode for which to analyze the relationship
            
        Returns:
            Dictionary containing relationship analysis
        """
        self.log(f"Analyzing relationship between {entity1_name or entity1_id} and {entity2_name or entity2_id} for episode {episode}", logging.INFO)
        
        # Resolve entity IDs and names if needed
        if entity1_id is None and entity1_name and entity1_type == "character" and 'db_sqlite' in sys.modules:
            character = db_sqlite.get_character_by_name(entity1_name)
            if character:
                entity1_id = character["id"]
                entity1_name = character["name"]
        
        if entity2_id is None and entity2_name and entity2_type == "character" and 'db_sqlite' in sys.modules:
            character = db_sqlite.get_character_by_name(entity2_name)
            if character:
                entity2_id = character["id"]
                entity2_name = character["name"]
        
        # Check if we have sufficient identification for both entities
        if (entity1_id is None and entity1_name is None) or (entity2_id is None and entity2_name is None):
            self.log("Cannot analyze relationship: missing entity identifiers", logging.ERROR)
            return {
                "error": "missing_entity_identifiers",
                "message": "Both entities must have either ID or name provided"
            }
        
        # If we have the relationship analyzer, use it
        if self.relationship_analyzer:
            analysis = self.relationship_analyzer.analyze_relationship(
                entity1_id=entity1_id,
                entity1_name=entity1_name,
                entity1_type=entity1_type,
                entity2_id=entity2_id,
                entity2_name=entity2_name,
                entity2_type=entity2_type,
                episode=episode
            )
            
            # Track analysis count
            current_count = self.get_state("relationship_analysis_count") or 0
            self.update_state("relationship_analysis_count", current_count + 1)
            
            return analysis
        
        # If we don't have the analyzer, provide a simplified analysis
        return self._simplified_relationship_analysis(
            entity1_id, entity1_name, entity1_type,
            entity2_id, entity2_name, entity2_type,
            episode
        )
    
    def _simplified_relationship_analysis(self,
                                        entity1_id: Optional[int],
                                        entity1_name: Optional[str],
                                        entity1_type: str,
                                        entity2_id: Optional[int],
                                        entity2_name: Optional[str],
                                        entity2_type: str,
                                        episode: str) -> Dict[str, Any]:
        """
        Provide a simplified relationship analysis when the full analyzer is not available
        
        Args:
            entity1_id: ID of the first entity (optional)
            entity1_name: Name of the first entity (optional)
            entity1_type: Type of the first entity
            entity2_id: ID of the second entity (optional)
            entity2_name: Name of the second entity (optional)
            entity2_type: Type of the second entity
            episode: Episode for which to analyze the relationship
            
        Returns:
            Dictionary containing simplified relationship analysis
        """
        # Initialize analysis with basic information
        analysis = {
            "entity1": {
                "id": entity1_id,
                "name": entity1_name,
                "type": entity1_type
            },
            "entity2": {
                "id": entity2_id,
                "name": entity2_name,
                "type": entity2_type
            },
            "episode": episode,
            "created_at": time.time(),
            "analysis_method": "simplified",
            "relationship_dynamic": None,
            "relationship_history": [],
            "current_state": None,
            "potential_conflicts": [],
            "potential_growth": []
        }
        
        # If both entities are characters and we have database access, get relationship data
        if entity1_type == "character" and entity2_type == "character" and entity1_id and entity2_id and 'db_sqlite' in sys.modules:
            try:
                # Get character relationship
                relationship = db_sqlite.get_relationship_between_characters(entity1_id, entity2_id)
                
                if relationship:
                    analysis["relationship_dynamic"] = relationship.get("dynamic")
                
                # Try to get relationship state
                relationship_state = db_sqlite.get_relationship_current_state(
                    "character", entity1_id, "character", entity2_id
                )
                
                if relationship_state:
                    analysis["current_state"] = relationship_state
            except Exception as e:
                self.log(f"Error getting relationship data: {e}", logging.ERROR)
        
        # Track analysis count
        current_count = self.get_state("relationship_analysis_count") or 0
        self.update_state("relationship_analysis_count", current_count + 1)
        
        return analysis
    
    def analyze_narrative_psychology(self, 
                                   narrative_text: str,
                                   episode: str,
                                   focus_entities: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze the psychological aspects of a narrative
        
        Args:
            narrative_text: Text of the narrative to analyze
            episode: Episode identifier
            focus_entities: Optional list of entities to focus on
            
        Returns:
            Dictionary containing psychological analysis of the narrative
        """
        self.log(f"Analyzing narrative psychology for episode {episode}", logging.INFO)
        
        if not focus_entities:
            focus_entities = []
        
        # Initialize analysis
        analysis = {
            "episode": episode,
            "created_at": time.time(),
            "analysis_method": "simplified" if not self.character_analyzer else "full",
            "character_states": {},
            "relationship_dynamics": [],
            "psychological_themes": [],
            "emotional_arc": None,
            "character_growth_moments": []
        }
        
        # Process each focus entity
        for entity in focus_entities:
            entity_id = entity.get("id")
            entity_name = entity.get("name")
            entity_type = entity.get("type", "character")
            
            if entity_type == "character":
                # Analyze character in narrative
                if self.character_analyzer:
                    # Use full analyzer if available
                    character_state = self.character_analyzer._analyze_character_in_narrative(
                        entity_id, entity_name, narrative_text, episode
                    )
                else:
                    # Use simplified analysis
                    character_state = self._simplified_character_in_narrative(
                        entity_id, entity_name, narrative_text, episode
                    )
                
                if character_state:
                    analysis["character_states"][entity_name] = character_state
        
        # Analyze relationship dynamics if we have multiple characters
        character_names = list(analysis["character_states"].keys())
        if len(character_names) >= 2:
            # Generate relationship dynamics for each pair
            for i in range(len(character_names)):
                for j in range(i+1, len(character_names)):
                    char1 = character_names[i]
                    char2 = character_names[j]
                    
                    # Extract relationship dynamic from narrative
                    dynamic = self._extract_relationship_dynamic(char1, char2, narrative_text)
                    
                    if dynamic:
                        analysis["relationship_dynamics"].append({
                            "entities": [char1, char2],
                            "dynamic": dynamic
                        })
        
        # Extract psychological themes
        analysis["psychological_themes"] = self._extract_psychological_themes(narrative_text)
        
        # Infer emotional arc
        analysis["emotional_arc"] = self._infer_emotional_arc(narrative_text)
        
        # Identify character growth moments
        if self.character_analyzer:
            # Use full analyzer if available
            analysis["character_growth_moments"] = self.character_analyzer._identify_growth_moments(
                narrative_text, analysis["character_states"]
            )
        else:
            # Use simplified approach
            analysis["character_growth_moments"] = self._simplified_growth_moments(
                narrative_text, analysis["character_states"]
            )
        
        # Track analysis count
        current_count = self.get_state("narrative_analysis_count") or 0
        self.update_state("narrative_analysis_count", current_count + 1)
        
        return analysis
    
    def _simplified_character_in_narrative(self,
                                        character_id: Optional[int],
                                        character_name: str,
                                        narrative_text: str,
                                        episode: str) -> Optional[Dict[str, Any]]:
        """
        Simplified analysis of a character in narrative text
        
        Args:
            character_id: Character ID if available
            character_name: Character name
            narrative_text: Narrative text to analyze
            episode: Current episode
            
        Returns:
            Dictionary with character state analysis or None if character not found
        """
        # First, check if the character is actually mentioned in the narrative
        if character_name not in narrative_text:
            return None
        
        # Initialize character state
        character_state = {
            "emotional_state": None,
            "actions": [],
            "interactions": []
        }
        
        # Extract emotional keywords
        emotion_keywords = {
            "joy": ["happy", "excited", "content", "satisfied", "elated"],
            "fear": ["afraid", "anxious", "terrified", "worried", "panicked"],
            "anger": ["angry", "frustrated", "irritated", "enraged", "furious"],
            "sadness": ["sad", "depressed", "disappointed", "grieving", "melancholic"]
        }
        
        # Find emotional state
        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                # Simple check for keywords near character name
                pattern = fr'{character_name}.*{keyword}|{keyword}.*{character_name}'
                if re.search(pattern, narrative_text, re.IGNORECASE):
                    character_state["emotional_state"] = emotion
                    break
            
            if character_state["emotional_state"]:
                break
        
        # Extract actions
        action_verbs = ["said", "walked", "ran", "fought", "decided", "took", "gave", "found"]
        sentences = narrative_text.split('.')
        
        for sentence in sentences:
            if character_name in sentence:
                for verb in action_verbs:
                    if verb in sentence.lower():
                        character_state["actions"].append(sentence.strip() + '.')
                        break
        
        # Limit to top 3 actions
        character_state["actions"] = character_state["actions"][:3]
        
        # Extract interactions with other characters
        # (This is a simple approach - just looking for sentences with multiple names)
        for sentence in sentences:
            if character_name in sentence:
                other_names = []
                words = sentence.split()
                for word in words:
                    # Simple heuristic - look for capitalized words that aren't the character's name
                    if word and word[0].isupper() and word not in ["I", "The", character_name] and len(word) > 1:
                        other_names.append(word.strip(",.!?\"'()"))
                
                if other_names:
                    character_state["interactions"].append({
                        "other_entities": other_names,
                        "text": sentence.strip() + '.'
                    })
        
        # Limit to top 3 interactions
        character_state["interactions"] = character_state["interactions"][:3]
        
        return character_state
    
    def _extract_relationship_dynamic(self, char1: str, char2: str, narrative_text: str) -> Optional[str]:
        """
        Extract relationship dynamic between two characters from narrative
        
        Args:
            char1: First character name
            char2: Second character name
            narrative_text: Narrative text to analyze
            
        Returns:
            Description of relationship dynamic or None if not found
        """
        # Define relationship dynamics to look for
        dynamics = {
            "friendly": ["friend", "ally", "support", "trust", "help"],
            "hostile": ["enemy", "hostile", "threat", "attack", "fight", "argue"],
            "romantic": ["love", "romance", "intimate", "kiss", "embrace"],
            "professional": ["colleague", "partner", "work", "mission", "task"],
            "familial": ["family", "brother", "sister", "father", "mother"],
            "tense": ["tension", "suspicious", "wary", "cautious", "distrust"]
        }
        
        # Check for sentences containing both characters
        sentences = narrative_text.split('.')
        relevant_sentences = []
        
        for sentence in sentences:
            if char1 in sentence and char2 in sentence:
                relevant_sentences.append(sentence.strip())
        
        if not relevant_sentences:
            return None
        
        # Check for relationship keywords
        dynamic_scores = {dynamic: 0 for dynamic in dynamics}
        
        for sentence in relevant_sentences:
            for dynamic, keywords in dynamics.items():
                for keyword in keywords:
                    if keyword in sentence.lower():
                        dynamic_scores[dynamic] += 1
        
        # Return the highest scoring dynamic, if any
        if any(dynamic_scores.values()):
            top_dynamic = max(dynamic_scores.items(), key=lambda x: x[1])
            if top_dynamic[1] > 0:
                return top_dynamic[0]
        
        return None
    
    def _extract_psychological_themes(self, narrative_text: str) -> List[str]:
        """
        Extract psychological themes from narrative text
        
        Args:
            narrative_text: Narrative text to analyze
            
        Returns:
            List of psychological themes found in the text
        """
        # Define psychological themes to look for
        themes = {
            "identity": ["identity", "self", "who am I", "become", "change", "true self"],
            "trauma": ["trauma", "wound", "hurt", "past", "memory", "flashback"],
            "trust": ["trust", "betray", "loyalty", "faith", "doubt", "suspicious"],
            "power": ["power", "control", "dominate", "influence", "helpless", "strength"],
            "fear": ["fear", "afraid", "terror", "dread", "panic", "scared"],
            "isolation": ["alone", "lonely", "isolated", "abandoned", "outcast", "rejected"],
            "transformation": ["transform", "change", "evolve", "grow", "become", "different"]
        }
        
        # Check for theme keywords
        found_themes = []
        
        for theme, keywords in themes.items():
            for keyword in keywords:
                if keyword in narrative_text.lower():
                    found_themes.append(theme)
                    break
        
        return found_themes
    
    def _infer_emotional_arc(self, narrative_text: str) -> Optional[str]:
        """
        Infer the emotional arc of a narrative
        
        Args:
            narrative_text: Narrative text to analyze
            
        Returns:
            Description of the emotional arc or None if not identifiable
        """
        # Split into beginning, middle, and end
        text_length = len(narrative_text)
        beginning = narrative_text[:text_length//3].lower()
        middle = narrative_text[text_length//3:2*text_length//3].lower()
        end = narrative_text[2*text_length//3:].lower()
        
        # Define emotion categories
        positive_emotions = ["happy", "joy", "content", "satisfied", "hope", "optimistic", "relief"]
        negative_emotions = ["sad", "fear", "anxiety", "worried", "angry", "frustrated", "distress"]
        tense_emotions = ["tense", "suspense", "uncertain", "anxious", "nervous", "apprehensive"]
        
        # Count emotions in each section
        def count_emotions(text, emotions):
            return sum(text.count(emotion) for emotion in emotions)
        
        pos_begin = count_emotions(beginning, positive_emotions)
        neg_begin = count_emotions(beginning, negative_emotions)
        tense_begin = count_emotions(beginning, tense_emotions)
        
        pos_mid = count_emotions(middle, positive_emotions)
        neg_mid = count_emotions(middle, negative_emotions)
        tense_mid = count_emotions(middle, tense_emotions)
        
        pos_end = count_emotions(end, positive_emotions)
        neg_end = count_emotions(end, negative_emotions)
        tense_end = count_emotions(end, tense_emotions)
        
        # Determine dominant emotion for each section
        def dominant_emotion(pos, neg, tense):
            if pos > neg and pos > tense:
                return "positive"
            elif neg > pos and neg > tense:
                return "negative"
            elif tense > pos and tense > neg:
                return "tense"
            else:
                return "neutral"
        
        begin_emotion = dominant_emotion(pos_begin, neg_begin, tense_begin)
        mid_emotion = dominant_emotion(pos_mid, neg_mid, tense_mid)
        end_emotion = dominant_emotion(pos_end, neg_end, tense_end)
        
        # Identify emotional arc pattern
        pattern = (begin_emotion, mid_emotion, end_emotion)
        
        # Map patterns to arc types
        arc_types = {
            ("positive", "negative", "positive"): "Positive resolution after challenge",
            ("positive", "tense", "positive"): "Return to stability after uncertainty",
            ("negative", "negative", "positive"): "Emotional growth and improvement",
            ("negative", "tense", "positive"): "Overcoming adversity to reach happiness",
            ("positive", "positive", "negative"): "Tragic turn of events",
            ("positive", "tense", "negative"): "Deterioration after uncertainty",
            ("negative", "positive", "negative"): "Brief respite before return to difficulty",
            ("negative", "tense", "negative"): "Sustained darkness with moments of tension",
            ("tense", "negative", "positive"): "Resolution after uncertainty and challenge",
            ("tense", "positive", "negative"): "False hope dashed by grim reality"
        }
        
        return arc_types.get(pattern)
    
    def _simplified_growth_moments(self, 
                                narrative_text: str, 
                                character_states: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify character growth moments in a narrative
        
        Args:
            narrative_text: Narrative text to analyze
            character_states: Dictionary of character states
            
        Returns:
            List of character growth moments
        """
        growth_moments = []
        
        # Define growth indicators
        growth_indicators = [
            "realized", "understood", "learned", "changed", "decided", 
            "transformed", "saw differently", "accepted", "let go", 
            "for the first time", "never before", "finally"
        ]
        
        # Check for sentences with growth indicators
        sentences = narrative_text.split('.')
        
        for sentence in sentences:
            # Check if sentence contains a growth indicator
            indicator_found = False
            for indicator in growth_indicators:
                if indicator in sentence.lower():
                    indicator_found = True
                    break
            
            if not indicator_found:
                continue
            
            # Find which character is experiencing growth
            character_name = None
            for name in character_states.keys():
                if name in sentence:
                    character_name = name
                    break
            
            if not character_name:
                # Look for any capitalized name
                words = sentence.split()
                for word in words:
                    if word and word[0].isupper() and word not in ["I", "The"] and len(word) > 1:
                        character_name = word.strip(",.!?\"'()")
                        break
            
            if character_name:
                # Determine growth type
                growth_type = "insight"  # Default
                if any(term in sentence.lower() for term in ["accepted", "let go"]):
                    growth_type = "acceptance"
                elif any(term in sentence.lower() for term in ["decided", "choice", "commitment"]):
                    growth_type = "decision"
                elif any(term in sentence.lower() for term in ["changed", "transformed", "different"]):
                    growth_type = "transformation"
                
                growth_moments.append({
                    "character": character_name,
                    "type": growth_type,
                    "description": sentence.strip() + '.'
                })
        
        # Limit to top 3 growth moments
        return growth_moments[:3]
    
    def predict_character_reaction(self,
                                 character_id: Optional[int] = None,
                                 character_name: Optional[str] = None,
                                 event_description: str = "",
                                 episode: str = "S01E01") -> Dict[str, Any]:
        """
        Predict a character's reaction to an event
        
        Args:
            character_id: ID of the character (optional if name is provided)
            character_name: Name of the character (optional if ID is provided)
            event_description: Description of the event
            episode: Episode for which to predict the reaction
            
        Returns:
            Dictionary containing predicted reaction
        """
        self.log(f"Predicting reaction for {character_name or character_id} to event in {episode}", logging.INFO)
        
        # Try to get character ID if only name is provided
        if character_id is None and character_name and 'db_sqlite' in sys.modules:
            character = db_sqlite.get_character_by_name(character_name)
            if character:
                character_id = character["id"]
                character_name = character["name"]
        
        # Try to get character name if only ID is provided
        if character_name is None and character_id is not None and 'db_sqlite' in sys.modules:
            character = db_sqlite.get_character_by_id(character_id)
            if character:
                character_name = character["name"]
        
        # Check if we have either ID or name
        if character_id is None and character_name is None:
            self.log("Cannot predict reaction: no ID or name provided", logging.ERROR)
            return {
                "error": "no_character_identifier",
                "message": "Either character ID or name must be provided"
            }
        
        # If we have the character analyzer, use it
        if self.character_analyzer:
            reaction = self.character_analyzer.predict_character_reaction(
                character_id=character_id,
                character_name=character_name,
                event_description=event_description,
                current_episode=episode
            )
            return reaction
        
        # If we don't have the analyzer, provide a simplified prediction
        return self._simplified_reaction_prediction(character_id, character_name, event_description, episode)
    
    def _simplified_reaction_prediction(self,
                                      character_id: Optional[int],
                                      character_name: Optional[str],
                                      event_description: str,
                                      episode: str) -> Dict[str, Any]:
        """
        Provide a simplified prediction of character reaction when the full analyzer is not available
        
        Args:
            character_id: ID of the character (optional)
            character_name: Name of the character (optional)
            event_description: Description of the event
            episode: Episode for which to predict the reaction
            
        Returns:
            Dictionary containing simplified reaction prediction
        """
        # Initialize reaction
        reaction = {
            "character_id": character_id,
            "character_name": character_name,
            "event_description": event_description,
            "episode": episode,
            "created_at": time.time(),
            "analysis_method": "simplified",
            "emotional_reaction": None,
            "behavioral_reaction": None,
            "confidence": 0.6  # Lower confidence for simplified prediction
        }
        
        # Get character data if available
        character_data = None
        
        if 'db_sqlite' in sys.modules:
            try:
                # Try to get character data
                if character_id is not None:
                    character = db_sqlite.get_character_by_id(character_id)
                elif character_name is not None:
                    character = db_sqlite.get_character_by_name(character_name)
                else:
                    character = None
                
                if character:
                    character_data = character
                    
                    # Get entity state
                    if character_id is not None:
                        entity_states = db_sqlite.get_entity_state_at_episode(
                            "character", character_id, episode
                        )
                        
                        if entity_states:
                            # Use current emotional state
                            reaction["current_emotional_state"] = entity_states.get("emotional")
                            reaction["current_physical_state"] = entity_states.get("physical")
            except Exception as e:
                self.log(f"Error getting character data: {e}", logging.ERROR)
        
        # Extract event characteristics
        event_lower = event_description.lower()
        
        # Check for event types
        is_threat = any(term in event_lower for term in ["threat", "danger", "attack", "risk", "warning"])
        is_opportunity = any(term in event_lower for term in ["opportunity", "chance", "offer", "possibility"])
        is_loss = any(term in event_lower for term in ["lost", "loss", "gone", "failed", "missing", "broken"])
        is_social = any(term in event_lower for term in ["told", "said", "asked", "spoke", "talk", "meeting"])
        
        # Predict emotional reaction based on event type
        if is_threat:
            reaction["emotional_reaction"] = "Fear and caution; alert to potential danger"
        elif is_opportunity:
            reaction["emotional_reaction"] = "Curiosity and interest; evaluating potential benefits"
        elif is_loss:
            reaction["emotional_reaction"] = "Sadness and disappointment; processing the loss"
        elif is_social:
            reaction["emotional_reaction"] = "Attentiveness; focusing on social dynamics"
        else:
            reaction["emotional_reaction"] = "Mixed emotional response based on context"
        
        # Predict behavioral reaction based on event type
        if is_threat:
            reaction["behavioral_reaction"] = "Defensive positioning; preparing to protect self or others"
        elif is_opportunity:
            reaction["behavioral_reaction"] = "Cautious exploration; gathering more information"
        elif is_loss:
            reaction["behavioral_reaction"] = "Withdrawal or reflection; processing emotions internally"
        elif is_social:
            reaction["behavioral_reaction"] = "Engaged conversation; maintaining appropriate social responses"
        else:
            reaction["behavioral_reaction"] = "Contextual response based on immediate needs and goals"
        
        return reaction
    
    def run_test(self) -> bool:
        """
        Run tests on the Character Psychologist
        
        Returns:
            True if all tests pass, False otherwise
        """
        self.log("=== Running Character Psychologist tests ===", logging.INFO)
        
        # Import the central testing module
        try:
            from prove import TestEnvironment
            use_test_env = True
        except ImportError:
            self.log("The central testing module (prove.py) could not be imported. Running simplified tests.", logging.WARNING)
            use_test_env = False
        
        if use_test_env:
            # Run tests using TestEnvironment from prove.py
            with TestEnvironment() as env:
                all_passed = True
                
                # Define test functions
                def test_character_analysis():
                    test_character_name = "Alex"  # From the sample data
                    analysis = self.analyze_character(character_name=test_character_name)
                    
                    assert isinstance(analysis, dict)
                    assert "character_name" in analysis
                    assert analysis["character_name"] == test_character_name
                    return True
                
                def test_relationship_analysis():
                    test_char1 = "Alex"
                    test_char2 = "Emilia"
                    analysis = self.analyze_relationship(
                        entity1_name=test_char1,
                        entity2_name=test_char2
                    )
                    
                    assert isinstance(analysis, dict)
                    assert "entity1" in analysis
                    assert "entity2" in analysis
                    assert analysis["entity1"]["name"] == test_char1
                    assert analysis["entity2"]["name"] == test_char2
                    return True
                
                def test_narrative_analysis():
                    test_narrative = """
                    Alex moved cautiously through the dark corridor, heart pounding. The memory of what happened 
                    last time was still fresh. Emilia had warned him about the security systems, but he hadn't 
                    expected them to be so advanced. Now he needed to be extra careful.
                    
                    "Just a bit further," he whispered to himself, checking the small device in his hand.
                    
                    When he turned the corner, he froze. Emilia was already there, looking surprisingly calm.
                    
                    "You're late," she said with a hint of amusement in her voice.
                    
                    Alex felt a mixture of relief and suspicion. "How did you get past the guards?"
                    
                    Emilia just smiled. "I have my ways. Now, are we doing this or what?"
                    
                    For the first time, Alex realized that he might not know Emilia as well as he thought.
                    """
                    
                    focus_entities = [
                        {"name": "Alex", "type": "character"},
                        {"name": "Emilia", "type": "character"}
                    ]
                    
                    analysis = self.analyze_narrative_psychology(
                        narrative_text=test_narrative,
                        episode="S01E01",
                        focus_entities=focus_entities
                    )
                    
                    assert isinstance(analysis, dict)
                    assert "character_states" in analysis
                    assert "psychological_themes" in analysis
                    assert "Alex" in analysis["character_states"]
                    return True
                
                def test_reaction_prediction():
                    test_character = "Alex"
                    test_event = "Emilia reveals she's been working for Arasaka all along."
                    
                    reaction = self.predict_character_reaction(
                        character_name=test_character,
                        event_description=test_event
                    )
                    
                    assert isinstance(reaction, dict)
                    assert "character_name" in reaction
                    assert "emotional_reaction" in reaction
                    assert "behavioral_reaction" in reaction
                    return True
                
                # Run all tests with the testing environment
                all_passed &= env.run_test("Character Analysis", test_character_analysis)
                all_passed &= env.run_test("Relationship Analysis", test_relationship_analysis)
                all_passed &= env.run_test("Narrative Analysis", test_narrative_analysis)
                all_passed &= env.run_test("Reaction Prediction", test_reaction_prediction)
                
                self.log(f"=== Test Results: {'All Passed' if all_passed else 'Some Failed'} ===", logging.INFO)
                return all_passed
                
        else:
            # Run simplified tests without TestEnvironment
            all_passed = True
            
            # Test 1: Character analysis
            try:
                self.log("Test 1: Character analysis", logging.INFO)
                test_character_name = "Alex"  # From the sample data
                analysis = self.analyze_character(character_name=test_character_name)
                
                assert isinstance(analysis, dict)
                assert "character_name" in analysis
                assert analysis["character_name"] == test_character_name
                
                self.log("✓ Test 1 passed", logging.INFO)
            except AssertionError:
                self.log("✗ Test 1 failed", logging.ERROR)
                all_passed = False
            except Exception as e:
                self.log(f"✗ Test 1 error: {e}", logging.ERROR)
                all_passed = False
            
            # Test 2: Relationship analysis
            try:
                self.log("Test 2: Relationship analysis", logging.INFO)
                test_char1 = "Alex"
                test_char2 = "Emilia"
                analysis = self.analyze_relationship(
                    entity1_name=test_char1,
                    entity2_name=test_char2
                )
                
                assert isinstance(analysis, dict)
                assert "entity1" in analysis
                assert "entity2" in analysis
                assert analysis["entity1"]["name"] == test_char1
                assert analysis["entity2"]["name"] == test_char2
                
                self.log("✓ Test 2 passed", logging.INFO)
            except AssertionError:
                self.log("✗ Test 2 failed", logging.ERROR)
                all_passed = False
            except Exception as e:
                self.log(f"✗ Test 2 error: {e}", logging.ERROR)
                all_passed = False
            
            # Test 3: Narrative psychological analysis
            try:
                self.log("Test 3: Narrative psychological analysis", logging.INFO)
                
                test_narrative = """
                Alex moved cautiously through the dark corridor, heart pounding. The memory of what happened 
                last time was still fresh. Emilia had warned him about the security systems, but he hadn't 
                expected them to be so advanced. Now he needed to be extra careful.
                
                "Just a bit further," he whispered to himself, checking the small device in his hand.
                
                When he turned the corner, he froze. Emilia was already there, looking surprisingly calm.
                
                "You're late," she said with a hint of amusement in her voice.
                
                Alex felt a mixture of relief and suspicion. "How did you get past the guards?"
                
                Emilia just smiled. "I have my ways. Now, are we doing this or what?"
                
                For the first time, Alex realized that he might not know Emilia as well as he thought.
                """
                
                focus_entities = [
                    {"name": "Alex", "type": "character"},
                    {"name": "Emilia", "type": "character"}
                ]
                
                analysis = self.analyze_narrative_psychology(
                    narrative_text=test_narrative,
                    episode="S01E01",
                    focus_entities=focus_entities
                )
                
                assert isinstance(analysis, dict)
                assert "character_states" in analysis
                assert "psychological_themes" in analysis
                
                self.log("✓ Test 3 passed", logging.INFO)
            except AssertionError:
                self.log("✗ Test 3 failed", logging.ERROR)
                all_passed = False
            except Exception as e:
                self.log(f"✗ Test 3 error: {e}", logging.ERROR)
                all_passed = False
            
            # Test 4: Character reaction prediction
            try:
                self.log("Test 4: Character reaction prediction", logging.INFO)
                test_character = "Alex"
                test_event = "Emilia reveals she's been working for Arasaka all along."
                
                reaction = self.predict_character_reaction(
                    character_name=test_character,
                    event_description=test_event
                )
                
                assert isinstance(reaction, dict)
                assert "character_name" in reaction
                assert "emotional_reaction" in reaction
                assert "behavioral_reaction" in reaction
                
                self.log("✓ Test 4 passed", logging.INFO)
            except AssertionError:
                self.log("✗ Test 4 failed", logging.ERROR)
                all_passed = False
            except Exception as e:
                self.log(f"✗ Test 4 error: {e}", logging.ERROR)
                all_passed = False
            
            self.log(f"=== Test Results: {'All Passed' if all_passed else 'Some Failed'} ===", logging.INFO)
            return all_passed

def main():
    """
    Main entry point for running the module directly
    """
    parser = argparse.ArgumentParser(description="Psyche: Character Psychologist for Night City Stories")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--analyze-character", help="Analyze a character by name")
    parser.add_argument("--analyze-relationship", nargs=2, metavar=('CHAR1', 'CHAR2'),
                        help="Analyze relationship between two characters")
    parser.add_argument("--predict-reaction", nargs=2, metavar=('CHAR', 'EVENT'),
                        help="Predict character reaction to an event")
    parser.add_argument("--episode", default="S01E01", help="Episode for analysis (default: S01E01)")
    parser.add_argument("--output", choices=["text", "json"], default="text", 
                        help="Output format (default: text)")
    args = parser.parse_args()
    
    # Create Character Psychologist instance
    psychologist = CharacterPsychologist()
    
    if args.test:
        # Run tests
        result = psychologist.run_test()
        print(f"Test Result: {'Passed' if result else 'Failed'}")
    elif args.analyze_character:
        # Analyze character
        analysis = psychologist.analyze_character(
            character_name=args.analyze_character,
            episode=args.episode
        )
        
        if args.output == "json":
            print(json.dumps(analysis, indent=2))
        else:
            print(f"\nCharacter Analysis: {args.analyze_character}")
            print("-" * 80)
            
            if "error" in analysis:
                print(f"Error: {analysis['error']}")
                print(f"Message: {analysis['message']}")
            else:
                print(f"Character: {analysis.get('character_name', 'Unknown')}")
                print(f"Analysis method: {analysis.get('analysis_method', 'Unknown')}")
                
                if "personality_traits" in analysis and analysis["personality_traits"]:
                    print("\nPersonality Traits:")
                    for trait, score in analysis["personality_traits"].items():
                        print(f"  {trait.capitalize()}: {score:.2f}")
                
                if "core_drives" in analysis and analysis["core_drives"]:
                    print("\nCore Drives:")
                    for drive, score in analysis["core_drives"].items():
                        print(f"  {drive.capitalize()}: {score:.2f}")
                
                if "current_emotional_state" in analysis and analysis["current_emotional_state"]:
                    print(f"\nCurrent Emotional State: {analysis['current_emotional_state']}")
                
                if "current_physical_state" in analysis and analysis["current_physical_state"]:
                    print(f"Current Physical State: {analysis['current_physical_state']}")
                
                if "psychological_insights" in analysis and analysis["psychological_insights"]:
                    insights = analysis["psychological_insights"]
                    print("\nPsychological Insights:")
                    
                    if "core_conflicts" in insights and insights["core_conflicts"]:
                        print("  Core Conflicts:")
                        for conflict in insights["core_conflicts"]:
                            print(f"    - {conflict}")
                    
                    if "narrative_role" in insights and insights["narrative_role"]:
                        print(f"  Narrative Role: {insights['narrative_role']}")
            
            print("-" * 80)
    elif args.analyze_relationship:
        # Analyze relationship
        char1, char2 = args.analyze_relationship
        analysis = psychologist.analyze_relationship(
            entity1_name=char1,
            entity2_name=char2,
            episode=args.episode
        )
        
        if args.output == "json":
            print(json.dumps(analysis, indent=2))
        else:
            print(f"\nRelationship Analysis: {char1} and {char2}")
            print("-" * 80)
            
            if "error" in analysis:
                print(f"Error: {analysis['error']}")
                print(f"Message: {analysis['message']}")
            else:
                print(f"Analysis method: {analysis.get('analysis_method', 'Unknown')}")
                
                if "relationship_dynamic" in analysis and analysis["relationship_dynamic"]:
                    print(f"\nRelationship Dynamic: {analysis['relationship_dynamic']}")
                
                if "current_state" in analysis and analysis["current_state"]:
                    print("\nCurrent State:")
                    for rel_type, state in analysis["current_state"].items():
                        print(f"  {rel_type}: {state}")
                
                if "potential_conflicts" in analysis and analysis["potential_conflicts"]:
                    print("\nPotential Conflicts:")
                    for conflict in analysis["potential_conflicts"]:
                        print(f"  - {conflict}")
                
                if "potential_growth" in analysis and analysis["potential_growth"]:
                    print("\nPotential Growth Areas:")
                    for growth in analysis["potential_growth"]:
                        print(f"  - {growth}")
            
            print("-" * 80)
    elif args.predict_reaction:
        # Predict character reaction
        char, event = args.predict_reaction
        reaction = psychologist.predict_character_reaction(
            character_name=char,
            event_description=event,
            episode=args.episode
        )
        
        if args.output == "json":
            print(json.dumps(reaction, indent=2))
        else:
            print(f"\nPredicted Reaction: {char} to event")
            print("-" * 80)
            print(f"Event: {event}")
            
            if "error" in reaction:
                print(f"Error: {reaction['error']}")
                print(f"Message: {reaction['message']}")
            else:
                print(f"\nEmotional Reaction: {reaction.get('emotional_reaction', 'Unknown')}")
                print(f"Behavioral Reaction: {reaction.get('behavioral_reaction', 'Unknown')}")
                
                if "cognitive_reaction" in reaction and reaction["cognitive_reaction"]:
                    print(f"Cognitive Reaction: {reaction['cognitive_reaction']}")
                
                if "long_term_impact" in reaction and reaction["long_term_impact"]:
                    print(f"Long-term Impact: {reaction['long_term_impact']}")
                
                print(f"\nConfidence: {reaction.get('confidence', 0.0):.2f}")
            
            print("-" * 80)
    else:
        # Show help
        parser.print_help()

if __name__ == "__main__":
    main()