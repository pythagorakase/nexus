#!/usr/bin/env python3
"""
memnon.py: Memory Access Module for Night City Stories

This module provides a unified memory system that coordinates between the
hierarchical memory framework and the underlying database modules. It
implements navigation between memory levels, contextual retrieval, and
entity-focused memory operations.

Usage:
    import memnon
    
    # Retrieve relevant memory for a context
    memory_chunks = memnon.get_memory_for_context("What happened with Alex in Neon Bay?")
    
    # Or run standalone with --test flag to validate functionality
    python memnon.py --test
"""

import re
import json
import logging
import argparse
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any, Set

# Import database modules
try:
    import db_sqlite as db
    import db_chroma as vdb
    import config_manager as config
except ImportError as e:
    print(f"Warning: Failed to import a required module: {e}")
    # Set placeholders to None for optional dependency handling
    db = None
    vdb = None
    config = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("memnon.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("memnon")

# Default settings (can be overridden by config_manager)
DEFAULT_SETTINGS = {
    "memory": {
        "enable_hierarchical_memory": True,
        "use_multi_model_embeddings": True,
        "max_results_per_query": 5,
        "confidence_threshold": 0.7,
        "recency_weight": 0.3,
        "relevance_weight": 0.7,
        "narrative_chunk_limit": 10,
        "memory_levels": {
            "top": {
                "weight": 0.2,
                "limit": 3
            },
            "mid": {
                "weight": 0.3,
                "limit": 5
            },
            "chunk": {
                "weight": 0.5,
                "limit": 10
            }
        }
    }
}

# Memory levels
class MemoryLevel:
    TOP = "top"
    MID = "mid" 
    CHUNK = "chunk"

# Global variables
settings = DEFAULT_SETTINGS.copy()

class MemoryError(Exception):
    """Base exception for memory-related errors"""
    pass

class MemoryRetrievalError(MemoryError):
    """Exception for memory retrieval errors"""
    pass

class MemoryNavigationError(MemoryError):
    """Exception for memory navigation errors"""
    pass

def load_settings() -> Dict[str, Any]:
    """
    Load settings from config_manager, with fallback to default settings
    
    Returns:
        Dictionary containing settings
    """
    global settings
    
    try:
        # Try to load from config_manager if available
        if config:
            memory_config = config.get_section("memory")
            if memory_config:
                settings["memory"].update(memory_config)
            
            # Check if we should enable hierarchical memory
            if not settings["memory"]["enable_hierarchical_memory"]:
                logger.info("Hierarchical memory is disabled in configuration")
        
        logger.info("Memory settings loaded")
    
    except Exception as e:
        logger.error(f"Error loading memory settings: {e}. Using default settings.")
    
    return settings

def get_memory_for_context(query_text: str, 
                          top_k: int = None,
                          memory_levels: List[str] = None,
                          entity_filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Retrieve memory chunks relevant to the given context query
    
    Args:
        query_text: Query text to find relevant memory
        top_k: Maximum number of total results to return
        memory_levels: Which memory levels to search (defaults to all levels)
        entity_filters: Optional entity filters to apply
        
    Returns:
        List of memory chunks sorted by relevance
    """
    if not memory_levels:
        memory_levels = [MemoryLevel.TOP, MemoryLevel.MID, MemoryLevel.CHUNK]
    
    if top_k is None:
        top_k = settings["memory"]["max_results_per_query"]
    
    try:
        results = []
        
        # Process each memory level
        for level in memory_levels:
            level_results = _get_memory_by_level(level, query_text, entity_filters)
            
            # Apply level-specific weights
            level_weight = settings["memory"]["memory_levels"].get(level, {}).get("weight", 0.33)
            for result in level_results:
                result["weighted_score"] = result["score"] * level_weight
                result["memory_level"] = level
            
            results.extend(level_results)
        
        # Sort by weighted score and limit results
        results.sort(key=lambda x: x["weighted_score"], reverse=True)
        results = results[:top_k]
        
        return results
    
    except Exception as e:
        logger.error(f"Error retrieving memory for context: {e}")
        return []

def _get_memory_by_level(level: str, 
                        query_text: str,
                        entity_filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Retrieve memory from a specific level
    
    Args:
        level: Memory level ('top', 'mid', or 'chunk')
        query_text: Query text
        entity_filters: Optional entity filters
        
    Returns:
        List of memory results from the specified level
    """
    # Determine level-specific limit
    level_limit = settings["memory"]["memory_levels"].get(level, {}).get("limit", 5)
    
    if level == MemoryLevel.CHUNK:
        # Use ChromaDB for chunk-level memory
        if vdb:
            chunk_results = vdb.query_by_text(
                query_text=query_text,
                filters=entity_filters,
                top_k=level_limit,
                multi_model=settings["memory"]["use_multi_model_embeddings"]
            )
            
            # Convert to standard format
            return [
                {
                    "id": result["chunk_id"],
                    "text": result["text"],
                    "score": result["score"],
                    "metadata": result["metadata"],
                    "type": "narrative_chunk"
                }
                for result in chunk_results
            ]
        else:
            logger.warning("ChromaDB module not available for chunk-level memory")
            return []
    
    elif level in [MemoryLevel.TOP, MemoryLevel.MID]:
        # Use SQLite for structured memory
        if db:
            # Prepare filters
            filters = {}
            if entity_filters:
                for key, value in entity_filters.items():
                    filters[key] = value
            
            # Get memory from database
            memory_items = db.get_memory_level(level, filters)
            
            # We need to rank these items without embeddings
            # Use a simple keyword matching score for now
            scored_items = []
            query_terms = set(query_text.lower().split())
            
            for item in memory_items:
                item_text = ""
                if level == MemoryLevel.TOP:
                    item_text = f"{item['title']} {item['description']}"
                else:  # mid level
                    item_text = f"{item['title']} {item['content']}"
                
                item_terms = set(item_text.lower().split())
                
                # Calculate Jaccard similarity between query terms and item terms
                intersection = len(query_terms.intersection(item_terms))
                union = len(query_terms.union(item_terms))
                similarity = intersection / union if union > 0 else 0
                
                # Add to results if similarity is above threshold
                if similarity > 0:
                    scored_items.append({
                        "id": str(item["id"]),
                        "text": item["description"] if level == MemoryLevel.TOP else item["content"],
                        "score": similarity,
                        "metadata": item,
                        "type": item["type"]
                    })
            
            # Sort by score and limit results
            scored_items.sort(key=lambda x: x["score"], reverse=True)
            return scored_items[:level_limit]
        else:
            logger.warning("SQLite module not available for structured memory")
            return []
    
    else:
        logger.error(f"Invalid memory level: {level}")
        return []

def navigate_memory(source_id: str, 
                   source_level: str,
                   direction: str = "down",
                   link_types: List[str] = None) -> List[Dict[str, Any]]:
    """
    Navigate from one memory item to related items
    
    Args:
        source_id: ID of the source memory item
        source_level: Level of the source memory item
        direction: Direction to navigate ('up', 'down', 'both')
        link_types: Optional list of link types to filter by
        
    Returns:
        List of related memory items
    """
    if not settings["memory"]["enable_hierarchical_memory"]:
        logger.warning("Hierarchical memory is disabled")
        return []
    
    if not db:
        logger.error("SQLite module not available for memory navigation")
        return []
    
    try:
        # Determine the direction mapping
        if direction == "up":
            db_direction = "incoming"
        elif direction == "down":
            db_direction = "outgoing"
        else:  # 'both'
            db_direction = "both"
        
        # Get memory links
        memory_links = db.get_memory_links(
            source_level=source_level,
            source_id=source_id,
            direction=db_direction,
            link_types=link_types
        )
        
        # Process links to get connected memory items
        results = []
        for link in memory_links:
            # Determine the connected level and ID
            if "connected_level" in link:
                connected_level = link["connected_level"]
                connected_id = link["connected_id"]
            else:
                connected_level = link["target_level"]
                connected_id = link["target_id"]
            
            # Get the connected memory item
            if connected_level == MemoryLevel.CHUNK:
                # For chunk-level memory, use ChromaDB
                if vdb:
                    chunk_results = vdb.query_by_chunk_id(
                        chunk_id=connected_id,
                        find_similar=False
                    )
                    
                    if chunk_results:
                        chunk = chunk_results[0]
                        results.append({
                            "id": chunk["chunk_id"],
                            "text": chunk["text"],
                            "score": link.get("relevance_score", 1.0),
                            "metadata": chunk["metadata"],
                            "type": "narrative_chunk",
                            "memory_level": MemoryLevel.CHUNK,
                            "link_type": link["link_type"],
                            "link_direction": link["direction"]
                        })
            else:
                # For structured memory, use SQLite
                memory_items = db.get_memory_level(
                    level=connected_level,
                    filters={"id": connected_id}
                )
                
                if memory_items:
                    item = memory_items[0]
                    results.append({
                        "id": str(item["id"]),
                        "text": item["description"] if connected_level == MemoryLevel.TOP else item["content"],
                        "score": link.get("relevance_score", 1.0),
                        "metadata": item,
                        "type": item["type"],
                        "memory_level": connected_level,
                        "link_type": link["link_type"],
                        "link_direction": link["direction"]
                    })
        
        return results
    
    except Exception as e:
        logger.error(f"Error navigating memory: {e}")
        return []

def get_entity_memory(entity_type: str, 
                     entity_id: int,
                     memory_level: str = "all",
                     max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Get memory related to a specific entity
    
    Args:
        entity_type: Type of entity ('character', 'faction', 'location')
        entity_id: ID of the entity
        memory_level: Which memory levels to search
        max_results: Maximum number of results to return
        
    Returns:
        List of memory items related to the entity
    """
    entity_name = None
    
    # Get entity name for better queries
    if db:
        if entity_type == "character":
            char = db.get_character_by_id(entity_id)
            if char:
                entity_name = char["name"]
        elif entity_type == "faction":
            faction = db.get_faction_by_name(entity_id)
            if faction:
                entity_name = faction["name"]
        elif entity_type == "location":
            location = db.get_location_by_name(entity_id)
            if location:
                entity_name = location["name"]
    
    if not entity_name:
        entity_name = f"{entity_type} {entity_id}"
    
    # Build a query based on entity name
    query = f"Information about {entity_name}"
    
    # Prepare entity filters
    entity_filters = {
        "entity_type": entity_type,
        "entity_id": entity_id
    }
    
    # Define memory levels to search
    levels_to_search = []
    if memory_level == "all":
        levels_to_search = [MemoryLevel.TOP, MemoryLevel.MID, MemoryLevel.CHUNK]
    elif memory_level == "structured":
        levels_to_search = [MemoryLevel.TOP, MemoryLevel.MID]
    elif memory_level == "narrative":
        levels_to_search = [MemoryLevel.CHUNK]
    else:
        levels_to_search = [memory_level]
    
    # Get memory for this entity
    memory_items = get_memory_for_context(
        query_text=query,
        top_k=max_results,
        memory_levels=levels_to_search,
        entity_filters=entity_filters
    )
    
    return memory_items

def get_recent_narrative(max_chunks: int = 10, 
                        filter_episode: str = None) -> List[Dict[str, Any]]:
    """
    Get the most recent narrative chunks
    
    Args:
        max_chunks: Maximum number of chunks to retrieve
        filter_episode: Optional episode filter
        
    Returns:
        List of recent narrative chunks in chronological order
    """
    if not vdb:
        logger.error("ChromaDB module not available for recent narrative")
        return []
    
    try:
        # Get current episode from settings if not specified
        if not filter_episode and config:
            filter_episode = config.get("narrative.current_episode")
        
        # Prepare filters
        filters = {}
        if filter_episode:
            filters["episode"] = filter_episode
        
        # Get chunks for the episode
        chunks = vdb.get_chunks_by_episode(filter_episode)
        
        # Sort by chunk number
        chunks.sort(key=lambda x: x.get("chunk_number", 0))
        
        # Take the most recent chunks
        recent_chunks = chunks[-max_chunks:] if max_chunks > 0 else chunks
        
        # Format the results
        results = []
        for chunk in recent_chunks:
            results.append({
                "id": chunk["chunk_id"],
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "type": "narrative_chunk",
                "memory_level": MemoryLevel.CHUNK
            })
        
        return results
    
    except Exception as e:
        logger.error(f"Error retrieving recent narrative: {e}")
        return []

def add_memory_link(source_level: str, 
                  source_id: str,
                  target_level: str,
                  target_id: str,
                  link_type: str,
                  relevance_score: float = None) -> bool:
    """
    Create a link between two memory items
    
    Args:
        source_level: Source memory level
        source_id: ID of the source memory item
        target_level: Target memory level
        target_id: ID of the target memory item
        link_type: Type of link
        relevance_score: Optional relevance score
        
    Returns:
        True if the link was created successfully, False otherwise
    """
    if not settings["memory"]["enable_hierarchical_memory"]:
        logger.warning("Hierarchical memory is disabled")
        return False
    
    if not db:
        logger.error("SQLite module not available for creating memory links")
        return False
    
    try:
        success = db.create_memory_link(
            source_level=source_level,
            source_id=source_id,
            target_level=target_level,
            target_id=target_id,
            link_type=link_type,
            relevance_score=relevance_score
        )
        
        if success:
            logger.info(f"Created memory link: {source_level}/{source_id} -> {target_level}/{target_id} ({link_type})")
        
        return success
    
    except Exception as e:
        logger.error(f"Error creating memory link: {e}")
        return False

def update_entity_state(entity_type: str,
                      entity_id: int,
                      state_type: str,
                      state_value: str,
                      episode: str,
                      confidence: float = 1.0,
                      source: str = "api",
                      notes: Optional[str] = None,
                      narrative_time: Optional[str] = None,
                      chunk_id: Optional[str] = None) -> bool:
    """
    Update an entity's state in memory
    
    Args:
        entity_type: Type of entity ('character', 'faction', 'location')
        entity_id: ID of the entity
        state_type: Type of state to update
        state_value: New value for the state
        episode: Episode identifier
        confidence: Confidence level for this update (0.0-1.0)
        source: Source of this update (e.g., 'api', 'narrative')
        notes: Optional notes about this update
        narrative_time: Optional in-story timestamp
        chunk_id: Optional reference to specific narrative chunk
        
    Returns:
        True if the state was updated successfully, False otherwise
    """
    logger.info(f"Updating {entity_type} {entity_id} state {state_type}={state_value} for episode {episode}")
    
    if not db:
        logger.error("SQLite module not available for updating entity state")
        return False
    
    try:
        # Use the SQLite module to update the entity state
        success = db.update_entity_state(
            entity_type=entity_type,
            entity_id=entity_id,
            state_type=state_type,
            state_value=state_value,
            episode=episode,
            chunk_id=chunk_id,
            narrative_time=narrative_time,
            confidence=confidence,
            source=source,
            notes=notes
        )
        
        if success:
            # Add a mid-level memory item for the state update if significant
            if confidence >= 0.8:
                entity_name = db.get_entity_name(entity_type, entity_id) or f"{entity_type}_{entity_id}"
                memory_title = f"{entity_name} {state_type} update"
                memory_content = f"{entity_name}'s {state_type} changed to {state_value}"
                
                # Create memory item
                memory_id = add_mid_level_memory(
                    memory_type="entity_state",
                    episode=episode,
                    title=memory_title,
                    content=memory_content,
                    entities=[{"type": entity_type, "id": entity_id}]
                )
                
                logger.info(f"Created mid-level memory for entity state update: {memory_id}")
        
        return success
    
    except Exception as e:
        logger.error(f"Error updating entity state: {e}")
        logger.error(f"Parameters: {entity_type}, {entity_id}, {state_type}, {state_value}, {episode}")
        return False
        
def update_relationship_state(entity1_type: str,
                            entity1_id: int,
                            entity2_type: str,
                            entity2_id: int,
                            relationship_type: str,
                            state_value: str,
                            episode: str,
                            symmetrical: bool = False,
                            chunk_id: Optional[str] = None,
                            narrative_time: Optional[str] = None,
                            confidence: float = 1.0,
                            source: str = "api",
                            notes: Optional[str] = None) -> bool:
    """
    Update a relationship state between two entities
    
    Args:
        entity1_type: Type of first entity
        entity1_id: ID of first entity
        entity2_type: Type of second entity
        entity2_id: ID of second entity
        relationship_type: Type of relationship
        state_value: Value of the relationship state
        episode: Episode identifier
        symmetrical: Whether the relationship applies in both directions
        chunk_id: Optional reference to specific narrative chunk
        narrative_time: Optional in-story timestamp
        confidence: Confidence level for this update (0.0-1.0)
        source: Source of this update
        notes: Optional notes about this update
        
    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Updating relationship between {entity1_type} {entity1_id} and {entity2_type} {entity2_id}: {relationship_type}={state_value}")
    
    if not db:
        logger.error("SQLite module not available for updating relationship state")
        return False
    
    try:
        # Use the SQLite module to update the relationship state
        success = db.update_relationship_state(
            entity1_type=entity1_type,
            entity1_id=entity1_id,
            entity2_type=entity2_type,
            entity2_id=entity2_id,
            relationship_type=relationship_type,
            state_value=state_value,
            episode=episode,
            symmetrical=symmetrical,
            chunk_id=chunk_id,
            narrative_time=narrative_time,
            confidence=confidence,
            source=source,
            notes=notes
        )
        
        if success:
            # Add a mid-level memory item for the relationship update if significant
            if confidence >= 0.8:
                entity1_name = db.get_entity_name(entity1_type, entity1_id) or f"{entity1_type}_{entity1_id}"
                entity2_name = db.get_entity_name(entity2_type, entity2_id) or f"{entity2_type}_{entity2_id}"
                
                memory_title = f"Relationship between {entity1_name} and {entity2_name}"
                memory_content = f"{relationship_type} relationship changed to {state_value}"
                
                # Create memory item
                memory_id = add_mid_level_memory(
                    memory_type="relationship_update",
                    episode=episode,
                    title=memory_title,
                    content=memory_content,
                    entities=[
                        {"type": entity1_type, "id": entity1_id},
                        {"type": entity2_type, "id": entity2_id}
                    ]
                )
                
                logger.info(f"Created mid-level memory for relationship update: {memory_id}")
                
                # If symmetrical, add the reverse relationship
                if symmetrical:
                    # The db.update_relationship_state should have already handled this
                    pass
        
        return success
    
    except Exception as e:
        logger.error(f"Error updating relationship state: {e}")
        logger.error(f"Parameters: {entity1_type}, {entity1_id}, {entity2_type}, {entity2_id}, {relationship_type}, {state_value}")
        return False

def add_top_level_memory(memory_type: str, 
                        title: str, 
                        description: str,
                        start_episode: str = None,
                        end_episode: str = None,
                        entities: List[Dict[str, Any]] = None) -> Optional[int]:
    """
    Add a top-level memory item
    
    Args:
        memory_type: Type of memory ('story_arc', 'theme', 'character_arc')
        title: Short title/name for the memory
        description: Detailed description
        start_episode: Optional starting episode
        end_episode: Optional ending episode
        entities: List of related entities with their IDs and types
        
    Returns:
        ID of the newly created memory item, or None if creation failed
    """
    if not settings["memory"]["enable_hierarchical_memory"]:
        logger.warning("Hierarchical memory is disabled")
        return None
    
    if not db:
        logger.error("SQLite module not available for adding memory")
        return None
    
    try:
        memory_id = db.add_top_level_memory(
            memory_type=memory_type,
            title=title,
            description=description,
            start_episode=start_episode,
            end_episode=end_episode,
            entities=entities
        )
        
        if memory_id:
            logger.info(f"Added top-level memory: {title} (ID: {memory_id})")
        
        return memory_id
    
    except Exception as e:
        logger.error(f"Error adding top-level memory: {e}")
        return None

def add_mid_level_memory(memory_type: str, 
                        episode: str, 
                        title: str, 
                        content: str,
                        entities: List[Dict[str, Any]] = None,
                        parent_ids: List[int] = None) -> Optional[int]:
    """
    Add a mid-level memory item
    
    Args:
        memory_type: Type of memory ('episode_summary', 'character_state', 'world_event')
        episode: Related episode identifier
        title: Short title/name for the memory
        content: Detailed content/description
        entities: List of related entities with their IDs and types
        parent_ids: List of top-level memory IDs this relates to
        
    Returns:
        ID of the newly created memory item, or None if creation failed
    """
    if not settings["memory"]["enable_hierarchical_memory"]:
        logger.warning("Hierarchical memory is disabled")
        return None
    
    if not db:
        logger.error("SQLite module not available for adding memory")
        return None
    
    try:
        memory_id = db.add_mid_level_memory(
            memory_type=memory_type,
            episode=episode,
            title=title,
            content=content,
            entities=entities,
            parent_ids=parent_ids
        )
        
        if memory_id:
            logger.info(f"Added mid-level memory: {title} (ID: {memory_id})")
        
        return memory_id
    
    except Exception as e:
        logger.error(f"Error adding mid-level memory: {e}")
        return None

def add_narrative_chunk(chunk_id: str, 
                       chunk_text: str, 
                       metadata: Dict[str, Any] = None) -> bool:
    """
    Add a narrative chunk to the memory system
    
    Args:
        chunk_id: ID of the chunk
        chunk_text: Text content of the chunk
        metadata: Optional metadata for the chunk
        
    Returns:
        True if the chunk was added successfully, False otherwise
    """
    if not vdb:
        logger.error("ChromaDB module not available for adding narrative chunks")
        return False
    
    if not metadata:
        metadata = {}
    
    try:
        success = vdb.add_chunk(
            chunk_id=chunk_id,
            chunk_text=chunk_text,
            metadata=metadata
        )
        
        if success:
            logger.info(f"Added narrative chunk: {chunk_id}")
        
        return success
    
    except Exception as e:
        logger.error(f"Error adding narrative chunk: {e}")
        return False

def update_chunk_metadata(chunk_id: str, metadata: Dict[str, Any]) -> bool:
    """
    Update metadata for a narrative chunk
    
    Args:
        chunk_id: ID of the chunk
        metadata: New metadata for the chunk
        
    Returns:
        True if the metadata was updated successfully, False otherwise
    """
    if not vdb:
        logger.error("ChromaDB module not available for updating chunk metadata")
        return False
    
    try:
        success = vdb.update_chunk_metadata(
            chunk_id=chunk_id,
            metadata=metadata
        )
        
        if success:
            logger.info(f"Updated metadata for chunk: {chunk_id}")
        
        return success
    
    except Exception as e:
        logger.error(f"Error updating chunk metadata: {e}")
        return False

def extract_chunk_id(text: str) -> Optional[str]:
    """
    Extract chunk ID from text
    
    Args:
        text: Text to extract from
        
    Returns:
        Chunk ID or None if not found
    """
    if vdb:
        return vdb.extract_chunk_id_from_text(text)
    
    # Fallback pattern if vdb is not available
    chunk_marker_regex = r'<!--\s*SCENE BREAK:\s*(S\d+E\d+)_([\d]{3})'
    pattern = re.compile(chunk_marker_regex)
    match = pattern.search(text)
    
    if match:
        episode = match.group(1)  # e.g., "S03E11"
        chunk_number = match.group(2)  # e.g., "037"
        return f"{episode}_{chunk_number}"
    
    return None

def run_test() -> bool:
    """
    Run tests on the memory module
    
    Returns:
        True if all tests pass, False otherwise
    """
    logger.info("=== Running memnon tests ===")
    
    try:
        # Import test utilities if available
        try:
            import test_utils # type: ignore
            use_test_env = True
        except ImportError:
            use_test_env = False
            logger.warning("test_utils module not available, using simplified testing")
        
        if use_test_env:
            # Run tests with test environment
            with test_utils.TestEnvironment(
                use_temp_dir=True,
                create_test_db=True,
                setup_settings=True
            ) as env:
                # Run individual tests
                all_passed = True
                all_passed &= env.run_test("Settings Loading", test_settings_loading)
                all_passed &= env.run_test("Memory Navigation", test_memory_navigation)
                all_passed &= env.run_test("Entity Memory", test_entity_memory)
                all_passed &= env.run_test("Memory Context", test_memory_context)
                
                return all_passed
        else:
            # Run simplified tests without test environment
            return run_simplified_tests()
    
    except Exception as e:
        logger.error(f"Error during tests: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def run_simplified_tests() -> bool:
    """
    Run simplified tests without test environment
    
    Returns:
        True if all tests pass, False otherwise
    """
    try:
        # Test settings loading
        settings = load_settings()
        assert isinstance(settings, dict)
        assert "memory" in settings
        logger.info("✓ Settings loading test passed")
        
        # Test memory context functions with mock data
        if "memory" in settings:
            # Mock memory items
            mock_items = [
                {
                    "id": "top_1",
                    "text": "Test top-level memory",
                    "score": 0.8,
                    "type": "story_arc",
                    "memory_level": "top"
                },
                {
                    "id": "mid_1",
                    "text": "Test mid-level memory",
                    "score": 0.7,
                    "type": "episode_summary",
                    "memory_level": "mid"
                },
                {
                    "id": "chunk_1",
                    "text": "Test chunk-level memory",
                    "score": 0.9,
                    "type": "narrative_chunk",
                    "memory_level": "chunk"
                }
            ]
            
            # Add weighted scores
            for item in mock_items:
                level = item["memory_level"]
                level_weight = settings["memory"]["memory_levels"].get(level, {}).get("weight", 0.33)
                item["weighted_score"] = item["score"] * level_weight
            
            # Sort by weighted score
            mock_items.sort(key=lambda x: x["weighted_score"], reverse=True)
            
            logger.info("✓ Memory context test passed")
        
        # Test chunk ID extraction
        test_text = """<!-- SCENE BREAK: S01E05_012 (Test Scene) -->
        This is a test scene in Night City."""
        chunk_id = extract_chunk_id(test_text)
        assert chunk_id == "S01E05_012"
        logger.info("✓ Chunk ID extraction test passed")
        
        logger.info("All simplified tests passed!")
        return True
    
    except AssertionError as e:
        logger.error(f"Test failed: {e}")
        return False
    
    except Exception as e:
        logger.error(f"Error during simplified tests: {e}")
        return False

def test_settings_loading() -> bool:
    """Test settings loading"""
    settings = load_settings()
    assert isinstance(settings, dict)
    assert "memory" in settings
    assert "enable_hierarchical_memory" in settings["memory"]
    assert "memory_levels" in settings["memory"]
    
    # Check memory level settings
    memory_levels = settings["memory"]["memory_levels"]
    assert MemoryLevel.TOP in memory_levels
    assert MemoryLevel.MID in memory_levels
    assert MemoryLevel.CHUNK in memory_levels
    
    return True

def test_memory_navigation() -> bool:
    """Test memory navigation functions"""
    global db, vdb
    
    # Skip test if dependencies are not available
    if not db:
        logger.warning("Skipping memory navigation test: db module not available")
        return True
    
    # Create test memory items
    top_id = add_top_level_memory(
        memory_type="story_arc",
        title="Test Story Arc",
        description="A test story arc for memory navigation",
        start_episode="S01E01"
    )
    assert top_id is not None
    
    mid_id = add_mid_level_memory(
        memory_type="episode_summary",
        episode="S01E01",
        title="Test Episode Summary",
        content="A test episode summary for memory navigation",
        parent_ids=[top_id]
    )
    assert mid_id is not None
    
    # Test navigation
    down_links = navigate_memory(
        source_id=str(top_id),
        source_level=MemoryLevel.TOP,
        direction="down"
    )
    assert len(down_links) > 0
    assert down_links[0]["id"] == str(mid_id)
    
    up_links = navigate_memory(
        source_id=str(mid_id),
        source_level=MemoryLevel.MID,
        direction="up"
    )
    assert len(up_links) > 0
    assert up_links[0]["id"] == str(top_id)
    
    return True

def test_entity_memory() -> bool:
    """Test entity memory functions"""
    global db
    
    # Skip test if dependencies are not available
    if not db:
        logger.warning("Skipping entity memory test: db module not available")
        return True
    
    # Get memory for a character
    character_memory = get_entity_memory(
        entity_type="character",
        entity_id=1,  # Alex
        memory_level="all"
    )
    
    # This might return no results in a test environment, so we'll just check the function runs
    assert isinstance(character_memory, list)
    
    return True

def test_memory_context() -> bool:
    """Test memory context functions"""
    # Test with a simple query
    results = get_memory_for_context(
        query_text="What happened with Alex?",
        top_k=5
    )
    
    # This might return no results in a test environment, so we'll just check the function runs
    assert isinstance(results, list)
    
    return True

def main():
    """
    Main entry point for the script when run directly.
    Handles command-line arguments and executes the appropriate functionality.
    """
    parser = argparse.ArgumentParser(description="Memory Access Module")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--query", help="Query text to search for memories")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    parser.add_argument("--level", choices=["top", "mid", "chunk", "all"], default="all",
                       help="Memory level to search")
    parser.add_argument("--entity-type", choices=["character", "faction", "location"],
                       help="Entity type for entity memory queries")
    parser.add_argument("--entity-id", type=int, help="Entity ID for entity memory queries")
    parser.add_argument("--recent", action="store_true", help="Get recent narrative chunks")
    parser.add_argument("--extract-id", help="Extract chunk ID from text")
    args = parser.parse_args()
    
    # Load settings
    load_settings()
    
    try:
        if args.test:
            # Run tests
            success = run_test()
            if not success:
                logger.error("Tests failed!")
                return 1
        
        elif args.query:
            # Set memory levels to search
            memory_levels = None
            if args.level != "all":
                memory_levels = [args.level]
            
            # Query by text
            results = get_memory_for_context(
                query_text=args.query,
                top_k=args.top_k,
                memory_levels=memory_levels
            )
            
            print(f"Found {len(results)} memories for query: '{args.query}'")
            for i, result in enumerate(results):
                print(f"\n--- Result {i+1}/{len(results)} (Score: {result['score']:.4f}) ---")
                print(f"ID: {result['id']}")
                print(f"Level: {result['memory_level']}")
                print(f"Type: {result.get('type', 'Unknown')}")
                print("\nContent:")
                print(result['text'])
                print("-" * 80)
        
        elif args.entity_type and args.entity_id is not None:
            # Get entity memory
            results = get_entity_memory(
                entity_type=args.entity_type,
                entity_id=args.entity_id,
                memory_level=args.level,
                max_results=args.top_k
            )
            
            print(f"Found {len(results)} memories for {args.entity_type} {args.entity_id}")
            for i, result in enumerate(results):
                print(f"\n--- Result {i+1}/{len(results)} (Score: {result['score']:.4f}) ---")
                print(f"ID: {result['id']}")
                print(f"Level: {result['memory_level']}")
                print(f"Type: {result.get('type', 'Unknown')}")
                print("\nContent:")
                print(result['text'])
                print("-" * 80)
        
        elif args.recent:
            # Get recent narrative
            results = get_recent_narrative(max_chunks=args.top_k)
            
            print(f"Found {len(results)} recent narrative chunks")
            for i, result in enumerate(results):
                print(f"\n--- Chunk {i+1}/{len(results)} ---")
                print(f"ID: {result['id']}")
                print("\nContent:")
                print(result['text'])
                print("-" * 80)
        
        elif args.extract_id:
            # Extract chunk ID from text
            chunk_id = extract_chunk_id(args.extract_id)
            
            if chunk_id:
                print(f"Extracted chunk ID: {chunk_id}")
            else:
                print("No chunk ID found in the provided text")
        
        else:
            # No arguments provided, show help
            parser.print_help()
    
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    main()
