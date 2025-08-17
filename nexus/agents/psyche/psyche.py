"""
PSYCHE - Character Psychology Utility Module

PSYCHE is responsible for automatically generating character context
for narrative generation. It pulls essential character information
based on character references in chunks.
"""

import logging
from typing import Dict, List, Optional, Any, Set
from pathlib import Path

logger = logging.getLogger("nexus.psyche")


class PSYCHE:
    """
    Character psychology utility module for automatic context generation.
    
    Auto-generates minimal character context including:
    - Character summaries for present/mentioned characters
    - Current locations for mentioned characters  
    - Emotional states for present characters
    - Relevant relationship data
    
    Can be expanded on-demand for deeper psychological analysis.
    """
    
    def __init__(self, memnon_instance):
        """
        Initialize PSYCHE with a MEMNON instance for database access.
        
        Args:
            memnon_instance: MEMNON agent instance for DB operations
        """
        self.memnon = memnon_instance
        logger.info("PSYCHE character psychology utility initialized")
    
    def generate_character_context(
        self,
        present_character_ids: List[int],
        mentioned_character_ids: List[int],
        expand_psychology: bool = False,
        include_relationships: bool = True
    ) -> Dict[str, Any]:
        """
        Generate automatic character context for narrative generation.
        
        Args:
            present_character_ids: IDs of characters present in the scene
            mentioned_character_ids: IDs of characters mentioned but not present
            expand_psychology: Whether to include deep psychological profiles
            include_relationships: Whether to include relationship data
            
        Returns:
            Dict containing character context organized by category
        """
        context = {
            "present_characters": {},
            "mentioned_characters": {},
            "relationships": [],
            "summary": ""
        }
        
        # Process present characters
        for char_id in present_character_ids:
            char_data = self._get_character_essentials(
                char_id, 
                include_emotional_state=True,
                include_current_activity=True
            )
            if char_data:
                context["present_characters"][char_id] = char_data
        
        # Process mentioned characters
        for char_id in mentioned_character_ids:
            # Skip if already in present
            if char_id not in present_character_ids:
                char_data = self._get_character_essentials(
                    char_id,
                    include_current_location=True,
                    include_current_activity=True
                )
                if char_data:
                    context["mentioned_characters"][char_id] = char_data
        
        # Get relationships if requested
        if include_relationships:
            all_char_ids = set(present_character_ids) | set(mentioned_character_ids)
            context["relationships"] = self._get_character_relationships(all_char_ids)
        
        # Add deep psychology if requested
        if expand_psychology:
            for char_id in present_character_ids:
                psych_data = self._get_character_psychology(char_id)
                if psych_data and char_id in context["present_characters"]:
                    context["present_characters"][char_id]["psychology"] = psych_data
        
        # Generate summary
        context["summary"] = self._generate_context_summary(context)
        
        return context
    
    def _get_character_essentials(
        self,
        character_id: int,
        include_emotional_state: bool = False,
        include_current_location: bool = False,
        include_current_activity: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get essential character information.
        
        Args:
            character_id: Character ID
            include_emotional_state: Include emotional_state field
            include_current_location: Include current_location field
            include_current_activity: Include current_activity field
            
        Returns:
            Character data dict or None if not found
        """
        # Build dynamic field list
        fields = ["id", "name", "summary", "appearance"]
        if include_emotional_state:
            fields.append("emotional_state")
        if include_current_location:
            fields.append("current_location")
        if include_current_activity:
            fields.append("current_activity")
        
        sql = f"""
        SELECT {', '.join(fields)}
        FROM characters
        WHERE id = {character_id}
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            logger.warning(f"Character {character_id} not found")
            return None
        
        row = result['rows'][0]
        return {field: row.get(field) for field in fields if row.get(field) is not None}
    
    def _get_character_psychology(self, character_id: int) -> Optional[Dict[str, Any]]:
        """
        Get deep psychological profile for a character.
        
        Args:
            character_id: Character ID
            
        Returns:
            Psychology data or None if not found
        """
        sql = f"""
        SELECT 
            self_concept, behavior, cognitive_framework,
            temperament, relational_style, defense_mechanisms,
            character_arc, secrets
        FROM character_psychology
        WHERE character_id = {character_id}
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            # Try to get from main character table
            fallback_sql = f"""
            SELECT personality, background, extra_data
            FROM characters
            WHERE id = {character_id}
            """
            fallback_result = self.memnon.execute_readonly_sql(fallback_sql)
            
            if fallback_result and fallback_result.get('rows'):
                row = fallback_result['rows'][0]
                return {
                    "personality": row.get("personality"),
                    "background": row.get("background"),
                    "extra_data": row.get("extra_data")
                }
            return None
        
        row = result['rows'][0]
        psych_data = {}
        
        # Include non-null JSONB fields
        for field in ['self_concept', 'behavior', 'cognitive_framework', 
                      'temperament', 'relational_style', 'defense_mechanisms',
                      'character_arc', 'secrets']:
            if row.get(field):
                psych_data[field] = row[field]
        
        return psych_data if psych_data else None
    
    def _get_character_relationships(
        self, 
        character_ids: Set[int]
    ) -> List[Dict[str, Any]]:
        """
        Get relationships between specified characters.
        
        Args:
            character_ids: Set of character IDs
            
        Returns:
            List of relationship dicts
        """
        if len(character_ids) < 2:
            return []
        
        char_list = ','.join(str(id) for id in character_ids)
        
        sql = f"""
        SELECT 
            cr.character1_id, c1.name as character1_name,
            cr.character2_id, c2.name as character2_name,
            cr.relationship_type, cr.emotional_valence,
            cr.dynamic, cr.recent_events
        FROM character_relationships cr
        JOIN characters c1 ON cr.character1_id = c1.id
        JOIN characters c2 ON cr.character2_id = c2.id
        WHERE cr.character1_id IN ({char_list})
          AND cr.character2_id IN ({char_list})
        ORDER BY cr.character1_id, cr.character2_id
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            return []
        
        relationships = []
        for row in result['rows']:
            relationships.append({
                "characters": [
                    {"id": row['character1_id'], "name": row['character1_name']},
                    {"id": row['character2_id'], "name": row['character2_name']}
                ],
                "type": row.get('relationship_type'),
                "emotional_valence": row.get('emotional_valence'),
                "dynamic": row.get('dynamic'),
                "recent_events": row.get('recent_events')
            })
        
        return relationships
    
    def _generate_context_summary(self, context: Dict[str, Any]) -> str:
        """
        Generate a brief summary of the character context.
        
        Args:
            context: The full character context dict
            
        Returns:
            Summary string
        """
        present_count = len(context.get("present_characters", {}))
        mentioned_count = len(context.get("mentioned_characters", {}))
        relationship_count = len(context.get("relationships", []))
        
        summary_parts = []
        
        if present_count > 0:
            present_names = [c.get("name", "Unknown") for c in context["present_characters"].values()]
            summary_parts.append(f"Present: {', '.join(present_names[:3])}" + 
                                 (" and others" if present_count > 3 else ""))
        
        if mentioned_count > 0:
            mentioned_names = [c.get("name", "Unknown") for c in context["mentioned_characters"].values()]
            summary_parts.append(f"Mentioned: {', '.join(mentioned_names[:3])}" +
                                 (" and others" if mentioned_count > 3 else ""))
        
        if relationship_count > 0:
            summary_parts.append(f"{relationship_count} relationships tracked")
        
        return " | ".join(summary_parts) if summary_parts else "No character context"
    
    def analyze_chunk_characters(self, chunk_id: int) -> Dict[str, Any]:
        """
        Analyze character references in a specific chunk.
        
        Args:
            chunk_id: Narrative chunk ID
            
        Returns:
            Dict with present and mentioned character IDs
        """
        sql = f"""
        SELECT 
            character_id,
            reference
        FROM chunk_character_references
        WHERE chunk_id = {chunk_id}
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        present = []
        mentioned = []
        
        if result and result.get('rows'):
            for row in result['rows']:
                if row.get('reference') == 'present':
                    present.append(row['character_id'])
                elif row.get('reference') == 'mentioned':
                    mentioned.append(row['character_id'])
        
        return {
            "chunk_id": chunk_id,
            "present_character_ids": present,
            "mentioned_character_ids": mentioned
        }
    
    def get_character_list(self) -> List[Dict[str, Any]]:
        """
        Get minimal list of all characters (for Apex AI reference).
        
        Returns:
            List of dicts with character id and name
        """
        sql = """
        SELECT id, name
        FROM characters
        ORDER BY id
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            return []
        
        return [{"id": row['id'], "name": row['name']} for row in result['rows']]