#!/usr/bin/env python3
"""
psyche_poly.py: Relationship Analysis Module for Night City Stories

This module provides functionality for analyzing relationships between characters as part of 
the Character Psychologist agent. It handles relationship dynamic detection, communication 
pattern analysis, relationship stability assessment, and predictions for relationship 
development over time.

The RelationshipAnalyzer class serves as the core component, providing methods to analyze 
pairs of characters, detect patterns in their interactions, and assess the psychological 
underpinnings of their relationships.

Usage:
    # Import and use within the main psyche.py module
    from psyche_poly import RelationshipAnalyzer, RELATIONSHIP_TYPES, RELATIONSHIP_DYNAMICS
    
    relationship_analyzer = RelationshipAnalyzer()
    analysis = relationship_analyzer.analyze_relationship(entity1_id=1, entity1_name="Alex", entity2_id=2, entity2_name="Emilia")
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
        logging.FileHandler("psyche_poly.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("psyche_poly")

# Core relationship types
RELATIONSHIP_TYPES = {
    "professional": {
        "description": "Work-related or skill-based connections",
        "subtypes": ["mentorship", "rivalry", "collaboration", "colleague", "supervisor"]
    },
    "personal": {
        "description": "Emotional or intimate connections",
        "subtypes": ["friendship", "romance", "family", "acquaintance", "confidant"]
    },
    "antagonistic": {
        "description": "Hostile or opposing connections",
        "subtypes": ["enemy", "adversary", "opposition", "nemesis", "competitor"]
    },
    "power_based": {
        "description": "Authority or influence-related connections",
        "subtypes": ["authority", "subordinate", "equal", "protector", "dependent"]
    }
}

# Core relationship dynamics
RELATIONSHIP_DYNAMICS = {
    "trust": {
        "description": "Degree of faith in reliability and truth",
        "high": "Deep mutual trust and confidence in each other",
        "low": "Suspicion, skepticism, and guarded interactions"
    },
    "intimacy": {
        "description": "Emotional and psychological closeness",
        "high": "Strong emotional connection and vulnerability sharing",
        "low": "Emotional distance and superficial engagement"
    },
    "power_balance": {
        "description": "Distribution of influence and control",
        "balanced": "Equal partnership with mutual respect",
        "imbalanced": "One party holds significantly more control or influence"
    },
    "stability": {
        "description": "Consistency and predictability of the relationship",
        "high": "Consistent, reliable patterns of interaction",
        "low": "Volatile, unpredictable, and rapidly changing"
    },
    "communication": {
        "description": "Quality and nature of information exchange",
        "healthy": "Open, honest, and constructive communication",
        "unhealthy": "Deceptive, manipulative, or avoidant communication"
    },
    "conflict_pattern": {
        "description": "How disagreements are handled",
        "constructive": "Productive resolution focused on mutual growth",
        "destructive": "Escalation, blame, or unresolved tension"
    }
}

# Communication patterns
COMMUNICATION_PATTERNS = {
    "open": "Transparent sharing of thoughts and feelings",
    "closed": "Guarded, minimal disclosure of personal information",
    "direct": "Straightforward expression without ambiguity",
    "indirect": "Subtle, implied communication requiring interpretation",
    "supportive": "Affirming and encouraging exchanges",
    "critical": "Judgmental or fault-finding interactions",
    "collaborative": "Joint problem-solving and decision-making",
    "competitive": "Communication aimed at gaining advantage",
    "passive": "Non-assertive, yielding communication style",
    "aggressive": "Forceful, dominant expression",
    "passive_aggressive": "Indirect expression of negative feelings",
    "manipulative": "Strategic communication to influence or control"
}

class RelationshipAnalyzer:
    """
    Relationship Analyzer for psychological assessment of interpersonal dynamics
    """
    
    def __init__(self, settings: Dict[str, Any] = None):
        """
        Initialize the Relationship Analyzer
        
        Args:
            settings: Optional settings dictionary
        """
        # Initialize settings
        self.settings = {}
        if settings:
            self.settings.update(settings)
        elif config:
            # Try to load from config_manager
            relationship_config = config.get_section("relationship_analysis")
            if relationship_config:
                self.settings.update(relationship_config)
        
        # Initialize cache for relationship analyses
        self.relationship_analyses = {}
        
        # Initialize counter for analyses
        self.analysis_count = 0
        
        logger.info("Relationship Analyzer initialized")
    
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
            entity1_type: Type of the first entity (default: "character")
            entity2_id: ID of the second entity (optional if name is provided)
            entity2_name: Name of the second entity (optional if ID is provided)
            entity2_type: Type of the second entity (default: "character")
            episode: Episode for which to analyze the relationship
            
        Returns:
            Dictionary containing relationship analysis
        """
        logger.info(f"Analyzing relationship between {entity1_name or entity1_id} and {entity2_name or entity2_id} for episode {episode}")
        
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
            logger.error("Cannot analyze relationship: missing entity identifiers")
            return {
                "error": "missing_entity_identifiers",
                "message": "Both entities must have either ID or name provided"
            }
        
        # Check if we have a cached analysis
        cache_key = f"{entity1_type}_{entity1_id}_{entity1_name}_{entity2_type}_{entity2_id}_{entity2_name}_{episode}"
        if cache_key in self.relationship_analyses:
            # Get cached analysis
            analysis = self.relationship_analyses[cache_key]
            logger.info(f"Using cached analysis for relationship between {entity1_name or entity1_id} and {entity2_name or entity2_id}")
        else:
            # Create a new analysis
            analysis = self._create_relationship_analysis(
                entity1_id, entity1_name, entity1_type,
                entity2_id, entity2_name, entity2_type,
                episode
            )
            self.relationship_analyses[cache_key] = analysis
            logger.info(f"Created new analysis for relationship between {entity1_name or entity1_id} and {entity2_name or entity2_id}")
        
        # Get relationship memory for context
        memory_context = ""
        try:
            if 'memnon' in sys.modules and entity1_name and entity2_name:
                # Search for relationship mentions in memory
                memory_chunks = memnon.get_memory_for_context(
                    f"Relationship between {entity1_name} and {entity2_name}, interactions, history",
                    top_k=5
                )
                
                # Extract text from chunks
                for chunk in memory_chunks:
                    chunk_text = chunk.get("text", "")
                    if chunk_text:
                        memory_context += chunk_text + "\n\n"
                
                # Add memory context to analysis
                analysis["memory_context"] = memory_context
                
                # Analyze relationship in narrative context
                narrative_analysis = self._analyze_relationship_in_narrative(
                    entity1_name, entity2_name, memory_context, episode
                )
                
                if narrative_analysis:
                    # Merge narrative analysis into the main analysis
                    analysis["observed_dynamics"] = narrative_analysis.get("observed_dynamics", {})
                    analysis["significant_interactions"] = narrative_analysis.get("significant_interactions", [])
                    analysis["communication_pattern"] = narrative_analysis.get("communication_pattern")
        except Exception as e:
            logger.error(f"Error getting relationship memory: {e}")
        
        # Analyze relationship stability
        stability_analysis = self._analyze_relationship_stability(analysis)
        analysis["stability_analysis"] = stability_analysis
        
        # Predict relationship development
        development_prediction = self._predict_relationship_development(analysis)
        analysis["development_prediction"] = development_prediction
        
        # Track analysis count
        self.analysis_count += 1
        
        return analysis
    
    def _create_relationship_analysis(self,
                                    entity1_id: Optional[int],
                                    entity1_name: Optional[str],
                                    entity1_type: str,
                                    entity2_id: Optional[int],
                                    entity2_name: Optional[str],
                                    entity2_type: str,
                                    episode: str) -> Dict[str, Any]:
        """
        Create a baseline relationship analysis between two entities
        
        Args:
            entity1_id: ID of the first entity (optional)
            entity1_name: Name of the first entity (optional)
            entity1_type: Type of the first entity
            entity2_id: ID of the second entity (optional)
            entity2_name: Name of the second entity (optional)
            entity2_type: Type of the second entity
            episode: Episode for which to analyze the relationship
            
        Returns:
            Dictionary containing the relationship analysis
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
            "updated_at": time.time(),
            "relationship_type": None,
            "relationship_subtype": None,
            "relationship_dynamics": {},
            "relationship_history": [],
            "power_dynamic": None,
            "communication_pattern": None,
            "observed_dynamics": {},
            "significant_interactions": [],
            "potential_conflicts": [],
            "psychological_alignment": {}
        }
        
        # If both entities are characters and we have database access, get relationship data
        if entity1_type == "character" and entity2_type == "character" and 'db_sqlite' in sys.modules:
            try:
                # Get character relationship if both IDs are available
                if entity1_id is not None and entity2_id is not None:
                    relationship = db_sqlite.get_relationship_between_characters(entity1_id, entity2_id)
                    
                    if relationship:
                        # Set relationship dynamic from database
                        dynamic = relationship.get("dynamic")
                        if dynamic:
                            # Try to categorize the dynamic
                            analysis["relationship_type"], analysis["relationship_subtype"] = self._categorize_relationship_dynamic(dynamic)
                
                # Try to get relationship state
                if entity1_id is not None and entity2_id is not None:
                    relationship_state = db_sqlite.get_relationship_current_state(
                        "character", entity1_id, "character", entity2_id
                    )
                    
                    if relationship_state:
                        # Extract relationship dynamics from state
                        for state_type, state_value in relationship_state.items():
                            # Map state types to relationship dynamics
                            if state_type == "trust":
                                analysis["relationship_dynamics"]["trust"] = state_value
                            elif state_type == "power":
                                analysis["power_dynamic"] = state_value
                            elif state_type == "closeness" or state_type == "intimacy":
                                analysis["relationship_dynamics"]["intimacy"] = state_value
                            else:
                                # For other state types, add directly to dynamics
                                analysis["relationship_dynamics"][state_type] = state_value
                
                # Get relationship history
                if entity1_id is not None and entity2_id is not None:
                    # This would ideally use a dedicated function to get relationship history
                    # For now, we'll simulate with a simplified approach
                    if 'memnon' in sys.modules:
                        # Use memnon to get historical events involving both entities
                        memory_chunks = memnon.get_memory_for_context(
                            f"Historical events and interactions between {entity1_name} and {entity2_name}",
                            top_k=5
                        )
                        
                        # Extract and process events
                        for chunk in memory_chunks:
                            chunk_text = chunk.get("text", "")
                            chunk_episode = chunk.get("metadata", {}).get("episode", "unknown")
                            
                            if chunk_text and chunk_episode:
                                # Add to relationship history
                                analysis["relationship_history"].append({
                                    "episode": chunk_episode,
                                    "description": self._extract_relevant_content(chunk_text, entity1_name, entity2_name)
                                })
                
                # Get individual character data for psychological alignment
                if entity1_id is not None:
                    char1 = db_sqlite.get_character_by_id(entity1_id)
                    if char1:
                        analysis["entity1"]["description"] = char1.get("description", "")
                        analysis["entity1"]["personality"] = char1.get("personality", "")
                
                if entity2_id is not None:
                    char2 = db_sqlite.get_character_by_id(entity2_id)
                    if char2:
                        analysis["entity2"]["description"] = char2.get("description", "")
                        analysis["entity2"]["personality"] = char2.get("personality", "")
                
                # If we have personality data for both characters, analyze psychological alignment
                if "personality" in analysis["entity1"] and "personality" in analysis["entity2"]:
                    analysis["psychological_alignment"] = self._analyze_psychological_alignment(
                        analysis["entity1"]["personality"],
                        analysis["entity2"]["personality"]
                    )
            except Exception as e:
                logger.error(f"Error getting relationship data: {e}")
        
        return analysis
    
    def _categorize_relationship_dynamic(self, dynamic: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Categorize a relationship dynamic into type and subtype
        
        Args:
            dynamic: Relationship dynamic description
            
        Returns:
            Tuple of (relationship_type, relationship_subtype)
        """
        dynamic_lower = dynamic.lower()
        
        # Check for professional relationships
        for subtype in RELATIONSHIP_TYPES["professional"]["subtypes"]:
            if subtype in dynamic_lower or subtype.replace("_", " ") in dynamic_lower:
                return "professional", subtype
        
        # Check for personal relationships
        for subtype in RELATIONSHIP_TYPES["personal"]["subtypes"]:
            if subtype in dynamic_lower or subtype.replace("_", " ") in dynamic_lower:
                return "personal", subtype
        
        # Check for antagonistic relationships
        for subtype in RELATIONSHIP_TYPES["antagonistic"]["subtypes"]:
            if subtype in dynamic_lower or subtype.replace("_", " ") in dynamic_lower:
                return "antagonistic", subtype
        
        # Check for power-based relationships
        for subtype in RELATIONSHIP_TYPES["power_based"]["subtypes"]:
            if subtype in dynamic_lower or subtype.replace("_", " ") in dynamic_lower:
                return "power_based", subtype
        
        # Additional keyword checks
        if any(word in dynamic_lower for word in ["friend", "close", "trust", "confide"]):
            return "personal", "friendship"
        elif any(word in dynamic_lower for word in ["love", "intimate", "romantic", "attracted"]):
            return "personal", "romance"
        elif any(word in dynamic_lower for word in ["work", "colleague", "professional", "business"]):
            return "professional", "collaboration"
        elif any(word in dynamic_lower for word in ["enemy", "hostile", "oppose", "against", "conflict"]):
            return "antagonistic", "adversary"
        elif any(word in dynamic_lower for word in ["lead", "follow", "command", "obey", "authority"]):
            return "power_based", "authority"
        
        # Default if no clear category is found
        return None, None
    
    def _analyze_psychological_alignment(self, personality1: str, personality2: str) -> Dict[str, Any]:
        """
        Analyze psychological alignment between two personalities
        
        Args:
            personality1: Personality description of the first entity
            personality2: Personality description of the second entity
            
        Returns:
            Dictionary containing psychological alignment analysis
        """
        # Initialize alignment analysis
        alignment = {
            "compatibility": None,
            "complementary_traits": [],
            "conflicting_traits": [],
            "potential_growth_areas": []
        }
        
        # Combine personality descriptions
        combined_text = (personality1 + " " + personality2).lower()
        
        # Define trait pairs to analyze
        trait_pairs = {
            "analytical_intuitive": {
                "first": ["analytical", "logical", "methodical", "rational", "systematic"],
                "second": ["intuitive", "instinctive", "gut", "feeling", "instinct"],
                "complementary": True
            },
            "cautious_risk_taking": {
                "first": ["cautious", "careful", "measured", "prudent", "safe"],
                "second": ["risk", "adventurous", "bold", "daring", "spontaneous"],
                "complementary": True
            },
            "introvert_extrovert": {
                "first": ["introvert", "quiet", "reserved", "solitary", "reflective"],
                "second": ["extrovert", "outgoing", "social", "expressive", "talkative"],
                "complementary": True
            },
            "detail_big_picture": {
                "first": ["detail", "precise", "specific", "thorough", "meticulous"],
                "second": ["big picture", "vision", "abstract", "conceptual", "strategic"],
                "complementary": True
            },
            "controlling_adaptable": {
                "first": ["controlling", "dominant", "leader", "authoritative", "decisive"],
                "second": ["adaptable", "flexible", "accommodating", "easygoing", "agreeable"],
                "conflicting": True
            },
            "trusting_suspicious": {
                "first": ["trusting", "open", "believing", "accepting", "faith"],
                "second": ["suspicious", "skeptical", "doubting", "questioning", "wary"],
                "conflicting": True
            },
            "optimistic_pessimistic": {
                "first": ["optimistic", "hopeful", "positive", "upbeat", "enthusiastic"],
                "second": ["pessimistic", "negative", "critical", "doubtful", "cynical"],
                "conflicting": True
            }
        }
        
        # Analyze each trait pair
        for pair_name, pair_data in trait_pairs.items():
            # Check if first personality has traits from the first set
            has_first_trait = any(trait in personality1.lower() for trait in pair_data["first"])
            # Check if second personality has traits from the second set
            has_second_trait = any(trait in personality2.lower() for trait in pair_data["second"])
            
            # Check for complementary or conflicting traits
            if has_first_trait and has_second_trait:
                if pair_data.get("complementary"):
                    alignment["complementary_traits"].append(pair_name.replace("_", "-"))
                elif pair_data.get("conflicting"):
                    alignment["conflicting_traits"].append(pair_name.replace("_", "-"))
            
            # Also check the reverse case
            has_second_trait_in_first = any(trait in personality1.lower() for trait in pair_data["second"])
            has_first_trait_in_second = any(trait in personality2.lower() for trait in pair_data["first"])
            
            if has_second_trait_in_first and has_first_trait_in_second:
                if pair_data.get("complementary"):
                    alignment["complementary_traits"].append(pair_name.replace("_", "-") + " (reversed)")
                elif pair_data.get("conflicting"):
                    alignment["conflicting_traits"].append(pair_name.replace("_", "-") + " (reversed)")
        
        # Determine overall compatibility based on trait analysis
        complementary_count = len(alignment["complementary_traits"])
        conflicting_count = len(alignment["conflicting_traits"])
        
        if complementary_count > conflicting_count + 1:
            alignment["compatibility"] = "high"
        elif complementary_count > conflicting_count:
            alignment["compatibility"] = "moderate"
        elif complementary_count == conflicting_count:
            alignment["compatibility"] = "mixed"
        else:
            alignment["compatibility"] = "low"
        
        # Identify potential growth areas
        if "controlling-adaptable" in alignment["conflicting_traits"]:
            alignment["potential_growth_areas"].append("developing balanced decision-making processes")
        if "trusting-suspicious" in alignment["conflicting_traits"]:
            alignment["potential_growth_areas"].append("establishing clear communication about expectations")
        if "optimistic-pessimistic" in alignment["conflicting_traits"]:
            alignment["potential_growth_areas"].append("finding middle ground in goal-setting and planning")
        if "analytical-intuitive" in alignment["complementary_traits"]:
            alignment["potential_growth_areas"].append("leveraging complementary problem-solving approaches")
        
        return alignment
    
    def _extract_relevant_content(self, text: str, entity1_name: str, entity2_name: str) -> str:
        """
        Extract content relevant to the relationship between two entities
        
        Args:
            text: Full text to extract from
            entity1_name: Name of the first entity
            entity2_name: Name of the second entity
            
        Returns:
            Extracted relevant content
        """
        # Split text into sentences
        sentences = text.split('.')
        
        # Find sentences containing both entity names
        relevant_sentences = []
        for sentence in sentences:
            if entity1_name in sentence and entity2_name in sentence:
                relevant_sentences.append(sentence.strip())
        
        # If no sentences contain both names, look for sentences with either name
        if not relevant_sentences:
            for sentence in sentences:
                if entity1_name in sentence or entity2_name in sentence:
                    relevant_sentences.append(sentence.strip())
            
            # Limit to 3 sentences if we found any
            relevant_sentences = relevant_sentences[:3]
        
        # Combine sentences
        return '. '.join(relevant_sentences) + '.' if relevant_sentences else "No relevant content found."
    
    def _analyze_relationship_in_narrative(self, 
                                        entity1_name: str, 
                                        entity2_name: str, 
                                        narrative_text: str,
                                        episode: str) -> Dict[str, Any]:
        """
        Analyze relationship dynamics in narrative text
        
        Args:
            entity1_name: Name of the first entity
            entity2_name: Name of the second entity
            narrative_text: Narrative text to analyze
            episode: Current episode
            
        Returns:
            Dictionary with relationship analysis
        """
        # Initialize relationship analysis
        relationship_analysis = {
            "observed_dynamics": {},
            "significant_interactions": [],
            "communication_pattern": None
        }
        
        # Skip if narrative text is empty
        if not narrative_text:
            return relationship_analysis
        
        # Extract interaction sentences
        interaction_sentences = self._extract_interaction_sentences(narrative_text, entity1_name, entity2_name)
        
        # Analyze dynamics in interactions
        dynamics_analysis = self._analyze_dynamics_in_text(interaction_sentences, entity1_name, entity2_name)
        relationship_analysis["observed_dynamics"] = dynamics_analysis
        
        # Extract significant interactions
        relationship_analysis["significant_interactions"] = self._extract_significant_interactions(
            narrative_text, entity1_name, entity2_name
        )
        
        # Analyze communication pattern
        relationship_analysis["communication_pattern"] = self._analyze_communication_pattern(
            interaction_sentences, entity1_name, entity2_name
        )
        
        return relationship_analysis
    
    def _extract_interaction_sentences(self, text: str, entity1_name: str, entity2_name: str) -> List[str]:
        """
        Extract sentences containing interactions between two entities
        
        Args:
            text: Text to search
            entity1_name: Name of the first entity
            entity2_name: Name of the second entity
            
        Returns:
            List of interaction sentences
        """
        # Split text into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Find sentences containing both entity names
        interaction_sentences = []
        for sentence in sentences:
            if entity1_name in sentence and entity2_name in sentence:
                interaction_sentences.append(sentence.strip())
        
        return interaction_sentences
    
    def _analyze_dynamics_in_text(self, sentences: List[str], entity1_name: str, entity2_name: str) -> Dict[str, str]:
        """
        Analyze relationship dynamics in interaction sentences
        
        Args:
            sentences: List of interaction sentences
            entity1_name: Name of the first entity
            entity2_name: Name of the second entity
            
        Returns:
            Dictionary of relationship dynamics
        """
        # Initialize dynamics
        dynamics = {}
        
        # Skip if no sentences
        if not sentences:
            return dynamics
        
        # Combine all sentences for analysis
        combined_text = " ".join(sentences).lower()
        
        # Analyze trust
        trust_indicators = {
            "high": ["trust", "confide", "rely", "honest", "faithful", "loyal", "depend"],
            "low": ["suspect", "doubt", "distrust", "skeptical", "wary", "suspicious", "betray"]
        }
        
        trust_high_count = sum(combined_text.count(word) for word in trust_indicators["high"])
        trust_low_count = sum(combined_text.count(word) for word in trust_indicators["low"])
        
        if trust_high_count > trust_low_count + 1:
            dynamics["trust"] = "high"
        elif trust_low_count > trust_high_count + 1:
            dynamics["trust"] = "low"
        elif trust_high_count > 0 or trust_low_count > 0:
            dynamics["trust"] = "mixed"
        
        # Analyze intimacy
        intimacy_indicators = {
            "high": ["close", "intimate", "personal", "confide", "share", "bond", "deep"],
            "low": ["distant", "formal", "cold", "impersonal", "detached", "superficial"]
        }
        
        intimacy_high_count = sum(combined_text.count(word) for word in intimacy_indicators["high"])
        intimacy_low_count = sum(combined_text.count(word) for word in intimacy_indicators["low"])
        
        if intimacy_high_count > intimacy_low_count + 1:
            dynamics["intimacy"] = "high"
        elif intimacy_low_count > intimacy_high_count + 1:
            dynamics["intimacy"] = "low"
        elif intimacy_high_count > 0 or intimacy_low_count > 0:
            dynamics["intimacy"] = "mixed"
        
        # Analyze power balance
        power_indicators = {
            "entity1_dominant": [
                f"{entity1_name.lower()} order", f"{entity1_name.lower()} command", 
                f"{entity1_name.lower()} direct", f"{entity1_name.lower()} lead", 
                f"{entity2_name.lower()} obey", f"{entity2_name.lower()} follow"
            ],
            "entity2_dominant": [
                f"{entity2_name.lower()} order", f"{entity2_name.lower()} command", 
                f"{entity2_name.lower()} direct", f"{entity2_name.lower()} lead", 
                f"{entity1_name.lower()} obey", f"{entity1_name.lower()} follow"
            ],
            "balanced": ["agree", "together", "both", "equal", "mutual", "partner"]
        }
        
        entity1_power_count = sum(combined_text.count(phrase) for phrase in power_indicators["entity1_dominant"])
        entity2_power_count = sum(combined_text.count(phrase) for phrase in power_indicators["entity2_dominant"])
        balanced_power_count = sum(combined_text.count(word) for word in power_indicators["balanced"])
        
        if entity1_power_count > entity2_power_count + balanced_power_count:
            dynamics["power_balance"] = f"{entity1_name} dominant"
        elif entity2_power_count > entity1_power_count + balanced_power_count:
            dynamics["power_balance"] = f"{entity2_name} dominant"
        elif balanced_power_count > entity1_power_count + entity2_power_count:
            dynamics["power_balance"] = "balanced"
        else:
            dynamics["power_balance"] = "context dependent"
        
        # Analyze conflict
        conflict_indicators = {
            "high": ["argue", "fight", "disagree", "conflict", "tension", "dispute", "clash"],
            "low": ["agree", "harmony", "peaceful", "understanding", "compromise"]
        }
        
        conflict_high_count = sum(combined_text.count(word) for word in conflict_indicators["high"])
        conflict_low_count = sum(combined_text.count(word) for word in conflict_indicators["low"])
        
        if conflict_high_count > conflict_low_count + 1:
            dynamics["conflict"] = "high"
        elif conflict_low_count > conflict_high_count + 1:
            dynamics["conflict"] = "low"
        elif conflict_high_count > 0 or conflict_low_count > 0:
            dynamics["conflict"] = "moderate"
        
        return dynamics
    
    def _extract_significant_interactions(self, text: str, entity1_name: str, entity2_name: str) -> List[Dict[str, str]]:
        """
        Extract significant interactions between two entities
        
        Args:
            text: Text to search
            entity1_name: Name of the first entity
            entity2_name: Name of the second entity
            
        Returns:
            List of significant interactions
        """
        # Split text into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Find sentences containing both entity names
        interaction_sentences = []
        for sentence in sentences:
            if entity1_name in sentence and entity2_name in sentence:
                interaction_sentences.append(sentence.strip())
        
        # Identify significant interactions
        significant_interactions = []
        
        # Look for significant interaction types
        significance_indicators = {
            "conflict": ["argue", "fight", "disagree", "conflict", "tension", "dispute", "clash", "yell"],
            "support": ["help", "support", "assist", "aid", "defend", "protect", "save"],
            "revelation": ["reveal", "confess", "admit", "tell", "secret", "truth", "discover"],
            "emotional": ["love", "hate", "fear", "trust", "distrust", "jealous", "proud", "disappointed"],
            "power": ["order", "command", "obey", "follow", "lead", "dominate", "control"]
        }
        
        for sentence in interaction_sentences:
            sentence_lower = sentence.lower()
            
            # Check for significance indicators
            interaction_type = None
            for type_name, indicators in significance_indicators.items():
                if any(indicator in sentence_lower for indicator in indicators):
                    interaction_type = type_name
                    break
            
            if interaction_type:
                significant_interactions.append({
                    "type": interaction_type,
                    "description": sentence
                })
        
        # Limit to the 3 most significant interactions
        return significant_interactions[:3]
    
    def _analyze_communication_pattern(self, sentences: List[str], entity1_name: str, entity2_name: str) -> Optional[str]:
        """
        Analyze communication pattern between two entities
        
        Args:
            sentences: List of interaction sentences
            entity1_name: Name of the first entity
            entity2_name: Name of the second entity
            
        Returns:
            Communication pattern description or None if not enough data
        """
        # Skip if not enough sentences
        if len(sentences) < 2:
            return None
        
        # Combine sentences for analysis
        combined_text = " ".join(sentences).lower()
        
        # Count occurrences of communication pattern indicators
        pattern_counts = {}
        for pattern, description in COMMUNICATION_PATTERNS.items():
            # Define keywords for each pattern
            if pattern == "open":
                keywords = ["share", "honest", "open", "express", "talk", "communicate"]
            elif pattern == "closed":
                keywords = ["withhold", "hide", "secret", "avoid", "silent", "quiet"]
            elif pattern == "direct":
                keywords = ["direct", "clear", "straightforward", "explicit", "blunt"]
            elif pattern == "indirect":
                keywords = ["hint", "imply", "suggest", "subtle", "indirect"]
            elif pattern == "supportive":
                keywords = ["support", "encourage", "understand", "listen", "empathize"]
            elif pattern == "critical":
                keywords = ["criticize", "judge", "fault", "blame", "negative"]
            elif pattern == "collaborative":
                keywords = ["together", "collaborate", "cooperate", "joint", "team"]
            elif pattern == "competitive":
                keywords = ["compete", "challenge", "opposition", "argue", "debate"]
            elif pattern == "passive":
                keywords = ["yield", "submit", "give in", "agree", "concede"]
            elif pattern == "aggressive":
                keywords = ["demand", "force", "insist", "pressure", "aggressive"]
            elif pattern == "passive_aggressive":
                keywords = ["indirect", "sarcasm", "subtle", "implied", "undertone"]
            elif pattern == "manipulative":
                keywords = ["manipulate", "trick", "deceive", "leverage", "influence"]
            else:
                keywords = []
            
            # Count occurrences
            pattern_counts[pattern] = sum(combined_text.count(keyword) for keyword in keywords)
        
        # Find the dominant patterns (top 2)
        sorted_patterns = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)
        dominant_patterns = [pattern for pattern, count in sorted_patterns[:2] if count > 0]
        
        if not dominant_patterns:
            return None
        
        # Combine patterns into a description
        if len(dominant_patterns) == 1:
            pattern = dominant_patterns[0]
            return f"{pattern.replace('_', '-')} communication"
        else:
            pattern1 = dominant_patterns[0]
            pattern2 = dominant_patterns[1]
            return f"{pattern1.replace('_', '-')} and {pattern2.replace('_', '-')} communication"
    
    def _analyze_relationship_stability(self, relationship_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the stability of a relationship
        
        Args:
            relationship_analysis: Relationship analysis dictionary
            
        Returns:
            Dictionary with stability analysis
        """
        # Initialize stability analysis
        stability_analysis = {
            "stability_level": None,
            "stabilizing_factors": [],
            "destabilizing_factors": [],
            "vulnerability_points": []
        }
        
        # Extract dynamics
        dynamics = relationship_analysis.get("relationship_dynamics", {})
        observed_dynamics = relationship_analysis.get("observed_dynamics", {})
        
        # Combine dynamics
        all_dynamics = {**dynamics, **observed_dynamics}
        
        # Analyze trust
        trust_level = all_dynamics.get("trust")
        if trust_level == "high":
            stability_analysis["stabilizing_factors"].append("high mutual trust")
        elif trust_level == "low":
            stability_analysis["destabilizing_factors"].append("lack of trust")
            stability_analysis["vulnerability_points"].append("trust issues could lead to relationship breakdown")
        
        # Analyze conflict
        conflict_level = all_dynamics.get("conflict")
        if conflict_level == "high":
            stability_analysis["destabilizing_factors"].append("high level of conflict")
            stability_analysis["vulnerability_points"].append("unresolved conflicts may escalate")
        elif conflict_level == "low":
            stability_analysis["stabilizing_factors"].append("low conflict level")
        
        # Analyze power balance
        power_balance = all_dynamics.get("power_balance")
        if power_balance == "balanced":
            stability_analysis["stabilizing_factors"].append("balanced power dynamic")
        elif power_balance and "dominant" in power_balance:
            stability_analysis["vulnerability_points"].append("power imbalance may cause resentment")
        
        # Analyze communication pattern
        communication_pattern = relationship_analysis.get("communication_pattern")
        if communication_pattern:
            if any(pattern in communication_pattern for pattern in ["open", "direct", "supportive", "collaborative"]):
                stability_analysis["stabilizing_factors"].append("healthy communication patterns")
            elif any(pattern in communication_pattern for pattern in ["closed", "indirect", "critical", "manipulative"]):
                stability_analysis["destabilizing_factors"].append("problematic communication patterns")
                stability_analysis["vulnerability_points"].append("communication issues may worsen over time")
        
        # Analyze psychological alignment
        psychological_alignment = relationship_analysis.get("psychological_alignment", {})
        compatibility = psychological_alignment.get("compatibility")
        
        if compatibility == "high":
            stability_analysis["stabilizing_factors"].append("high psychological compatibility")
        elif compatibility == "low":
            stability_analysis["destabilizing_factors"].append("low psychological compatibility")
            stability_analysis["vulnerability_points"].append("fundamental personality differences may create recurring issues")
        
        # Determine overall stability level
        stabilizing_count = len(stability_analysis["stabilizing_factors"])
        destabilizing_count = len(stability_analysis["destabilizing_factors"])
        
        if stabilizing_count > destabilizing_count + 1:
            stability_analysis["stability_level"] = "high"
        elif stabilizing_count > destabilizing_count:
            stability_analysis["stability_level"] = "moderate"
        elif stabilizing_count == destabilizing_count:
            stability_analysis["stability_level"] = "variable"
        else:
            stability_analysis["stability_level"] = "low"
        
        return stability_analysis
    
    def _predict_relationship_development(self, relationship_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict how a relationship might develop over time
        
        Args:
            relationship_analysis: Relationship analysis dictionary
            
        Returns:
            Dictionary with development predictions
        """
        # Initialize development prediction
        development_prediction = {
            "trajectory": None,
            "potential_evolution": None,
            "growth_opportunities": [],
            "potential_challenges": []
        }
        
        # Get stability analysis
        stability_analysis = relationship_analysis.get("stability_analysis", {})
        stability_level = stability_analysis.get("stability_level")
        
        # Get relationship type and dynamics
        relationship_type = relationship_analysis.get("relationship_type")
        dynamics = {**relationship_analysis.get("relationship_dynamics", {}), **relationship_analysis.get("observed_dynamics", {})}
        
        # Determine trajectory based on stability and dynamics
        if stability_level == "high":
            development_prediction["trajectory"] = "stable continuation"
        elif stability_level == "low":
            development_prediction["trajectory"] = "deterioration without intervention"
        else:
            # Look at trust and conflict trends
            trust_level = dynamics.get("trust")
            conflict_level = dynamics.get("conflict")
            
            if trust_level == "high" and conflict_level in ["low", "moderate"]:
                development_prediction["trajectory"] = "gradual strengthening"
            elif trust_level == "low" and conflict_level == "high":
                development_prediction["trajectory"] = "gradual deterioration"
            else:
                development_prediction["trajectory"] = "fluctuating with external factors"
        
        # Predict potential evolution based on relationship type
        if relationship_type == "professional":
            if development_prediction["trajectory"] in ["stable continuation", "gradual strengthening"]:
                development_prediction["potential_evolution"] = "deepening professional respect and collaboration"
            else:
                development_prediction["potential_evolution"] = "professional distance or formal interactions"
        
        elif relationship_type == "personal":
            if development_prediction["trajectory"] in ["stable continuation", "gradual strengthening"]:
                if relationship_analysis.get("relationship_subtype") == "friendship":
                    development_prediction["potential_evolution"] = "deepening friendship with increased trust and intimacy"
                elif relationship_analysis.get("relationship_subtype") == "romance":
                    development_prediction["potential_evolution"] = "strengthening emotional connection and commitment"
                else:
                    development_prediction["potential_evolution"] = "closer personal bond"
            else:
                development_prediction["potential_evolution"] = "emotional distance or relationship breakdown"
        
        elif relationship_type == "antagonistic":
            if development_prediction["trajectory"] in ["stable continuation", "gradual strengthening"]:
                development_prediction["potential_evolution"] = "entrenchment of antagonistic positions"
            else:
                development_prediction["potential_evolution"] = "potential for reconciliation if external factors change"
        
        elif relationship_type == "power_based":
            if development_prediction["trajectory"] in ["stable continuation", "gradual strengthening"]:
                development_prediction["potential_evolution"] = "reinforcement of existing power dynamics"
            else:
                development_prediction["potential_evolution"] = "power struggle or renegotiation of relationship"
        else:
            development_prediction["potential_evolution"] = "depends on future interactions and context"
        
        # Identify growth opportunities
        psychological_alignment = relationship_analysis.get("psychological_alignment", {})
        
        # Add growth opportunities from complementary traits
        complementary_traits = psychological_alignment.get("complementary_traits", [])
        for trait in complementary_traits:
            if "analytical-intuitive" in trait:
                development_prediction["growth_opportunities"].append("combining analytical and intuitive approaches to problem-solving")
            elif "cautious-risk_taking" in trait:
                development_prediction["growth_opportunities"].append("balancing caution with calculated risk-taking")
            elif "introvert-extrovert" in trait:
                development_prediction["growth_opportunities"].append("complementary social dynamics and energy management")
            elif "detail-big_picture" in trait:
                development_prediction["growth_opportunities"].append("comprehensive strategic planning with attention to details")
        
        # Add growth opportunities based on relationship type
        if relationship_type == "professional":
            development_prediction["growth_opportunities"].append("developing shared professional goals")
        elif relationship_type == "personal":
            development_prediction["growth_opportunities"].append("deepening emotional understanding and support")
        elif relationship_type == "antagonistic":
            development_prediction["growth_opportunities"].append("finding common ground despite differences")
        
        # Identify potential challenges
        conflicting_traits = psychological_alignment.get("conflicting_traits", [])
        for trait in conflicting_traits:
            if "controlling-adaptable" in trait:
                development_prediction["potential_challenges"].append("negotiating decision-making processes")
            elif "trusting-suspicious" in trait:
                development_prediction["potential_challenges"].append("building and maintaining trust")
            elif "optimistic-pessimistic" in trait:
                development_prediction["potential_challenges"].append("aligning expectations and outlook")
        
        # Add challenges from vulnerability points
        for vulnerability in stability_analysis.get("vulnerability_points", []):
            development_prediction["potential_challenges"].append(vulnerability)
        
        return development_prediction
    
    def _extract_relationship_dynamic(self, entity1_name: str, entity2_name: str, narrative_text: str) -> Optional[str]:
        """
        Extract relationship dynamic between two entities from narrative text
        
        Args:
            entity1_name: Name of the first entity
            entity2_name: Name of the second entity
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
            if entity1_name in sentence and entity2_name in sentence:
                relevant_sentences.append(sentence.strip())
        
        if not relevant_sentences:
            return None
        
        # Check for relationship keywords
        dynamic_scores = {dynamic: 0 for dynamic in dynamics}
        
        for sentence in relevant_sentences:
            sentence_lower = sentence.lower()
            for dynamic, keywords in dynamics.items():
                for keyword in keywords:
                    if keyword in sentence_lower:
                        dynamic_scores[dynamic] += 1
        
        # Return the highest scoring dynamic, if any
        if any(dynamic_scores.values()):
            top_dynamic = max(dynamic_scores.items(), key=lambda x: x[1])
            if top_dynamic[1] > 0:
                return top_dynamic[0]
        
        return None
    
    def run_test(self) -> bool:
        """
        Run tests on the Relationship Analyzer
        
        Returns:
            True if all tests pass, False otherwise
        """
        logger.info("=== Running Relationship Analyzer tests ===")
        
        all_passed = True
        
        # Test 1: Creating a relationship analysis
        try:
            logger.info("Test 1: Creating a relationship analysis")
            test_entity1_name = "Alex"
            test_entity2_name = "Emilia"
            
            analysis = self._create_relationship_analysis(
                entity1_id=None,
                entity1_name=test_entity1_name,
                entity1_type="character",
                entity2_id=None,
                entity2_name=test_entity2_name,
                entity2_type="character",
                episode="S01E01"
            )
            
            assert isinstance(analysis, dict)
            assert "entity1" in analysis
            assert "entity2" in analysis
            assert analysis["entity1"]["name"] == test_entity1_name
            assert analysis["entity2"]["name"] == test_entity2_name
            
            logger.info("✓ Test 1 passed")
        except AssertionError:
            logger.error("✗ Test 1 failed")
            all_passed = False
        
        # Test 2: Analyzing relationship in narrative
        try:
            logger.info("Test 2: Analyzing relationship in narrative")
            test_narrative = """
            Alex approached Emilia cautiously, still unsure if he could trust her after what happened.
            "I need your help," he admitted reluctantly.
            Emilia smiled, but there was tension in her eyes. "I thought you'd never ask," she said.
            Their last mission together had ended badly, with both of them barely escaping with their lives.
            Alex still blamed her for the security breach, but he knew she was the only one with the skills he needed now.
            "Just don't expect me to turn my back on you," he warned.
            Emilia's smile faded. "Fair enough. I wouldn't either."
            """
            
            relationship_analysis = self._analyze_relationship_in_narrative(
                entity1_name="Alex",
                entity2_name="Emilia",
                narrative_text=test_narrative,
                episode="S01E01"
            )
            
            assert isinstance(relationship_analysis, dict)
            assert "observed_dynamics" in relationship_analysis
            assert "significant_interactions" in relationship_analysis
            
            # Verify dynamics detection
            dynamics = relationship_analysis["observed_dynamics"]
            assert "trust" in dynamics
            assert dynamics["trust"] == "low"
            
            # Verify communication pattern
            assert relationship_analysis["communication_pattern"] is not None
            
            logger.info("✓ Test 2 passed")
        except AssertionError:
            logger.error("✗ Test 2 failed")
            all_passed = False
        
        # Test 3: Relationship stability analysis
        try:
            logger.info("Test 3: Relationship stability analysis")
            test_relationship = {
                "relationship_dynamics": {
                    "trust": "low",
                    "intimacy": "moderate"
                },
                "observed_dynamics": {
                    "conflict": "high",
                    "power_balance": "balanced"
                },
                "communication_pattern": "direct and critical communication",
                "psychological_alignment": {
                    "compatibility": "low",
                    "conflicting_traits": ["trusting-suspicious", "optimistic-pessimistic"]
                }
            }
            
            stability = self._analyze_relationship_stability(test_relationship)
            
            assert isinstance(stability, dict)
            assert "stability_level" in stability
            assert stability["stability_level"] == "low"
            assert len(stability["destabilizing_factors"]) > 0
            assert len(stability["vulnerability_points"]) > 0
            
            logger.info("✓ Test 3 passed")
        except AssertionError:
            logger.error("✗ Test 3 failed")
            all_passed = False
        
        # Test 4: Relationship development prediction
        try:
            logger.info("Test 4: Relationship development prediction")
            test_relationship = {
                "relationship_type": "professional",
                "relationship_subtype": "collaboration",
                "relationship_dynamics": {
                    "trust": "moderate",
                    "intimacy": "low"
                },
                "observed_dynamics": {
                    "conflict": "moderate",
                    "power_balance": "balanced"
                },
                "stability_analysis": {
                    "stability_level": "moderate",
                    "vulnerability_points": ["communication issues may worsen over time"]
                },
                "psychological_alignment": {
                    "complementary_traits": ["analytical-intuitive", "detail-big_picture"],
                    "conflicting_traits": ["trusting-suspicious"]
                }
            }
            
            prediction = self._predict_relationship_development(test_relationship)
            
            assert isinstance(prediction, dict)
            assert "trajectory" in prediction
            assert "potential_evolution" in prediction
            assert "growth_opportunities" in prediction
            assert "potential_challenges" in prediction
            assert len(prediction["growth_opportunities"]) > 0
            assert len(prediction["potential_challenges"]) > 0
            
            logger.info("✓ Test 4 passed")
        except AssertionError:
            logger.error("✗ Test 4 failed")
            all_passed = False
        
        # Test 5: Categorizing relationship dynamic
        try:
            logger.info("Test 5: Categorizing relationship dynamic")
            test_dynamics = [
                "trusted friend and ally",
                "professional mentor",
                "romantic partner",
                "sworn enemy",
                "authority figure"
            ]
            
            for dynamic in test_dynamics:
                relationship_type, relationship_subtype = self._categorize_relationship_dynamic(dynamic)
                assert relationship_type is not None
                assert relationship_subtype is not None
            
            # Test specific cases
            relationship_type, relationship_subtype = self._categorize_relationship_dynamic("trusted friend and ally")
            assert relationship_type == "personal"
            assert relationship_subtype == "friendship"
            
            relationship_type, relationship_subtype = self._categorize_relationship_dynamic("professional mentor")
            assert relationship_type == "professional"
            assert relationship_subtype == "mentorship"
            
            logger.info("✓ Test 5 passed")
        except AssertionError:
            logger.error("✗ Test 5 failed")
            all_passed = False
        
        logger.info(f"=== Test Results: {'All Passed' if all_passed else 'Some Failed'} ===")
        return all_passed


# Main entry point for running the module directly
def main():
    """
    Main entry point for testing the module
    """
    parser = argparse.ArgumentParser(description="Relationship Analyzer for Night City Stories")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--analyze", nargs=2, metavar=('ENTITY1', 'ENTITY2'),
                       help="Analyze relationship between two entities")
    parser.add_argument("--episode", default="S01E01", help="Episode for analysis (default: S01E01)")
    parser.add_argument("--dynamic", help="Categorize a relationship dynamic description")
    parser.add_argument("--narrative", help="Path to a file containing narrative text to analyze")
    args = parser.parse_args()
    
    # Create analyzer instance
    analyzer = RelationshipAnalyzer()
    
    if args.test:
        # Run tests
        analyzer.run_test()
    
    elif args.analyze:
        # Analyze relationship between two entities
        entity1, entity2 = args.analyze
        analysis = analyzer.analyze_relationship(
            entity1_name=entity1,
            entity2_name=entity2,
            episode=args.episode
        )
        
        # Print analysis results
        print(f"\nRelationship Analysis: {entity1} and {entity2}")
        print("-" * 80)
        
        if "error" in analysis:
            print(f"Error: {analysis['error']}")
            print(f"Message: {analysis['message']}")
        else:
            # Print basic information
            print(f"Relationship Type: {analysis.get('relationship_type', 'Unknown')}")
            if analysis.get('relationship_subtype'):
                print(f"Subtype: {analysis.get('relationship_subtype')}")
            
            # Print dynamics
            print("\nRelationship Dynamics:")
            for dynamic, value in analysis.get("relationship_dynamics", {}).items():
                print(f"  {dynamic.capitalize()}: {value}")
            
            # Print observed dynamics
            observed = analysis.get("observed_dynamics", {})
            if observed:
                print("\nObserved Dynamics in Narrative:")
                for dynamic, value in observed.items():
                    print(f"  {dynamic.capitalize()}: {value}")
            
            # Print communication pattern
            if analysis.get("communication_pattern"):
                print(f"\nCommunication Pattern: {analysis['communication_pattern']}")
            
            # Print stability analysis
            stability = analysis.get("stability_analysis", {})
            if stability:
                print(f"\nStability Level: {stability.get('stability_level', 'Unknown')}")
                
                if stability.get("stabilizing_factors"):
                    print("Stabilizing Factors:")
                    for factor in stability["stabilizing_factors"]:
                        print(f"  - {factor}")
                
                if stability.get("vulnerability_points"):
                    print("Vulnerability Points:")
                    for point in stability["vulnerability_points"]:
                        print(f"  - {point}")
            
            # Print development prediction
            development = analysis.get("development_prediction", {})
            if development:
                print(f"\nPredicted Trajectory: {development.get('trajectory', 'Unknown')}")
                print(f"Potential Evolution: {development.get('potential_evolution', 'Unknown')}")
                
                if development.get("growth_opportunities"):
                    print("Growth Opportunities:")
                    for opportunity in development["growth_opportunities"]:
                        print(f"  - {opportunity}")
                
                if development.get("potential_challenges"):
                    print("Potential Challenges:")
                    for challenge in development["potential_challenges"]:
                        print(f"  - {challenge}")
        
        print("-" * 80)
    
    elif args.dynamic:
        # Categorize a relationship dynamic
        relationship_type, relationship_subtype = analyzer._categorize_relationship_dynamic(args.dynamic)
        print(f"\nRelationship Dynamic: '{args.dynamic}'")
        print(f"Categorized as: {relationship_type} / {relationship_subtype}")
    
    elif args.narrative:
        # Analyze relationship in narrative text
        try:
            with open(args.narrative, 'r') as f:
                narrative_text = f.read()
            
            print("Enter the names of the two entities to analyze:")
            entity1 = input("Entity 1: ")
            entity2 = input("Entity 2: ")
            
            analysis = analyzer._analyze_relationship_in_narrative(
                entity1_name=entity1,
                entity2_name=entity2,
                narrative_text=narrative_text,
                episode=args.episode
            )
            
            print(f"\nRelationship Analysis in Narrative: {entity1} and {entity2}")
            print("-" * 80)
            
            # Print dynamics
            print("Observed Dynamics:")
            for dynamic, value in analysis.get("observed_dynamics", {}).items():
                print(f"  {dynamic.capitalize()}: {value}")
            
            # Print significant interactions
            if analysis.get("significant_interactions"):
                print("\nSignificant Interactions:")
                for i, interaction in enumerate(analysis["significant_interactions"], 1):
                    print(f"  {i}. {interaction['type'].capitalize()}: {interaction['description']}")
            
            # Print communication pattern
            if analysis.get("communication_pattern"):
                print(f"\nCommunication Pattern: {analysis['communication_pattern']}")
            
            print("-" * 80)
        except FileNotFoundError:
            print(f"Error: File not found: {args.narrative}")
    
    else:
        # Show help
        parser.print_help()

if __name__ == "__main__":
    main()
