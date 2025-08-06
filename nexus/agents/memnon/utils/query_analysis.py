"""
Query Analysis Module for MEMNON

Provides functionality for analyzing and classifying user queries to determine the
appropriate search strategy and processing approach.
"""

import logging
import re
from typing import Dict, List, Any, Optional

logger = logging.getLogger("nexus.memnon.query_analysis")

class QueryAnalyzer:
    """
    Analyzes and classifies user queries to determine query intent and type.
    """
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        """
        Initialize the QueryAnalyzer
        
        Args:
            settings: Optional settings dictionary for customization
        """
        self.settings = settings or {}
        
        # Load custom patterns from settings if available
        self.character_patterns = self.settings.get("character_patterns", [
            r"\b(alex|emilia|pete|alina|dr\. nyati)\b",  # Character names
            r"\bwho is\b",
            r"\bcharacter\b",
            r"\bperson\b"
        ])
        
        self.location_patterns = self.settings.get("location_patterns", [
            r"\bwhere\b",
            r"\blocation\b",
            r"\bplace\b",
            r"\bcity\b",
            r"\bdistrict\b",
            r"\barea\b"
        ])
        
        self.event_patterns = self.settings.get("event_patterns", [
            r"\bwhat happened\b",
            r"\bevent\b",
            r"\boccurred\b",
            r"\btook place\b",
            r"\bwhen did\b"
        ])
        
        self.relationship_patterns = self.settings.get("relationship_patterns", [
            r"\brelationship\b",
            r"\bfeel about\b",
            r"\bthink about\b",
            r"\bfeel towards\b",
            r"\bthink of\b"
        ])
        
        self.theme_patterns = self.settings.get("theme_patterns", [
            r"\btheme\b",
            r"\bmotif\b",
            r"\bsymbolism\b",
            r"\bmeaning\b"
        ])
        
        # Compile patterns for efficiency
        self._compile_patterns()
        
        logger.info("QueryAnalyzer initialized")
    
    def _compile_patterns(self):
        """Compile regex patterns for efficiency."""
        self.compiled_character_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.character_patterns]
        self.compiled_location_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.location_patterns]
        self.compiled_event_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.event_patterns]
        self.compiled_relationship_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.relationship_patterns]
        self.compiled_theme_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.theme_patterns]
    
    def analyze_query(self, query_text: str) -> Dict[str, Any]:
        """
        Analyze a query to determine its type and characteristics.
        
        Args:
            query_text: The query string to analyze
            
        Returns:
            Dictionary with query analysis results
        """
        # Simple rule-based analysis
        query_info = {
            "text": query_text,
            "type": "general"  # Default
        }
        
        # Check for character-focused query
        for pattern in self.compiled_character_patterns:
            if pattern.search(query_text):
                query_info["type"] = "character"
                break
        
        # Check for location-focused query
        for pattern in self.compiled_location_patterns:
            if pattern.search(query_text):
                query_info["type"] = "location"
                break
        
        # Check for event-focused query
        for pattern in self.compiled_event_patterns:
            if pattern.search(query_text):
                query_info["type"] = "event"
                break
        
        # Check for relationship-focused query
        for pattern in self.compiled_relationship_patterns:
            if pattern.search(query_text):
                query_info["type"] = "relationship"
                break
        
        # Check for theme-focused query
        for pattern in self.compiled_theme_patterns:
            if pattern.search(query_text):
                query_info["type"] = "theme"
                break
        
        # Add confidence score (placeholder for future ML-based implementation)
        query_info["confidence"] = 0.8
        
        # Add entities (placeholder for future NER implementation)
        query_info["entities"] = []
        
        return query_info
    
    def is_temporal_query(self, query_text: str) -> bool:
        """
        Determine if a query has temporal aspects.
        
        Args:
            query_text: The query string to analyze
            
        Returns:
            Boolean indicating if the query has temporal aspects
        """
        # Simple rule-based temporal detection
        temporal_patterns = [
            r"\b(before|after|during|when|while|since|until|early|earlier|late|later)\b",
            r"\b(first|initial|initial|beginning|start|origin|genesis|inception)\b",
            r"\b(recent|latest|newest|current|last|now|ongoing|present|final)\b",
            r"\b(then|next|following|subsequently|afterward|previously)\b"
        ]
        
        for pattern in temporal_patterns:
            if re.search(pattern, query_text, re.IGNORECASE):
                return True
        
        return False
    
    def extract_entities(self, query_text: str) -> List[Dict[str, Any]]:
        """
        Extract named entities from a query.
        
        Args:
            query_text: The query string to analyze
            
        Returns:
            List of dictionaries with entity information
        """
        # Placeholder for future NER implementation
        # In a real implementation, this would use a proper NER model
        entities = []
        
        # Simple regex-based character detection
        character_names = ["Alex", "Emilia", "Pete", "Alina", "Dr. Nyati"]
        for name in character_names:
            if re.search(r'\b' + re.escape(name) + r'\b', query_text, re.IGNORECASE):
                entities.append({
                    "text": name,
                    "type": "CHARACTER",
                    "start": query_text.lower().find(name.lower()),
                    "end": query_text.lower().find(name.lower()) + len(name)
                })
        
        return entities 