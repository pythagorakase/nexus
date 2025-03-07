#!/usr/bin/env python3
"""
psyche_character.py: Character Analysis Module for Night City Stories

This module provides functionality for analyzing individual character psychology as part of 
the Character Psychologist agent. It handles personality trait extraction, emotional state 
tracking, psychological profile creation, character growth analysis, and psychological 
consistency checking.

The CharacterAnalyzer class serves as the core component, providing methods to create and
manage detailed psychological profiles for characters, analyze their emotional states and
motivations, and predict their reactions to events based on their established traits.

Usage:
    # Import and use within the main psyche.py module
    from psyche_character import CharacterAnalyzer, PERSONALITY_TRAITS, EMOTIONS, MOTIVATIONS
    
    character_analyzer = CharacterAnalyzer()
    profile = character_analyzer.analyze_character(character_id=1, character_name="Alex")
"""

import os
import sys
import json
import logging
import time
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any, Set

# Try to import required modules
try:
    # Import configuration manager
    import config_manager as config
    
    # Import database modules
    import db_sqlite
    
    # Import memory manager
    import memnon
    
except ImportError as e:
    print(f"Warning: Failed to import a required module: {e}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("psyche_character.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("psyche_character")

# Core personality traits
PERSONALITY_TRAITS = {
    "openness": {
        "description": "Openness to experience, curiosity, creativity",
        "high": "Imaginative, innovative, seeks new experiences",
        "low": "Conventional, practical, prefers routine"
    },
    "conscientiousness": {
        "description": "Organization, responsibility, self-discipline",
        "high": "Methodical, dependable, goal-oriented",
        "low": "Spontaneous, disorganized, present-focused"
    },
    "extraversion": {
        "description": "Energy directed outward, sociability",
        "high": "Outgoing, energetic, seeks social stimulation",
        "low": "Reserved, reflective, comfortable alone"
    },
    "agreeableness": {
        "description": "Compassion, cooperativeness, trust in others",
        "high": "Empathetic, trusting, values harmony",
        "low": "Competitive, skeptical, prioritizes self-interest"
    },
    "neuroticism": {
        "description": "Emotional instability, tendency to experience negative emotions",
        "high": "Sensitive, anxious, reactive to stress",
        "low": "Resilient, calm, emotionally stable"
    }
}

# Core emotional categories
EMOTIONS = {
    "joy": ["happy", "excited", "content", "satisfied", "elated"],
    "fear": ["afraid", "anxious", "terrified", "worried", "panicked"],
    "anger": ["angry", "frustrated", "irritated", "enraged", "furious"],
    "sadness": ["sad", "depressed", "disappointed", "grieving", "melancholic"],
    "disgust": ["disgusted", "repulsed", "appalled", "disdainful", "contemptuous"],
    "surprise": ["surprised", "shocked", "amazed", "astonished", "startled"],
    "trust": ["trusting", "accepting", "faithful", "confident", "secure"],
    "anticipation": ["expectant", "hopeful", "excited", "eager", "prepared"]
}

# Core motivational drives
MOTIVATIONS = {
    "survival": ["safety", "security", "stability", "health"],
    "power": ["control", "influence", "status", "dominance"],
    "achievement": ["competence", "mastery", "success", "recognition"],
    "affiliation": ["belonging", "connection", "intimacy", "acceptance"],
    "identity": ["authenticity", "self-expression", "uniqueness", "meaning"],
    "ideology": ["justice", "principles", "ethics", "beliefs"]
}

class CharacterAnalyzer:
    """
    Character Analyzer for psychological assessment and profiling of individual characters
    """
    
    def __init__(self, settings: Dict[str, Any] = None):
        """
        Initialize the Character Analyzer
        
        Args:
            settings: Optional settings dictionary
        """
        # Initialize settings
        self.settings = {}
        if settings:
            self.settings.update(settings)
        elif config:
            # Try to load from config_manager
            psyche_config = config.get_section("psyche")
            if psyche_config:
                self.settings.update(psyche_config)
        
        # Initialize cache for character profiles
        self.character_profiles = {}
        
        # Initialize counter for psychological analyses
        self.analysis_count = 0
        
        logger.info("Character Analyzer initialized")
    
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
        logger.info(f"Analyzing character: {character_name or character_id} for episode {episode}")
        
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
            logger.error("Cannot analyze character: no ID or name provided")
            return {
                "error": "no_character_identifier",
                "message": "Either character ID or name must be provided"
            }
        
        # Check if we have a cached profile
        profile_key = f"{character_id}_{character_name}"
        if profile_key in self.character_profiles:
            # Get cached profile
            profile = self.character_profiles[profile_key]
            logger.info(f"Using cached profile for {character_name or character_id}")
        else:
            # Create a new profile
            profile = self._create_character_profile(character_id, character_name)
            self.character_profiles[profile_key] = profile
            logger.info(f"Created new profile for {character_name or character_id}")
        
        # Get character state at the specified episode
        try:
            if 'db_sqlite' in sys.modules and character_id is not None:
                # Get physical and emotional states
                entity_states = db_sqlite.get_entity_state_at_episode(
                    "character", character_id, episode
                )
                
                # Update profile with current states
                if entity_states:
                    emotional_state = entity_states.get("emotional")
                    physical_state = entity_states.get("physical")
                    knowledge_state = entity_states.get("knowledge")
                    
                    # Merge states into profile
                    if emotional_state:
                        profile["current_emotional_state"] = emotional_state
                    
                    if physical_state:
                        profile["current_physical_state"] = physical_state
                    
                    if knowledge_state:
                        profile["current_knowledge"] = knowledge_state
        except Exception as e:
            logger.error(f"Error getting character states: {e}")
        
        # Get character memory for context
        memory_context = ""
        try:
            if 'memnon' in sys.modules and character_name:
                # Search for character mentions in memory
                memory_chunks = memnon.get_memory_for_context(
                    f"Information about {character_name}'s background, personality, and history",
                    top_k=5
                )
                
                # Extract text from chunks
                for chunk in memory_chunks:
                    chunk_text = chunk.get("text", "")
                    if chunk_text:
                        memory_context += chunk_text + "\n\n"
                
                # Add memory context to profile
                profile["memory_context"] = memory_context
        except Exception as e:
            logger.error(f"Error getting character memory: {e}")
        
        # Enhance the profile with psychological insights
        psychological_insights = self._generate_psychological_insights(profile)
        profile["psychological_insights"] = psychological_insights
        
        # Track analysis count
        self.analysis_count += 1
        
        return profile
    
    def _create_character_profile(self, 
                                character_id: Optional[int] = None, 
                                character_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a baseline psychological profile for a character
        
        Args:
            character_id: ID of the character (optional)
            character_name: Name of the character (optional)
            
        Returns:
            Dictionary containing the character's psychological profile
        """
        # Initialize profile with basic information
        profile = {
            "character_id": character_id,
            "character_name": character_name,
            "created_at": time.time(),
            "updated_at": time.time(),
            "personality_traits": {},
            "core_drives": {},
            "psychological_vulnerabilities": [],
            "emotional_patterns": {},
            "decision_making_style": None,
            "defense_mechanisms": [],
            "interpersonal_style": None,
            "character_development": [],
            "current_emotional_state": None,
            "current_physical_state": None,
            "current_knowledge": None,
            "memory_context": ""
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
                    description = character.get("description", "")
                    personality = character.get("personality", "")
                    
                    # Extract personality traits
                    profile["personality_traits"] = self._extract_personality_traits(
                        description, personality
                    )
                    
                    # Extract core drives
                    profile["core_drives"] = self._extract_core_drives(
                        description, personality
                    )
                    
                    # Extract vulnerabilities
                    profile["psychological_vulnerabilities"] = self._extract_vulnerabilities(
                        description, personality
                    )
                    
                    # Infer interpersonal style
                    profile["interpersonal_style"] = self._infer_interpersonal_style(
                        profile["personality_traits"]
                    )
                    
                    # Infer decision making style
                    profile["decision_making_style"] = self._infer_decision_making_style(
                        profile["personality_traits"], profile["core_drives"]
                    )
            except Exception as e:
                logger.error(f"Error creating profile from database: {e}")
        
        return profile
    
    def _extract_personality_traits(self, description: str, personality: str) -> Dict[str, float]:
        """
        Extract personality traits from character description and personality
        
        Args:
            description: Character description text
            personality: Character personality text
            
        Returns:
            Dictionary with personality trait dimensions and scores
        """
        # This would ideally use LLM analysis
        # For now, we'll use some simple keyword matching
        
        combined_text = (description + " " + personality).lower()
        
        traits = {}
        
        # Openness
        openness_keywords = {
            "high": ["creative", "curious", "imaginative", "innovative", "artistic", "open-minded"],
            "low": ["conventional", "traditional", "practical", "routine", "conservative"]
        }
        
        # Conscientiousness
        conscientiousness_keywords = {
            "high": ["organized", "disciplined", "responsible", "reliable", "methodical", "careful"],
            "low": ["spontaneous", "careless", "disorganized", "impulsive", "unreliable"]
        }
        
        # Extraversion
        extraversion_keywords = {
            "high": ["outgoing", "social", "energetic", "talkative", "assertive", "gregarious"],
            "low": ["quiet", "reserved", "solitary", "reflective", "introverted", "private"]
        }
        
        # Agreeableness
        agreeableness_keywords = {
            "high": ["kind", "compassionate", "empathetic", "cooperative", "trusting", "helpful"],
            "low": ["critical", "competitive", "suspicious", "challenging", "detached", "callous"]
        }
        
        # Neuroticism
        neuroticism_keywords = {
            "high": ["anxious", "moody", "stressed", "emotional", "worried", "sensitive"],
            "low": ["calm", "stable", "composed", "resilient", "steady", "relaxed"]
        }
        
        # Calculate trait scores based on keyword matches
        traits["openness"] = self._calculate_trait_score(combined_text, openness_keywords)
        traits["conscientiousness"] = self._calculate_trait_score(combined_text, conscientiousness_keywords)
        traits["extraversion"] = self._calculate_trait_score(combined_text, extraversion_keywords)
        traits["agreeableness"] = self._calculate_trait_score(combined_text, agreeableness_keywords)
        traits["neuroticism"] = self._calculate_trait_score(combined_text, neuroticism_keywords)
        
        return traits
    
    def _calculate_trait_score(self, text: str, keywords: Dict[str, List[str]]) -> float:
        """
        Calculate trait score based on keyword presence
        
        Args:
            text: Text to analyze
            keywords: Dictionary with "high" and "low" keywords
            
        Returns:
            Trait score from 0.0 to 1.0
        """
        high_count = 0
        low_count = 0
        
        # Count high keywords
        for keyword in keywords["high"]:
            if keyword in text:
                high_count += 1
        
        # Count low keywords
        for keyword in keywords["low"]:
            if keyword in text:
                low_count += 1
        
        # If no keywords found, return middle score
        if high_count == 0 and low_count == 0:
            return 0.5
        
        # Calculate score (0.0 to 1.0)
        total = high_count + low_count
        if total > 0:
            return min(1.0, max(0.0, 0.5 + 0.5 * (high_count - low_count) / total))
        else:
            return 0.5
    
    def _extract_core_drives(self, description: str, personality: str) -> Dict[str, float]:
        """
        Extract core motivational drives from character description and personality
        
        Args:
            description: Character description text
            personality: Character personality text
            
        Returns:
            Dictionary with motivational drives and their strengths
        """
        combined_text = (description + " " + personality).lower()
        
        drives = {}
        
        # Define keywords for each drive
        drive_keywords = {
            "survival": ["survival", "safety", "security", "protect", "defend", "risk", "danger", "threat"],
            "power": ["power", "control", "influence", "status", "authority", "dominance", "recognition"],
            "achievement": ["achieve", "accomplish", "success", "excel", "competence", "mastery", "skill"],
            "affiliation": ["connection", "relationship", "belonging", "love", "friendship", "loyalty", "trust"],
            "identity": ["identity", "self", "authentic", "true", "meaning", "purpose", "values", "principles"],
            "ideology": ["belief", "ideal", "cause", "justice", "right", "wrong", "ethics", "moral"]
        }
        
        # Calculate drive scores
        for drive, keywords in drive_keywords.items():
            count = 0
            for keyword in keywords:
                if keyword in combined_text:
                    count += 1
            
            # Scale score based on keyword count
            drives[drive] = min(1.0, count / (len(keywords) / 2))
        
        return drives
    
    def _extract_vulnerabilities(self, description: str, personality: str) -> List[str]:
        """
        Extract psychological vulnerabilities from character description and personality
        
        Args:
            description: Character description text
            personality: Character personality text
            
        Returns:
            List of identified psychological vulnerabilities
        """
        combined_text = (description + " " + personality).lower()
        
        vulnerabilities = []
        
        # Define vulnerability keywords
        vulnerability_indicators = {
            "trauma": ["trauma", "traumatic", "ptsd", "haunted by", "nightmares", "flashbacks"],
            "abandonment": ["abandoned", "left behind", "alone", "orphaned", "rejected", "forsaken"],
            "betrayal": ["betrayed", "deceived", "cheated", "backstabbed", "trust issues"],
            "inadequacy": ["inadequate", "not enough", "failure", "imposter", "unworthy"],
            "loss_of_control": ["control", "helpless", "powerless", "trapped", "cornered"],
            "rejection": ["rejected", "outcast", "unwanted", "unloved", "isolation", "loneliness"],
            "shame": ["shame", "guilt", "embarrassment", "dishonor", "humiliation"]
        }
        
        # Check for each vulnerability
        for vulnerability, keywords in vulnerability_indicators.items():
            for keyword in keywords:
                if keyword in combined_text:
                    vulnerabilities.append(vulnerability)
                    break  # One match is enough to identify this vulnerability
        
        return vulnerabilities
    
    def _infer_interpersonal_style(self, personality_traits: Dict[str, float]) -> str:
        """
        Infer interpersonal style from personality traits
        
        Args:
            personality_traits: Dictionary of personality trait scores
            
        Returns:
            Description of interpersonal style
        """
        extraversion = personality_traits.get("extraversion", 0.5)
        agreeableness = personality_traits.get("agreeableness", 0.5)
        
        # Define interpersonal styles based on extraversion and agreeableness
        if extraversion > 0.7 and agreeableness > 0.7:
            return "Warm and engaging; builds rapport easily and forms genuine connections"
        elif extraversion > 0.7 and agreeableness < 0.3:
            return "Dominant and challenging; takes charge in social situations but may create tension"
        elif extraversion < 0.3 and agreeableness > 0.7:
            return "Quiet and supportive; prefers deep one-on-one connections and harmony"
        elif extraversion < 0.3 and agreeableness < 0.3:
            return "Detached and analytical; maintains emotional distance and values independence"
        elif extraversion > 0.6:
            return "Outgoing and socially confident; thrives in group settings"
        elif agreeableness > 0.6:
            return "Cooperative and empathetic; prioritizes others' needs and group harmony"
        elif extraversion < 0.4:
            return "Reserved and selective; conserves social energy for meaningful interactions"
        elif agreeableness < 0.4:
            return "Autonomous and direct; values honesty over social niceties"
        else:
            return "Adaptable and balanced; adjusts interpersonal approach based on context"
    
    def _infer_decision_making_style(self, 
                                   personality_traits: Dict[str, float],
                                   core_drives: Dict[str, float]) -> str:
        """
        Infer decision-making style from personality traits and core drives
        
        Args:
            personality_traits: Dictionary of personality trait scores
            core_drives: Dictionary of motivational drive scores
            
        Returns:
            Description of decision-making style
        """
        openness = personality_traits.get("openness", 0.5)
        conscientiousness = personality_traits.get("conscientiousness", 0.5)
        neuroticism = personality_traits.get("neuroticism", 0.5)
        
        # Identify strongest drive
        strongest_drive = max(core_drives.items(), key=lambda x: x[1]) if core_drives else ("", 0)
        
        # Define decision-making styles
        if conscientiousness > 0.7:
            if openness > 0.6:
                return "Methodical yet innovative; carefully considers options while remaining open to creative solutions"
            else:
                return "Systematic and thorough; relies on proven approaches and careful analysis"
        elif openness > 0.7:
            if neuroticism > 0.6:
                return "Creative but cautious; explores novel options while anticipating potential problems"
            else:
                return "Intuitive and experimental; follows instincts and embraces novel approaches"
        elif neuroticism > 0.7:
            return "Risk-averse and cautious; focuses on avoiding negative outcomes"
        
        # Consider core drives if no clear style emerged
        if strongest_drive[0] == "survival" and strongest_drive[1] > 0.6:
            return "Safety-oriented; prioritizes security and risk mitigation in decisions"
        elif strongest_drive[0] == "power" and strongest_drive[1] > 0.6:
            return "Strategic and outcome-focused; makes decisions that maximize control and influence"
        elif strongest_drive[0] == "achievement" and strongest_drive[1] > 0.6:
            return "Results-driven; focuses on efficiency and measurable success"
        elif strongest_drive[0] == "affiliation" and strongest_drive[1] > 0.6:
            return "Collaborative; considers impact on relationships and seeks consensus"
        elif strongest_drive[0] == "identity" and strongest_drive[1] > 0.6:
            return "Values-aligned; makes decisions that reinforce personal identity and authenticity"
        elif strongest_drive[0] == "ideology" and strongest_drive[1] > 0.6:
            return "Principle-based; evaluates options against a consistent moral framework"
        
        # Default if no clear pattern
        return "Balanced and adaptable; adjusts decision approach based on context"
    
    def _generate_psychological_insights(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate psychological insights from character profile
        
        Args:
            profile: Character psychological profile
            
        Returns:
            Dictionary with psychological insights
        """
        insights = {
            "core_conflicts": [],
            "behavioral_patterns": [],
            "growth_potential": [],
            "blind_spots": [],
            "narrative_role": None
        }
        
        # Extract traits and drives for analysis
        personality = profile.get("personality_traits", {})
        drives = profile.get("core_drives", {})
        vulnerabilities = profile.get("psychological_vulnerabilities", [])
        emotional_state = profile.get("current_emotional_state")
        
        # Identify core psychological conflicts
        if personality and drives:
            # Check for conflict between traits and drives
            if personality.get("openness", 0.5) > 0.7 and drives.get("survival", 0) > 0.7:
                insights["core_conflicts"].append(
                    "Internal tension between desire for new experiences and need for safety"
                )
            
            if personality.get("agreeableness", 0.5) > 0.7 and drives.get("power", 0) > 0.7:
                insights["core_conflicts"].append(
                    "Conflict between cooperative nature and desire for control and influence"
                )
            
            if personality.get("extraversion", 0.5) < 0.3 and drives.get("affiliation", 0) > 0.7:
                insights["core_conflicts"].append(
                    "Struggle between need for solitude and deep desire for connection"
                )
        
        # Identify behavioral patterns
        if personality:
            if personality.get("neuroticism", 0.5) > 0.7 and personality.get("conscientiousness", 0.5) > 0.7:
                insights["behavioral_patterns"].append(
                    "Tendency to overplan and create excessive structure to manage anxiety"
                )
            
            if personality.get("openness", 0.5) > 0.7 and personality.get("extraversion", 0.5) > 0.7:
                insights["behavioral_patterns"].append(
                    "Pattern of seeking novel social experiences and becoming quickly bored with routine"
                )
        
        # Identify growth potential
        if vulnerabilities and personality:
            for vulnerability in vulnerabilities:
                if vulnerability == "abandonment" and drives.get("affiliation", 0) > 0.6:
                    insights["growth_potential"].append(
                        "Potential to transform abandonment fears into capacity for deep, authentic connection"
                    )
                elif vulnerability == "betrayal" and personality.get("openness", 0.5) > 0.6:
                    insights["growth_potential"].append(
                        "Ability to develop nuanced trust through openness to new perspectives on past betrayals"
                    )
        
        # Identify blind spots
        if personality:
            if personality.get("agreeableness", 0.5) > 0.8:
                insights["blind_spots"].append(
                    "May overlook others' manipulation due to assuming positive intent"
                )
            
            if personality.get("conscientiousness", 0.5) > 0.8:
                insights["blind_spots"].append(
                    "May miss spontaneous opportunities due to rigid adherence to plans"
                )
            
            if personality.get("extraversion", 0.5) < 0.2:
                insights["blind_spots"].append(
                    "May underestimate the importance of social alliances and networking"
                )
        
        # Determine narrative role
        if personality and drives and vulnerabilities:
            # This is a simplified approach - a full implementation would use more sophisticated analysis
            openness = personality.get("openness", 0.5)
            conscientiousness = personality.get("conscientiousness", 0.5)
            extraversion = personality.get("extraversion", 0.5)
            agreeableness = personality.get("agreeableness", 0.5)
            neuroticism = personality.get("neuroticism", 0.5)
            
            # Identify dominant drives
            dominant_drives = [k for k, v in drives.items() if v > 0.7]
            
            # Determine narrative role based on traits and drives
            if "power" in dominant_drives and agreeableness < 0.4 and conscientiousness > 0.6:
                insights["narrative_role"] = "Power-driven antagonist or ambitious anti-hero"
            elif "ideology" in dominant_drives and openness > 0.7 and neuroticism < 0.4:
                insights["narrative_role"] = "Visionary revolutionary or principled mentor"
            elif "achievement" in dominant_drives and conscientiousness > 0.7:
                insights["narrative_role"] = "Determined problem-solver or relentless pursuer"
            elif "affiliation" in dominant_drives and agreeableness > 0.7:
                insights["narrative_role"] = "Loyal ally or relationship bridge-builder"
            elif "survival" in dominant_drives and neuroticism > 0.7:
                insights["narrative_role"] = "Vigilant protector or paranoid survivor"
            elif "identity" in dominant_drives and openness > 0.6:
                insights["narrative_role"] = "Self-discovery seeker or identity-in-crisis"
            else:
                insights["narrative_role"] = "Complex supporting character with situational significance"
        
        return insights
    
    def predict_character_reaction(self, 
                                 character_id: Optional[int], 
                                 character_name: Optional[str],
                                 event_description: str,
                                 current_episode: str) -> Dict[str, Any]:
        """
        Predict a character's reaction to an event based on their psychological profile
        
        Args:
            character_id: ID of the character (optional if name is provided)
            character_name: Name of the character (optional if ID is provided)
            event_description: Description of the event to react to
            current_episode: Current episode identifier
            
        Returns:
            Dictionary containing predicted reaction
        """
        logger.info(f"Predicting reaction for {character_name or character_id} to event in {current_episode}")
        
        # Get character profile
        profile = self.analyze_character(character_id, character_name, current_episode)
        
        # If we couldn't get a profile, return an error
        if not profile or "error" in profile:
            return {
                "error": "could_not_get_profile",
                "message": f"Could not retrieve psychological profile for {character_name or character_id}"
            }
        
        # Initialize reaction
        reaction = {
            "character_name": profile["character_name"],
            "event_description": event_description,
            "emotional_reaction": None,
            "cognitive_reaction": None,
            "behavioral_reaction": None,
            "long_term_impact": None,
            "confidence": 0.7  # Default confidence
        }
        
        # Extract key elements from profile
        personality = profile.get("personality_traits", {})
        drives = profile.get("core_drives", {})
        vulnerabilities = profile.get("psychological_vulnerabilities", [])
        current_emotion = profile.get("current_emotional_state")
        decision_style = profile.get("decision_making_style")
        
        # Predict emotional reaction
        reaction["emotional_reaction"] = self._predict_emotional_reaction(
            event_description, personality, drives, vulnerabilities, current_emotion
        )
        
        # Predict cognitive reaction
        reaction["cognitive_reaction"] = self._predict_cognitive_reaction(
            event_description, personality, drives, decision_style
        )
        
        # Predict behavioral reaction
        reaction["behavioral_reaction"] = self._predict_behavioral_reaction(
            event_description, personality, drives, 
            reaction["emotional_reaction"], reaction["cognitive_reaction"]
        )
        
        # Predict long-term impact
        reaction["long_term_impact"] = self._predict_long_term_impact(
            event_description, personality, vulnerabilities,
            reaction["emotional_reaction"], reaction["cognitive_reaction"]
        )
        
        return reaction
    
    def _predict_emotional_reaction(self, 
                                 event_description: str,
                                 personality: Dict[str, float],
                                 drives: Dict[str, float],
                                 vulnerabilities: List[str],
                                 current_emotion: Optional[str]) -> str:
        """
        Predict a character's emotional reaction to an event
        
        Args:
            event_description: Description of the event
            personality: Character's personality traits
            drives: Character's core drives
            vulnerabilities: Character's psychological vulnerabilities
            current_emotion: Character's current emotional state
            
        Returns:
            Description of predicted emotional reaction
        """
        # This is a simplified implementation - a full version would use LLM for prediction
        
        # Extract event characteristics
        event_lower = event_description.lower()
        
        # Check for event types
        is_threat = any(term in event_lower for term in ["threat", "danger", "attack", "risk", "warning"])
        is_opportunity = any(term in event_lower for term in ["opportunity", "chance", "offer", "possibility"])
        is_loss = any(term in event_lower for term in ["lost", "loss", "gone", "failed", "missing", "broken"])
        is_social = any(term in event_lower for term in ["told", "said", "asked", "spoke", "talk", "meeting"])
        is_surprising = any(term in event_lower for term in ["surprise", "unexpected", "suddenly", "shock"])
        
        # Get personality factors
        neuroticism = personality.get("neuroticism", 0.5)
        extraversion = personality.get("extraversion", 0.5)
        openness = personality.get("openness", 0.5)
        
        # Predict dominant emotion based on event and personality
        if is_threat:
            if neuroticism > 0.7:
                return "Intense fear and anxiety; the threat triggers deep insecurity and catastrophic thinking"
            elif drives.get("power", 0) > 0.7:
                return "Defensive anger; perceives the threat as a challenge to control and status"
            else:
                return "Cautious concern; alert to the danger but maintaining composure"
                
        elif is_loss:
            if "abandonment" in vulnerabilities or "betrayal" in vulnerabilities:
                return "Deep grief tinged with abandonment anxiety; the loss reopens old emotional wounds"
            elif neuroticism > 0.6:
                return "Profound sadness and despondency; struggles to see beyond the immediate loss"
            else:
                return "Measured sadness; feels the loss while maintaining perspective"
                
        elif is_opportunity:
            if openness > 0.7:
                return "Excited curiosity; energized by the possibilities of something new"
            elif neuroticism > 0.7:
                return "Anxious hope; wants to believe in the opportunity but fears disappointment"
            else:
                return "Cautious optimism; interested but evaluating potential risks"
                
        elif is_social:
            if extraversion > 0.7:
                return "Engaged interest; socially energized and emotionally responsive"
            elif extraversion < 0.3:
                return "Mild discomfort; somewhat drained by the social demands"
            else:
                return "Neutral attentiveness; present but not strongly emotionally affected"
                
        elif is_surprising:
            if neuroticism > 0.7:
                return "Startled alarm; surprise triggers immediate anxiety response"
            elif openness > 0.7:
                return "Intrigued fascination; quickly shifts from surprise to curiosity"
            else:
                return "Momentary surprise; quickly returns to emotional baseline"
        
        # Default response if no specific pattern detected
        return "Mixed emotional response; depends on specifics and prior context"
    
    def _predict_cognitive_reaction(self, 
                                  event_description: str,
                                  personality: Dict[str, float],
                                  drives: Dict[str, float],
                                  decision_style: Optional[str]) -> str:
        """
        Predict a character's cognitive reaction to an event
        
        Args:
            event_description: Description of the event
            personality: Character's personality traits
            drives: Character's core drives
            decision_style: Character's decision-making style
            
        Returns:
            Description of predicted cognitive reaction
        """
        # Extract event characteristics
        event_lower = event_description.lower()
        
        # Get personality factors
        openness = personality.get("openness", 0.5)
        conscientiousness = personality.get("conscientiousness", 0.5)
        
        # Check for event types
        is_problem = any(term in event_lower for term in ["problem", "issue", "challenge", "obstacle", "difficulty"])
        is_information = any(term in event_lower for term in ["information", "news", "learn", "discover", "revelation"])
        is_choice = any(term in event_lower for term in ["choice", "decision", "option", "choose", "select"])
        
        # Predict cognitive reaction based on event type and personality
        if is_problem:
            if conscientiousness > 0.7:
                return "Systematic analysis; breaks down the problem into manageable components"
            elif openness > 0.7:
                return "Creative problem-solving; considers unconventional approaches and solutions"
            elif drives.get("achievement", 0) > 0.7:
                return "Solution-focused thinking; immediately begins formulating response strategies"
            else:
                return "Evaluative assessment; considers the problem's significance and required effort"
                
        elif is_information:
            if openness > 0.7:
                return "Integrative processing; connects new information to existing knowledge and possibilities"
            elif drives.get("power", 0) > 0.7:
                return "Strategic evaluation; assesses how the information can be leveraged for advantage"
            elif drives.get("ideology", 0) > 0.7:
                return "Value-based interpretation; filters information through existing belief system"
            else:
                return "Factual processing; focuses on understanding the concrete implications"
                
        elif is_choice:
            if conscientiousness > 0.7:
                return "Methodical consideration; carefully weighs pros and cons of each option"
            elif drives.get("survival", 0) > 0.7:
                return "Risk assessment; primarily focuses on potential dangers and safeguards"
            elif drives.get("affiliation", 0) > 0.7:
                return "Relational thinking; considers how each option affects important relationships"
            else:
                return "Practical evaluation; focuses on feasibility and expected outcomes"
        
        # Default response if no specific pattern detected
        return "Contextual assessment; processes the information based on current goals and needs"
    
    def _predict_behavioral_reaction(self, 
                                   event_description: str,
                                   personality: Dict[str, float],
                                   drives: Dict[str, float],
                                   emotional_reaction: Optional[str],
                                   cognitive_reaction: Optional[str]) -> str:
        """
        Predict a character's behavioral reaction to an event
        
        Args:
            event_description: Description of the event
            personality: Character's personality traits
            drives: Character's core drives
            emotional_reaction: Predicted emotional reaction
            cognitive_reaction: Predicted cognitive reaction
            
        Returns:
            Description of predicted behavioral reaction
        """
        # Get personality factors
        extraversion = personality.get("extraversion", 0.5)
        conscientiousness = personality.get("conscientiousness", 0.5)
        neuroticism = personality.get("neuroticism", 0.5)
        
        # Extract emotional components
        is_fearful = emotional_reaction and any(term in emotional_reaction.lower() 
                                               for term in ["fear", "anxious", "alarm", "dread"])
        is_angry = emotional_reaction and any(term in emotional_reaction.lower() 
                                            for term in ["anger", "frustrated", "defensive"])
        is_excited = emotional_reaction and any(term in emotional_reaction.lower() 
                                              for term in ["excited", "curious", "intrigued"])
        
        # Extract cognitive components
        is_analytical = cognitive_reaction and any(term in cognitive_reaction.lower() 
                                                 for term in ["analysis", "systematic", "evaluative", "assessment"])
        is_creative = cognitive_reaction and any(term in cognitive_reaction.lower() 
                                               for term in ["creative", "unconventional", "possibilities"])
        
        # Predict behavioral response pattern
        if is_fearful:
            if neuroticism > 0.7:
                return "Avoidance or withdrawal; creates distance from the threatening stimulus"
            elif drives.get("power", 0) > 0.7:
                return "Defensive control; attempts to manage the situation through asserting authority"
            elif conscientiousness > 0.7:
                return "Cautious preparation; methodically prepares for potential negative outcomes"
            else:
                return "Vigilant observation; maintains awareness while gathering more information"
                
        elif is_angry:
            if extraversion > 0.7:
                return "Direct confrontation; addresses the source of frustration immediately"
            elif conscientiousness > 0.7:
                return "Controlled expression; channels frustration into structured problem-solving"
            else:
                return "Internal processing; contains visible reaction while processing response"
                
        elif is_excited:
            if extraversion > 0.7:
                return "Enthusiastic engagement; actively explores and pursues the opportunity"
            elif is_analytical:
                return "Measured investigation; systematically evaluates the exciting possibility"
            else:
                return "Quiet interest; maintains outward calm while internally engaging with the stimulus"
        
        # If no clear emotional pattern, default based on personality
        if extraversion > 0.7:
            return "Active engagement; approaches the situation directly with visible energy"
        elif conscientiousness > 0.7:
            return "Methodical response; takes carefully planned steps based on reasoned analysis"
        elif neuroticism > 0.7:
            return "Cautious reaction; proceeds carefully while monitoring for potential issues"
        else:
            return "Measured response; reacts appropriately to the situation without significant emotional display"
    
    def _predict_long_term_impact(self, 
                                event_description: str,
                                personality: Dict[str, float],
                                vulnerabilities: List[str],
                                emotional_reaction: Optional[str],
                                cognitive_reaction: Optional[str]) -> str:
        """
        Predict the long-term impact of an event on a character
        
        Args:
            event_description: Description of the event
            personality: Character's personality traits
            vulnerabilities: Character's psychological vulnerabilities
            emotional_reaction: Predicted emotional reaction
            cognitive_reaction: Predicted cognitive reaction
            
        Returns:
            Description of predicted long-term impact
        """
        # Extract event characteristics
        event_lower = event_description.lower()
        
        # Check for event significance
        is_traumatic = any(term in event_lower for term in ["traumatic", "devastating", "horrific", "terrifying"])
        is_transformative = any(term in event_lower for term in ["life-changing", "transformative", "profound", "revelation"])
        is_challenging = any(term in event_lower for term in ["challenging", "difficult", "hardship", "struggle"])
        
        # Get personality factors
        neuroticism = personality.get("neuroticism", 0.5)
        openness = personality.get("openness", 0.5)
        
        # Predict long-term impact
        if is_traumatic:
            if neuroticism > 0.7:
                return "Potential trauma response; may develop persistent anxiety or avoidance patterns"
            elif "trauma" in vulnerabilities:
                return "Reactivation of previous trauma; could intensify existing psychological wounds"
            elif openness > 0.7:
                return "Post-traumatic growth potential; may eventually integrate experience into expanded worldview"
            else:
                return "Gradual adjustment; will process the experience over time with potential resilience"
                
        elif is_transformative:
            if openness > 0.7:
                return "Significant worldview shift; likely to incorporate new perspectives and possibilities"
            elif "identity" in vulnerabilities:
                return "Identity reconfiguration; may trigger substantial reexamination of self-concept"
            else:
                return "Selective integration; will adopt aspects that align with existing values and beliefs"
                
        elif is_challenging:
            if neuroticism > 0.7:
                return "Possible confidence impact; may reinforce self-doubt if not successfully navigated"
            elif "inadequacy" in vulnerabilities:
                return "Vulnerability activation; likely to trigger existing feelings of insufficiency"
            else:
                return "Skill development; will likely build new capabilities through overcoming the challenge"
        
        # Default for less significant events
        return "Moderate memory formation; will be incorporated into experience without major psychological shifts"
    
    def _analyze_character_in_narrative(self, 
                                      character_id: Optional[int], 
                                      character_name: str,
                                      narrative_text: str,
                                      episode: str) -> Dict[str, Any]:
        """
        Analyze a character's psychological state in a narrative
        
        Args:
            character_id: Character ID if available
            character_name: Character name
            narrative_text: Narrative text to analyze
            episode: Current episode
            
        Returns:
            Dictionary with character state analysis
        """
        # This is a simple implementation - a full version would use LLM for analysis
        
        # Initialize character state
        character_state = {
            "emotional_state": None,
            "motivational_state": None,
            "cognitive_state": None,
            "behavioral_indicators": [],
            "significant_actions": [],
            "psychological_shifts": []
        }
        
        # First, check if the character is actually mentioned in the narrative
        if character_name not in narrative_text:
            return None
        
        # Extract emotional state
        emotional_keywords = {}
        for emotion, terms in EMOTIONS.items():
            count = 0
            for term in terms:
                # Look for emotional terms near character name
                if self._is_term_associated_with_character(term, character_name, narrative_text):
                    count += 1
            
            if count > 0:
                emotional_keywords[emotion] = count
        
        # Set the dominant emotion
        if emotional_keywords:
            dominant_emotion = max(emotional_keywords.items(), key=lambda x: x[1])
            character_state["emotional_state"] = dominant_emotion[0]
        
        # Extract motivational state
        motivational_keywords = {}
        for motivation, terms in MOTIVATIONS.items():
            count = 0
            for term in terms:
                if self._is_term_associated_with_character(term, character_name, narrative_text):
                    count += 1
            
            if count > 0:
                motivational_keywords[motivation] = count
        
        # Set the dominant motivation
        if motivational_keywords:
            dominant_motivation = max(motivational_keywords.items(), key=lambda x: x[1])
            character_state["motivational_state"] = dominant_motivation[0]
        
        # Extract cognitive state indicators
        cognitive_indicators = {
            "rational": ["think", "consider", "analyze", "reason", "calculate", "evaluate"],
            "intuitive": ["feel", "sense", "intuit", "gut", "instinct"],
            "conflicted": ["uncertain", "torn", "hesitate", "doubt", "unsure", "conflict"],
            "focused": ["concentrate", "focus", "fixate", "determined", "intent"],
            "distracted": ["distract", "wander", "confusion", "scattered", "unfocused"]
        }
        
        for cognitive_state, terms in cognitive_indicators.items():
            for term in terms:
                if self._is_term_associated_with_character(term, character_name, narrative_text):
                    character_state["cognitive_state"] = cognitive_state
                    break
            
            if character_state["cognitive_state"]:
                break
        
        # Extract behavioral indicators
        behavioral_keywords = [
            "approached", "avoided", "attacked", "defended", "helped", "hindered",
            "shared", "withdrew", "confronted", "escaped", "investigated", "ignored"
        ]
        
        for keyword in behavioral_keywords:
            if self._is_term_associated_with_character(keyword, character_name, narrative_text):
                character_state["behavioral_indicators"].append(keyword)
        
        # Extract significant actions
        # This would require more sophisticated NLP in a full implementation
        # For now, we'll just look for sentences with the character name and action verbs
        sentences = narrative_text.split('.')
        for sentence in sentences:
            if character_name in sentence:
                action_verbs = ["said", "walked", "ran", "fought", "decided", "took", "gave", "found"]
                for verb in action_verbs:
                    if verb in sentence.lower():
                        # Clean up the sentence
                        clean_sentence = sentence.strip() + '.'
                        character_state["significant_actions"].append(clean_sentence)
                        break
        
        # Limit to top 3 actions for clarity
        character_state["significant_actions"] = character_state["significant_actions"][:3]
        
        return character_state
    
    def _is_term_associated_with_character(self, term: str, character_name: str, text: str) -> bool:
        """
        Check if a term is associated with a character in the text
        
        Args:
            term: Term to check for
            character_name: Character name
            text: Text to analyze
            
        Returns:
            True if the term is associated with the character
        """
        # Simple approach: check if term appears within 10 words of character name
        text_lower = text.lower()
        term_lower = term.lower()
        
        # Find all occurrences of the character name
        name_indices = [m.start() for m in re.finditer(re.escape(character_name), text)]
        
        for index in name_indices:
            # Get context window around name occurrence
            start = max(0, index - 50)
            end = min(len(text), index + 50 + len(character_name))
            context = text_lower[start:end]
            
            # Check if term is in context
            if term_lower in context:
                return True
        
        return False
    
    def _identify_growth_moments(self, 
                              narrative_text: str, 
                              character_states: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify character growth moments in the narrative
        
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
        
        # Check for growth indicators
        for indicator in growth_indicators:
            if indicator in narrative_text.lower():
                # Find the sentence containing this indicator
                sentences = narrative_text.split('.')
                for sentence in sentences:
                    if indicator in sentence.lower():
                        # Determine which character is experiencing the growth
                        character_name = None
                        for name in character_states.keys():
                            if name in sentence:
                                character_name = name
                                break
                        
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
                            "description": sentence.strip() + '.',
                            "psychological_significance": "Character development through new understanding or perspective"
                        })
                        break
        
        # Limit to 3 most significant growth moments
        return growth_moments[:3]
    
    def _check_psychological_consistency(self, 
                                      narrative_text: str, 
                                      character_states: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check for psychological consistency in the narrative
        
        Args:
            narrative_text: Narrative text to analyze
            character_states: Dictionary of character states
            
        Returns:
            Dictionary with consistency results
        """
        result = {
            "consistent": True,
            "inconsistencies": []
        }
        
        # For each character, check for psychological inconsistencies
        for character_name, state in character_states.items():
            emotional_state = state.get("emotional_state")
            motivational_state = state.get("motivational_state")
            
            # Skip characters without enough information
            if not emotional_state or not motivational_state:
                continue
            
            # Define opposite emotions
            opposing_emotions = {
                "joy": ["sadness", "fear"],
                "sadness": ["joy"],
                "fear": ["joy"],
                "anger": ["joy"],
                "trust": ["disgust"]
            }
            
            # Check for emotional inconsistencies
            if emotional_state in opposing_emotions:
                for opposing in opposing_emotions[emotional_state]:
                    for emotion_term in EMOTIONS.get(opposing, []):
                        # Check if the character is associated with the opposing emotion
                        if self._is_term_associated_with_character(emotion_term, character_name, narrative_text):
                            result["consistent"] = False
                            result["inconsistencies"].append({
                                "type": "emotional_inconsistency",
                                "character": character_name,
                                "description": f"Character shows both {emotional_state} and {opposing} without clear transition",
                                "psychological_explanation": "Emotional states typically transition gradually unless triggered by a significant event"
                            })
                            break
            
            # Check for motivational inconsistencies
            opposing_motivations = {
                "power": ["affiliation"],
                "achievement": ["safety"],
                "safety": ["risk-taking"]
            }
            
            if motivational_state in opposing_motivations:
                for opposing in opposing_motivations[motivational_state]:
                    # Check if character shows opposing motivation
                    if self._is_term_associated_with_character(opposing, character_name, narrative_text):
                        result["consistent"] = False
                        result["inconsistencies"].append({
                            "type": "motivational_inconsistency",
                            "character": character_name,
                            "description": f"Character shows both {motivational_state} and {opposing} drives without clear reasoning",
                            "psychological_explanation": "Core motivational drives tend to be stable unless explicitly challenged by narrative events"
                        })
        
        return result
