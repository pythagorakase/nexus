#!/usr/bin/env python3
"""
db_sqlite.py: SQLite Database Access Module for Night City Stories

This module provides a consolidated interface for all SQLite database operations,
including character data, events, factions, locations, hierarchical memory, and
entity state tracking. It implements clean APIs with comprehensive error handling
and supports transaction management for multi-operation updates.

Usage:
    import db_sqlite as db
    characters = db.get_characters()
    
    # Or run standalone with --test flag to validate functionality
    python db_sqlite.py --test
"""

import os
import re
import sqlite3
import json
import logging
import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("db_sqlite.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("db_sqlite")

# Default settings (can be overridden by settings.json)
DEFAULT_SETTINGS = {
    "db_path": "NightCityStories.db",
    "enable_foreign_keys": True,
    "timeout": 30.0,  # Seconds to wait for database lock
    "connection_cache_size": 5,  # Maximum number of cached connections
    "verbose_logging": False,  # Enable detailed query logging
    "test_data_path": "test_data/",  # Path for test data files
    "max_retries": 3,  # Maximum number of retries for failed operations
    "retry_delay": 0.5  # Delay between retries in seconds
}

# Global variables
settings = DEFAULT_SETTINGS.copy()
connection_cache = {}

class DatabaseError(Exception):
    """Base exception for database-related errors"""
    pass

class QueryError(DatabaseError):
    """Exception for query execution errors"""
    pass

class ConnectionError(DatabaseError):
    """Exception for database connection errors"""
    pass

class SchemaError(DatabaseError):
    """Exception for database schema-related errors"""
    pass

def load_settings() -> Dict[str, Any]:
    """
    Load settings from settings.json, with fallback to default settings
    
    Returns:
        Dictionary containing settings
    """
    global settings
    
    try:
        settings_path = Path("settings.json")
        if settings_path.exists():
            with open(settings_path, "r") as f:
                full_settings = json.load(f)
                
                # Extract database-specific settings if available
                if "database" in full_settings:
                    db_settings = full_settings["database"]
                    settings.update(db_settings)
                elif "db_settings" in full_settings:
                    db_settings = full_settings["db_settings"]
                    settings.update(db_settings)
                else:
                    # Use any top-level settings that match our expected keys
                    for key in DEFAULT_SETTINGS.keys():
                        if key in full_settings:
                            settings[key] = full_settings[key]
                            
            logger.info(f"Loaded settings from {settings_path}")
        else:
            logger.warning(f"Settings file not found: {settings_path}. Using default settings.")
            
    except Exception as e:
        logger.error(f"Error loading settings: {e}. Using default settings.")
    
    return settings

def get_connection(db_path: Optional[str] = None, 
                   return_row_factory: bool = True) -> sqlite3.Connection:
    """
    Get a connection to the SQLite database, with optional caching
    
    Args:
        db_path: Path to the database file (defaults to settings["db_path"])
        return_row_factory: Whether to use sqlite3.Row as row factory
        
    Returns:
        SQLite connection object
        
    Raises:
        ConnectionError: If the database connection fails
    """
    if db_path is None:
        db_path = settings["db_path"]
    
    # Use existing connection from cache if available
    cache_key = (db_path, return_row_factory)
    if cache_key in connection_cache:
        conn = connection_cache[cache_key]
        try:
            # Test if connection is still valid
            conn.execute("SELECT 1")
            return conn
        except sqlite3.Error:
            # Connection is stale, remove from cache
            del connection_cache[cache_key]
            logger.debug(f"Removed stale connection for {db_path}")
    
    # Create a new connection
    try:
        conn = sqlite3.connect(
            db_path, 
            timeout=settings["timeout"],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        
        # Configure connection
        if settings["enable_foreign_keys"]:
            conn.execute("PRAGMA foreign_keys = ON")
            
        if return_row_factory:
            conn.row_factory = sqlite3.Row
        
        # Cache the connection if cache isn't full
        if len(connection_cache) < settings["connection_cache_size"]:
            connection_cache[cache_key] = conn
            logger.debug(f"Cached new connection for {db_path}")
        
        return conn
        
    except sqlite3.Error as e:
        error_msg = f"Failed to connect to database {db_path}: {e}"
        logger.error(error_msg)
        raise ConnectionError(error_msg)

def update_relationship_state(entity1_type: str, entity1_id: int,
                            entity2_type: str, entity2_id: int,
                            relationship_type: str, state_value: str,
                            episode: str, symmetrical: bool = False,
                            chunk_id: str = None, narrative_time: str = None,
                            confidence: float = 1.0, source: str = "system",
                            notes: str = None) -> bool:
    """
    Update a relationship state between two entities
    
    Args:
        entity1_type: Type of first entity
        entity1_id: ID of first entity
        entity2_type: Type of second entity
        entity2_id: ID of second entity
        relationship_type: Type of relationship
        state_value: Value of the relationship
        episode: Episode identifier
        symmetrical: Whether this relationship applies in both directions
        chunk_id: Optional reference to specific narrative chunk
        narrative_time: Optional in-world time
        confidence: Confidence level
        source: Source of this information
        notes: Optional additional context
        
    Returns:
        True if the update was successful, False otherwise
    """
    if not check_table_exists("relationship_state_history") or not check_table_exists("relationship_metadata"):
        logger.warning("Relationship state tables do not exist")
        return False
    
    try:
        timestamp = time.time()
        created_at = time.time()
        
        # Get entity names for logging
        entity1_name = get_entity_name(entity1_type, entity1_id)
        entity2_name = get_entity_name(entity2_type, entity2_id)
        
        # Insert the relationship record
        insert_query = """
        INSERT INTO relationship_state_history
        (entity1_type, entity1_id, entity2_type, entity2_id, relationship_type,
         state_value, symmetrical, episode, timestamp, narrative_time, chunk_id,
         confidence, source, notes, created_at, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """
        
        insert_params = (
            entity1_type, entity1_id, entity2_type, entity2_id, relationship_type,
            state_value, symmetrical, episode, timestamp, narrative_time, chunk_id,
            confidence, source, notes, created_at
        )
        
        execute_write_query(insert_query, insert_params)
        
        # Update relationship metadata
        update_relationship_metadata(
            entity1_type, entity1_id, entity2_type, entity2_id,
            relationship_type, state_value, episode
        )
        
        # If symmetrical, also update in the other direction
        if symmetrical:
            insert_params = (
                entity2_type, entity2_id, entity1_type, entity1_id, relationship_type,
                state_value, symmetrical, episode, timestamp, narrative_time, chunk_id,
                confidence, source, notes, created_at
            )
            
            execute_write_query(insert_query, insert_params)
            
            # Update relationship metadata in reverse direction
            update_relationship_metadata(
                entity2_type, entity2_id, entity1_type, entity1_id,
                relationship_type, state_value, episode
            )
        
        logger.info(f"Updated relationship: {entity1_name} to {entity2_name} " +
                   f"{relationship_type}={state_value} (episode {episode})")
        return True
    
    except QueryError as e:
        logger.error(f"Error updating relationship state: {e}")
        return False

def update_relationship_metadata(entity1_type: str, entity1_id: int,
                               entity2_type: str, entity2_id: int,
                               relationship_type: str, state_value: str,
                               episode: str) -> bool:
    """
    Helper method to update the relationship metadata
    
    Args:
        entity1_type: Type of first entity
        entity1_id: ID of first entity
        entity2_type: Type of second entity
        entity2_id: ID of second entity
        relationship_type: Type of relationship
        state_value: New state value
        episode: Current episode
        
    Returns:
        True if successful, False otherwise
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check if there's an existing metadata entry
        query = """
        SELECT current_states, last_episode FROM relationship_metadata
        WHERE entity1_type = ? AND entity1_id = ? AND entity2_type = ? AND entity2_id = ?
        """
        
        cursor.execute(query, (entity1_type, entity1_id, entity2_type, entity2_id))
        row = cursor.fetchone()
        
        if row:
            # Update existing entry
            current_states = json.loads(row["current_states"]) if row["current_states"] else {}
            last_episode = row["last_episode"]
            
            # Update the state
            current_states[relationship_type] = state_value
            
            # Determine if we should update the episode (only if new one is later)
            update_episode = last_episode
            if not last_episode or compare_episodes(episode, last_episode) > 0:
                update_episode = episode
            
            # Update the metadata
            update_query = """
            UPDATE relationship_metadata
            SET current_states = ?, last_updated = ?, last_episode = ?
            WHERE entity1_type = ? AND entity1_id = ? AND entity2_type = ? AND entity2_id = ?
            """
            
            cursor.execute(update_query, (
                json.dumps(current_states),
                time.time(),
                update_episode,
                entity1_type,
                entity1_id,
                entity2_type,
                entity2_id
            ))
        else:
            # Create new metadata entry
            insert_query = """
            INSERT INTO relationship_metadata
            (entity1_type, entity1_id, entity2_type, entity2_id, current_states, last_updated, last_episode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            cursor.execute(insert_query, (
                entity1_type,
                entity1_id,
                entity2_type,
                entity2_id,
                json.dumps({relationship_type: state_value}),
                time.time(),
                episode
            ))
        
        conn.commit()
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Error updating relationship metadata: {e}")
        return False

def get_relationship_current_state(entity1_type: str, entity1_id: int,
                                 entity2_type: str, entity2_id: int,
                                 relationship_type: str = None) -> Union[str, Dict[str, str], None]:
    """
    Get the current state of a relationship between two entities
    
    Args:
        entity1_type: Type of first entity
        entity1_id: ID of first entity
        entity2_type: Type of second entity
        entity2_id: ID of second entity
        relationship_type: Optional specific relationship type
        
    Returns:
        If relationship_type is specified: the current value for that relationship
        If relationship_type is None: dictionary of all relationship types and values
    """
    if not check_table_exists("relationship_metadata"):
        logger.warning("Relationship metadata table does not exist")
        return None
    
    try:
        query = """
        SELECT current_states
        FROM relationship_metadata
        WHERE entity1_type = ? AND entity1_id = ? AND entity2_type = ? AND entity2_id = ?
        """
        
        rows = execute_query(query, (entity1_type, entity1_id, entity2_type, entity2_id), fetch_all=False)
        if not rows:
            return None
        
        current_states = json.loads(rows[0]["current_states"]) if rows[0]["current_states"] else {}
        
        if relationship_type:
            return current_states.get(relationship_type)
        return current_states
    
    except QueryError as e:
        logger.error(f"Error retrieving relationship current state: {e}")
        return None

def close_all_connections() -> None:
    """Close all cached database connections"""
    global connection_cache
    
    for key, conn in connection_cache.items():
        try:
            conn.close()
            logger.debug(f"Closed connection for {key[0]}")
        except sqlite3.Error as e:
            logger.warning(f"Error closing connection for {key[0]}: {e}")
    
    connection_cache = {}
    logger.info("All database connections closed")

def execute_query(query: str, 
                  params: Union[Tuple, List, Dict] = (), 
                  fetch_all: bool = True,
                  db_path: Optional[str] = None) -> List[sqlite3.Row]:
    """
    Execute a database query with error handling and retries
    
    Args:
        query: SQL query string
        params: Parameters for the query
        fetch_all: Whether to fetch all results (False for single result)
        db_path: Optional path to database file
        
    Returns:
        List of sqlite3.Row objects, or empty list if no results
        
    Raises:
        QueryError: If the query execution fails after retries
    """
    if settings["verbose_logging"]:
        logger.debug(f"Executing query: {query}")
        logger.debug(f"Parameters: {params}")
    
    retries = 0
    max_retries = settings["max_retries"]
    last_error = None
    
    while retries <= max_retries:
        try:
            conn = get_connection(db_path)
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if fetch_all:
                results = cursor.fetchall()
            else:
                result = cursor.fetchone()
                results = [result] if result else []
                
            return results
            
        except sqlite3.Error as e:
            last_error = e
            retries += 1
            
            if retries <= max_retries:
                retry_delay = settings["retry_delay"] * (2 ** (retries - 1))  # Exponential backoff
                logger.warning(f"Query failed: {e}. Retrying ({retries}/{max_retries}) in {retry_delay:.2f}s")
                time.sleep(retry_delay)
            else:
                error_msg = f"Query failed after {max_retries} retries: {e}"
                logger.error(error_msg)
                raise QueryError(error_msg)
    
    # This shouldn't be reached due to the exception above, but just in case
    raise QueryError(f"Query failed: {last_error}")

def execute_write_query(query: str, 
                       params: Union[Tuple, List, Dict] = (),
                       db_path: Optional[str] = None) -> int:
    """
    Execute a database write query (INSERT, UPDATE, DELETE)
    
    Args:
        query: SQL query string
        params: Parameters for the query
        db_path: Optional path to database file
        
    Returns:
        Number of rows affected
        
    Raises:
        QueryError: If the query execution fails
    """
    if settings["verbose_logging"]:
        logger.debug(f"Executing write query: {query}")
        logger.debug(f"Parameters: {params}")
    
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.rowcount
    
    except sqlite3.Error as e:
        error_msg = f"Write query failed: {e}"
        logger.error(error_msg)
        raise QueryError(error_msg)

def dict_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a sqlite3.Row to a dictionary"""
    return {key: row[key] for key in row.keys()}

def check_table_exists(table_name: str, db_path: Optional[str] = None) -> bool:
    """
    Check if a table exists in the database
    
    Args:
        table_name: Name of the table to check
        db_path: Optional path to database file
        
    Returns:
        True if the table exists, False otherwise
    """
    try:
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        results = execute_query(query, (table_name,), db_path=db_path)
        return len(results) > 0
    except QueryError:
        return False

def get_table_info(table_name: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get information about table columns
    
    Args:
        table_name: Name of the table
        db_path: Optional path to database file
        
    Returns:
        List of dictionaries containing column information
    """
    if not check_table_exists(table_name, db_path):
        raise SchemaError(f"Table does not exist: {table_name}")
        
    query = f"PRAGMA table_info({table_name})"
    
    try:
        results = execute_query(query, db_path=db_path)
        return [dict_from_row(row) for row in results]
    except QueryError as e:
        raise SchemaError(f"Failed to get table info for {table_name}: {e}")

#
# Character Query Functions
#

def get_characters() -> List[Dict[str, Any]]:
    """
    Fetch selected columns from the 'characters' table.
    
    Returns:
        List of dictionaries, one per character with keys:
        id, name, aliases, description, personality
    """
    try:
        query = """
        SELECT id, name, aliases, description, personality
        FROM characters;
        """
        rows = execute_query(query)
        characters = [dict_from_row(row) for row in rows]
        
        if settings["verbose_logging"]:
            char_count = len(characters)
            debug_str = json.dumps(characters, indent=2)
            logger.debug(f"Characters Retrieved: {char_count}, {len(debug_str)} characters")
            
        return characters
    
    except QueryError as e:
        logger.error(f"Error retrieving characters: {e}")
        return []

def get_character_by_id(character_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch a character by ID
    
    Args:
        character_id: The character's ID
        
    Returns:
        Dictionary with character data or None if not found
    """
    try:
        query = """
        SELECT id, name, aliases, description, personality
        FROM characters
        WHERE id = ?;
        """
        rows = execute_query(query, (character_id,), fetch_all=False)
        
        if not rows:
            return None
            
        return dict_from_row(rows[0])
    
    except QueryError as e:
        logger.error(f"Error retrieving character {character_id}: {e}")
        return None

def get_character_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a character by name (exact match)
    
    Args:
        name: The character's name
        
    Returns:
        Dictionary with character data or None if not found
    """
    try:
        query = """
        SELECT id, name, aliases, description, personality
        FROM characters
        WHERE name = ?;
        """
        rows = execute_query(query, (name,), fetch_all=False)
        
        if not rows:
            return None
            
        return dict_from_row(rows[0])
    
    except QueryError as e:
        logger.error(f"Error retrieving character '{name}': {e}")
        return None

def search_characters(search_term: str) -> List[Dict[str, Any]]:
    """
    Search for characters by name, aliases, or description
    
    Args:
        search_term: Term to search for
        
    Returns:
        List of matching character dictionaries
    """
    try:
        query = """
        SELECT id, name, aliases, description, personality
        FROM characters
        WHERE name LIKE ? OR aliases LIKE ? OR description LIKE ?;
        """
        search_pattern = f"%{search_term}%"
        params = (search_pattern, search_pattern, search_pattern)
        rows = execute_query(query, params)
        
        return [dict_from_row(row) for row in rows]
    
    except QueryError as e:
        logger.error(f"Error searching characters for '{search_term}': {e}")
        return []

#
# Character Relationship Functions
#

def get_character_relationships() -> List[Dict[str, Any]]:
    """
    Fetch selected columns from the 'character_relationships' table.
    
    Returns:
        List of dictionaries with keys:
        id, character1_id, character2_id, dynamic
    """
    try:
        query = """
        SELECT id, character1_id, character2_id, dynamic
        FROM character_relationships;
        """
        rows = execute_query(query)
        relationships = [dict_from_row(row) for row in rows]
        
        if settings["verbose_logging"]:
            rel_count = len(relationships)
            debug_str = json.dumps(relationships, indent=2)
            logger.debug(f"Character Relationships Retrieved: {rel_count}, {len(debug_str)} characters")
            
        return relationships
    
    except QueryError as e:
        logger.error(f"Error retrieving character relationships: {e}")
        return []

def get_character_relationships_for_character(character_id: int) -> List[Dict[str, Any]]:
    """
    Get all relationships for a specific character
    
    Args:
        character_id: The character's ID
        
    Returns:
        List of relationship dictionaries
    """
    try:
        query = """
        SELECT r.id, r.character1_id, r.character2_id, r.dynamic,
               c1.name as character1_name, c2.name as character2_name
        FROM character_relationships r
        JOIN characters c1 ON r.character1_id = c1.id
        JOIN characters c2 ON r.character2_id = c2.id
        WHERE r.character1_id = ? OR r.character2_id = ?;
        """
        rows = execute_query(query, (character_id, character_id))
        
        relationships = []
        for row in rows:
            row_dict = dict_from_row(row)
            
            # Restructure to have consistent "self" and "other" fields
            if row_dict["character1_id"] == character_id:
                row_dict["self_id"] = row_dict["character1_id"]
                row_dict["self_name"] = row_dict["character1_name"]
                row_dict["other_id"] = row_dict["character2_id"]
                row_dict["other_name"] = row_dict["character2_name"]
            else:
                row_dict["self_id"] = row_dict["character2_id"]
                row_dict["self_name"] = row_dict["character2_name"]
                row_dict["other_id"] = row_dict["character1_id"]
                row_dict["other_name"] = row_dict["character1_name"]
            
            relationships.append(row_dict)
            
        return relationships
    
    except QueryError as e:
        logger.error(f"Error retrieving relationships for character {character_id}: {e}")
        return []

def get_relationship_between_characters(character1_id: int, character2_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the relationship between two specific characters
    
    Args:
        character1_id: First character's ID
        character2_id: Second character's ID
        
    Returns:
        Relationship dictionary or None if no relationship exists
    """
    try:
        query = """
        SELECT id, character1_id, character2_id, dynamic
        FROM character_relationships
        WHERE (character1_id = ? AND character2_id = ?)
           OR (character1_id = ? AND character2_id = ?);
        """
        rows = execute_query(query, (character1_id, character2_id, character2_id, character1_id), fetch_all=False)
        
        if not rows:
            return None
            
        return dict_from_row(rows[0])
    
    except QueryError as e:
        logger.error(f"Error retrieving relationship between characters {character1_id} and {character2_id}: {e}")
        return None

#
# Event Functions
#

def get_events() -> List[Dict[str, Any]]:
    """
    Retrieves events from the SQLite database.
    
    Returns:
        List of dictionaries for each event with keys:
        event_id, description, cause, consequences, status
    """
    try:
        query = """
        SELECT event_id, description, status
        FROM events
        """
        rows = execute_query(query)
        events = [dict_from_row(row) for row in rows]
        
        if settings["verbose_logging"]:
            event_count = len(events)
            debug_str = json.dumps(events, indent=2)
            logger.debug(f"Events Retrieved: {event_count}, {len(debug_str)} characters")
            
        return events
    
    except QueryError as e:
        logger.error(f"Error retrieving events: {e}")
        return []

def get_event_by_id(event_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a specific event by ID
    
    Args:
        event_id: The event's ID
        
    Returns:
        Event dictionary or None if not found
    """
    try:
        query = """
        SELECT event_id, description, cause, consequences, status
        FROM events
        WHERE event_id = ?;
        """
        rows = execute_query(query, (event_id,), fetch_all=False)
        
        if not rows:
            return None
            
        return dict_from_row(rows[0])
    
    except QueryError as e:
        logger.error(f"Error retrieving event {event_id}: {e}")
        return None

def get_chunk_tag_for_event_id(event_id: int) -> Optional[str]:
    """
    Looks up the chunk_tag in the 'events' table where event_id = ?
    
    Args:
        event_id: The event's ID
        
    Returns:
        The chunk_tag string if found, or None if not found
    """
    try:
        query = """
        SELECT chunk_tag FROM events WHERE event_id = ?
        """
        rows = execute_query(query, (event_id,), fetch_all=False)
        
        if not rows:
            return None
            
        return rows[0]["chunk_tag"]
    
    except QueryError as e:
        logger.error(f"Error retrieving chunk_tag for event {event_id}: {e}")
        return None

def search_events(search_term: str) -> List[Dict[str, Any]]:
    """
    Search for events by description or status
    
    Args:
        search_term: Term to search for
        
    Returns:
        List of matching event dictionaries
    """
    try:
        query = """
        SELECT event_id, description, status
        FROM events
        WHERE description LIKE ? OR status LIKE ?;
        """
        search_pattern = f"%{search_term}%"
        rows = execute_query(query, (search_pattern, search_pattern))
        
        return [dict_from_row(row) for row in rows]
    
    except QueryError as e:
        logger.error(f"Error searching events for '{search_term}': {e}")
        return []

#
# Faction Functions
#

def get_factions() -> Dict[str, Dict[str, Any]]:
    """
    Fetches selected columns from the 'factions' table.
    
    Returns:
        Dictionary keyed by faction name, with values containing:
        name, ideology, hidden_agendas, current_activity
    """
    try:
        query = """
        SELECT name, ideology, hidden_agendas, current_activity
        FROM factions;
        """
        rows = execute_query(query)
        factions = {row["name"]: dict_from_row(row) for row in rows}
        
        if settings["verbose_logging"]:
            faction_count = len(factions)
            debug_str = json.dumps(factions, indent=2)
            logger.debug(f"Factions Retrieved: {faction_count}, {len(debug_str)} characters")
            
        return factions
    
    except QueryError as e:
        logger.error(f"Error retrieving factions: {e}")
        return {}

def get_faction_by_name(faction_name: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific faction by name
    
    Args:
        faction_name: The faction's name
        
    Returns:
        Faction dictionary or None if not found
    """
    try:
        query = """
        SELECT name, ideology, hidden_agendas, current_activity
        FROM factions
        WHERE name = ?;
        """
        rows = execute_query(query, (faction_name,), fetch_all=False)
        
        if not rows:
            return None
            
        return dict_from_row(rows[0])
    
    except QueryError as e:
        logger.error(f"Error retrieving faction '{faction_name}': {e}")
        return None

def search_factions(search_term: str) -> List[Dict[str, Any]]:
    """
    Search for factions by name, ideology, or current activity
    
    Args:
        search_term: Term to search for
        
    Returns:
        List of matching faction dictionaries
    """
    try:
        query = """
        SELECT name, ideology, hidden_agendas, current_activity
        FROM factions
        WHERE name LIKE ? OR ideology LIKE ? OR current_activity LIKE ?;
        """
        search_pattern = f"%{search_term}%"
        params = (search_pattern, search_pattern, search_pattern)
        rows = execute_query(query, params)
        
        return [dict_from_row(row) for row in rows]
    
    except QueryError as e:
        logger.error(f"Error searching factions for '{search_term}': {e}")
        return []

#
# Location Functions
#

def get_locations() -> Dict[str, Dict[str, Any]]:
    """
    Fetches selected columns from the 'locations' table.
    
    Returns:
        Dictionary keyed by location name, with values containing:
        name, description, status, historical_significance
    """
    try:
        query = """
        SELECT name, description, status, historical_significance
        FROM locations;
        """
        rows = execute_query(query)
        locations = {row["name"]: dict_from_row(row) for row in rows}
        
        if settings["verbose_logging"]:
            location_count = len(locations)
            debug_str = json.dumps(locations, indent=2)
            logger.debug(f"Locations Retrieved: {location_count}, {len(debug_str)} characters")
            
        return locations
    
    except QueryError as e:
        logger.error(f"Error retrieving locations: {e}")
        return {}

def get_location_by_name(location_name: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific location by name
    
    Args:
        location_name: The location's name
        
    Returns:
        Location dictionary or None if not found
    """
    try:
        query = """
        SELECT name, description, status, historical_significance
        FROM locations
        WHERE name = ?;
        """
        rows = execute_query(query, (location_name,), fetch_all=False)
        
        if not rows:
            return None
            
        return dict_from_row(rows[0])
    
    except QueryError as e:
        logger.error(f"Error retrieving location '{location_name}': {e}")
        return None

def search_locations(search_term: str) -> List[Dict[str, Any]]:
    """
    Search for locations by name, description, or status
    
    Args:
        search_term: Term to search for
        
    Returns:
        List of matching location dictionaries
    """
    try:
        query = """
        SELECT name, description, status, historical_significance
        FROM locations
        WHERE name LIKE ? OR description LIKE ? OR status LIKE ?;
        """
        search_pattern = f"%{search_term}%"
        params = (search_pattern, search_pattern, search_pattern)
        rows = execute_query(query, params)
        
        return [dict_from_row(row) for row in rows]
    
    except QueryError as e:
        logger.error(f"Error searching locations for '{search_term}': {e}")
        return []

#
# Secret Functions
#

def get_secrets() -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetches selected columns from the 'secrets' table.
    
    Returns:
        Dictionary grouping secrets by category, with each item containing:
        category, entity_id, entity_name, secret_type, details
    """
    try:
        query = """
        SELECT category, entity_id, entity_name, secret_type, details
        FROM secrets;
        """
        rows = execute_query(query)
        
        secrets = {}
        for row in rows:
            row_dict = dict_from_row(row)
            category = row_dict["category"]
            
            if category not in secrets:
                secrets[category] = []
                
            secrets[category].append(row_dict)
        
        if settings["verbose_logging"]:
            secret_count = sum(len(items) for items in secrets.values())
            debug_str = json.dumps(secrets, indent=2)
            logger.debug(f"Secrets Retrieved: {secret_count}, {len(debug_str)} characters")
            
        return secrets
    
    except QueryError as e:
        logger.error(f"Error retrieving secrets: {e}")
        return {}

def get_secrets_for_entity(entity_name: str) -> List[Dict[str, Any]]:
    """
    Get all secrets for a specific entity
    
    Args:
        entity_name: The entity's name
        
    Returns:
        List of secret dictionaries
    """
    try:
        query = """
        SELECT category, entity_id, entity_name, secret_type, details
        FROM secrets
        WHERE entity_name = ?;
        """
        rows = execute_query(query, (entity_name,))
        
        return [dict_from_row(row) for row in rows]
    
    except QueryError as e:
        logger.error(f"Error retrieving secrets for entity '{entity_name}': {e}")
        return []

#
# Hierarchical Memory Functions
#

def get_memory_level(level: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Get memory items from a specific hierarchical level
    
    Args:
        level: Memory level ('top', 'mid')
        filters: Optional dictionary of filters to apply
        
    Returns:
        List of memory item dictionaries
    """
    if level not in ["top", "mid"]:
        logger.error(f"Invalid memory level: {level}")
        return []
    
    table_name = "top_level_memory" if level == "top" else "mid_level_memory"
    
    # Check if the table exists
    if not check_table_exists(table_name):
        logger.warning(f"Memory table does not exist: {table_name}")
        return []
    
    try:
        query_parts = [f"SELECT * FROM {table_name}"]
        params = []
        
        # Apply filters if provided
        if filters:
            where_clauses = []
            for key, value in filters.items():
                where_clauses.append(f"{key} = ?")
                params.append(value)
            
            if where_clauses:
                query_parts.append("WHERE " + " AND ".join(where_clauses))
        
        query = " ".join(query_parts)
        rows = execute_query(query, tuple(params))
        
        return [dict_from_row(row) for row in rows]
    
    except QueryError as e:
        logger.error(f"Error retrieving {level} level memory: {e}")
        return []

def get_memory_links(source_level: str, source_id: str, 
                    direction: str = "outgoing", 
                    link_types: List[str] = None) -> List[Dict[str, Any]]:
    """
    Get links between memory items
    
    Args:
        source_level: Source memory level ('top', 'mid', 'chunk')
        source_id: ID of the source memory item
        direction: Link direction ('incoming', 'outgoing', 'both')
        link_types: Optional list of link types to filter by
        
    Returns:
        List of memory link dictionaries
    """
    if not check_table_exists("memory_links"):
        logger.warning("Memory links table does not exist")
        return []
    
    try:
        query_parts = []
        params = []
        
        # Handle different directions
        if direction in ["outgoing", "both"]:
            outgoing_query = """
            SELECT 'outgoing' as direction, link_type, relevance_score,
                   target_level, target_id
            FROM memory_links
            WHERE source_level = ? AND source_id = ?
            """
            params.extend([source_level, source_id])
            
            if link_types:
                placeholders = ", ".join(["?"] * len(link_types))
                outgoing_query += f" AND link_type IN ({placeholders})"
                params.extend(link_types)
                
            query_parts.append(outgoing_query)
        
        if direction in ["incoming", "both"]:
            incoming_query = """
            SELECT 'incoming' as direction, link_type, relevance_score,
                   source_level as connected_level, source_id as connected_id
            FROM memory_links
            WHERE target_level = ? AND target_id = ?
            """
            if direction == "both":
                # Add params again for the incoming query
                params.extend([source_level, source_id])
            else:
                # Just add the params for the incoming query
                params = [source_level, source_id]
                
            if link_types:
                placeholders = ", ".join(["?"] * len(link_types))
                incoming_query += f" AND link_type IN ({placeholders})"
                params.extend(link_types)
                
            query_parts.append(incoming_query)
        
        # Combine queries with UNION if needed
        query = " UNION ".join(query_parts)
        rows = execute_query(query, tuple(params))
        
        return [dict_from_row(row) for row in rows]
    
    except QueryError as e:
        logger.error(f"Error retrieving memory links: {e}")
        return []

def create_memory_link(source_level: str, source_id: str,
                     target_level: str, target_id: str,
                     link_type: str, relevance_score: float = None) -> bool:
    """
    Create a link between two memory items
    
    Args:
        source_level: Source memory level ('top', 'mid', 'chunk')
        source_id: ID of the source memory item
        target_level: Target memory level ('top', 'mid', 'chunk')
        target_id: ID of the target memory item
        link_type: Type of link ('contains', 'references', 'influences')
        relevance_score: Optional score indicating relevance strength
        
    Returns:
        True if the link was created successfully, False otherwise
    """
    if not check_table_exists("memory_links"):
        logger.warning("Memory links table does not exist")
        return False
    
    try:
        # Check if the link already exists
        check_query = """
        SELECT id FROM memory_links
        WHERE source_level = ? AND source_id = ? 
          AND target_level = ? AND target_id = ?
          AND link_type = ?
        """
        check_params = (source_level, source_id, target_level, target_id, link_type)
        existing = execute_query(check_query, check_params, fetch_all=False)
        
        if existing:
            # Update existing link if relevance_score is provided
            if relevance_score is not None:
                update_query = """
                UPDATE memory_links
                SET relevance_score = ?
                WHERE id = ?
                """
                execute_write_query(update_query, (relevance_score, existing[0]["id"]))
            
            return True
        
        # Create new link
        insert_query = """
        INSERT INTO memory_links
        (source_level, source_id, target_level, target_id, link_type, relevance_score)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        insert_params = (source_level, source_id, target_level, target_id, 
                         link_type, relevance_score)
        
        execute_write_query(insert_query, insert_params)
        return True
    
    except QueryError as e:
        logger.error(f"Error creating memory link: {e}")
        return False

def add_top_level_memory(memory_type: str, title: str, description: str,
                        start_episode: str = None, end_episode: str = None,
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
    if not check_table_exists("top_level_memory"):
        logger.warning("Top level memory table does not exist")
        return None
    
    try:
        # Generate an embedding ID (simplified version)
        embedding_id = f"top_{int(time.time())}_{hash(title) % 10000}"
        
        query = """
        INSERT INTO top_level_memory
        (type, title, description, start_episode, end_episode, entities, embedding_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        
        entities_json = json.dumps(entities or [])
        params = (memory_type, title, description, start_episode, end_episode,
                 entities_json, embedding_id)
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        
        memory_id = cursor.lastrowid
        logger.info(f"Added top-level memory: {title} (ID: {memory_id})")
        
        return memory_id
    
    except (sqlite3.Error, QueryError) as e:
        logger.error(f"Error adding top-level memory: {e}")
        return None

def add_mid_level_memory(memory_type: str, episode: str, title: str, content: str,
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
    if not check_table_exists("mid_level_memory"):
        logger.warning("Mid level memory table does not exist")
        return None
    
    try:
        # Generate an embedding ID
        embedding_id = f"mid_{episode}_{int(time.time())}_{hash(title) % 10000}"
        
        query = """
        INSERT INTO mid_level_memory
        (type, episode, title, content, entities, parent_ids, embedding_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        
        entities_json = json.dumps(entities or [])
        parent_ids_json = json.dumps(parent_ids or [])
        params = (memory_type, episode, title, content, entities_json,
                 parent_ids_json, embedding_id)
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        
        memory_id = cursor.lastrowid
        logger.info(f"Added mid-level memory: {title} (ID: {memory_id})")
        
        # If parent IDs are provided, create links
        if parent_ids:
            for parent_id in parent_ids:
                create_memory_link(
                    source_level="top",
                    source_id=str(parent_id),
                    target_level="mid",
                    target_id=str(memory_id),
                    link_type="contains"
                )
        
        return memory_id
    
    except (sqlite3.Error, QueryError) as e:
        logger.error(f"Error adding mid-level memory: {e}")
        return None

#
# Entity State Functions
#

def get_entity_state_history(entity_type: str, entity_id: int, 
                           state_type: str = None,
                           start_episode: str = None,
                           end_episode: str = None) -> List[Dict[str, Any]]:
    """
    Get the history of an entity's states
    
    Args:
        entity_type: Type of entity ('character', 'faction', 'location')
        entity_id: ID of entity
        state_type: Optional specific state type to retrieve
        start_episode: Optional starting episode
        end_episode: Optional ending episode
        
    Returns:
        List of state history entries in chronological order
    """
    if not check_table_exists("entity_state_history"):
        logger.warning("Entity state history table does not exist")
        return []
    
    try:
        query_parts = ["""
        SELECT * FROM entity_state_history
        WHERE entity_type = ? AND entity_id = ? AND is_active = 1
        """]
        params = [entity_type, entity_id]
        
        if state_type:
            query_parts.append("AND state_type = ?")
            params.append(state_type)
        
        if start_episode:
            query_parts.append("AND episode >= ?")
            params.append(start_episode)
        
        if end_episode:
            query_parts.append("AND episode <= ?")
            params.append(end_episode)
        
        query_parts.append("ORDER BY episode ASC, timestamp ASC")
        query = " ".join(query_parts)
        
        rows = execute_query(query, tuple(params))
        return [dict_from_row(row) for row in rows]
    
    except QueryError as e:
        logger.error(f"Error retrieving entity state history: {e}")
        return []

def get_entity_current_state(entity_type: str, entity_id: int, 
                           state_type: str = None) -> Union[str, Dict[str, Any], None]:
    """
    Get the current state of an entity
    
    Args:
        entity_type: Type of entity
        entity_id: ID of entity
        state_type: Optional specific state type to retrieve
        
    Returns:
        If state_type is specified: the current value for that state
        If state_type is None: dictionary of all current states
        None if entity not found
    """
    if not check_table_exists("entity_metadata"):
        logger.warning("Entity metadata table does not exist")
        return None
    
    try:
        query = """
        SELECT current_states, last_episode
        FROM entity_metadata
        WHERE entity_type = ? AND entity_id = ?
        """
        
        rows = execute_query(query, (entity_type, entity_id), fetch_all=False)
        if not rows:
            return None
        
        current_states = json.loads(rows[0]["current_states"]) if rows[0]["current_states"] else {}
        
        if state_type:
            return current_states.get(state_type)
        return current_states
    
    except QueryError as e:
        logger.error(f"Error retrieving entity current state: {e}")
        return None

def get_entity_state_at_episode(entity_type: str, entity_id: int,
                              episode: str,
                              state_type: str = None) -> Union[str, Dict[str, Any], None]:
    """
    Get an entity's state at a specific episode
    
    Args:
        entity_type: Type of entity
        entity_id: ID of entity
        episode: Target episode
        state_type: Optional specific state type to retrieve
        
    Returns:
        If state_type is specified: the value for that state at the episode
        If state_type is None: dictionary of all states at the episode
    """
    if not check_table_exists("entity_state_history"):
        logger.warning("Entity state history table does not exist")
        return None
    
    try:
        if state_type:
            # Get the most recent state of the specified type up to the given episode
            query = """
            SELECT state_value
            FROM entity_state_history
            WHERE entity_type = ? AND entity_id = ? AND state_type = ? 
              AND episode <= ? AND is_active = 1
            ORDER BY episode DESC, timestamp DESC
            LIMIT 1
            """
            
            rows = execute_query(query, (entity_type, entity_id, state_type, episode), fetch_all=False)
            return rows[0]["state_value"] if rows else None
        else:
            # Get all state types this entity has ever had
            query1 = """
            SELECT DISTINCT state_type
            FROM entity_state_history
            WHERE entity_type = ? AND entity_id = ? AND is_active = 1
            """
            
            state_type_rows = execute_query(query1, (entity_type, entity_id))
            state_types = [row["state_type"] for row in state_type_rows]
            
            # For each state type, get the most recent value up to the given episode
            states = {}
            for st in state_types:
                query2 = """
                SELECT state_value
                FROM entity_state_history
                WHERE entity_type = ? AND entity_id = ? AND state_type = ? 
                  AND episode <= ? AND is_active = 1
                ORDER BY episode DESC, timestamp DESC
                LIMIT 1
                """
                
                value_rows = execute_query(query2, (entity_type, entity_id, st, episode), fetch_all=False)
                if value_rows:
                    states[st] = value_rows[0]["state_value"]
            
            return states
    
    except QueryError as e:
        logger.error(f"Error retrieving entity state at episode: {e}")
        return None

def update_entity_state(entity_type: str, entity_id: int,
                      state_type: str, state_value: str,
                      episode: str, chunk_id: str = None,
                      narrative_time: str = None,
                      confidence: float = 1.0,
                      source: str = "system",
                      notes: str = None) -> bool:
    """
    Update an entity's state
    
    Args:
        entity_type: Type of entity ('character', 'faction', 'location')
        entity_id: Database ID of the entity
        state_type: Type of state
        state_value: Value of the state
        episode: Episode identifier
        chunk_id: Optional reference to specific narrative chunk
        narrative_time: Optional in-world time
        confidence: Confidence level (0.0-1.0)
        source: Source of this information
        notes: Optional additional context
        
    Returns:
        True if the update was successful, False otherwise
    """
    if not check_table_exists("entity_state_history") or not check_table_exists("entity_metadata"):
        logger.warning("Entity state tables do not exist")
        return False
    
    try:
        timestamp = time.time()
        created_at = time.time()
        
        # Get entity name for metadata
        entity_name = get_entity_name(entity_type, entity_id)
        
        # Insert the new state record
        insert_query = """
        INSERT INTO entity_state_history
        (entity_type, entity_id, state_type, state_value, episode, timestamp, 
         narrative_time, chunk_id, confidence, source, notes, created_at, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """
        
        insert_params = (
            entity_type, entity_id, state_type, state_value, episode, timestamp,
            narrative_time, chunk_id, confidence, source, notes, created_at
        )
        
        execute_write_query(insert_query, insert_params)
        
        # Update entity metadata
        update_entity_metadata(entity_type, entity_id, state_type, state_value, episode, entity_name)
        
        logger.info(f"Updated entity state: {entity_name} {state_type}={state_value} (episode {episode})")
        return True
    
    except QueryError as e:
        logger.error(f"Error updating entity state: {e}")
        return False

def update_entity_metadata(entity_type: str, entity_id: int,
                         state_type: str, state_value: str,
                         episode: str, entity_name: str = None) -> bool:
    """
    Helper method to update the entity metadata
    
    Args:
        entity_type: Type of entity
        entity_id: ID of entity
        state_type: Type of state being updated
        state_value: New state value
        episode: Current episode
        entity_name: Optional entity name for logging
        
    Returns:
        True if successful, False otherwise
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check if there's an existing metadata entry
        query = """
        SELECT current_states, last_episode FROM entity_metadata
        WHERE entity_type = ? AND entity_id = ?
        """
        
        cursor.execute(query, (entity_type, entity_id))
        row = cursor.fetchone()
        
        if row:
            # Update existing entry
            current_states = json.loads(row["current_states"]) if row["current_states"] else {}
            last_episode = row["last_episode"]
            
            # Update the state
            current_states[state_type] = state_value
            
            # Determine if we should update the episode (only if new one is later)
            update_episode = last_episode
            if not last_episode or compare_episodes(episode, last_episode) > 0:
                update_episode = episode
            
            # Update the metadata
            update_query = """
            UPDATE entity_metadata
            SET current_states = ?, last_updated = ?, last_episode = ?
            WHERE entity_type = ? AND entity_id = ?
            """
            
            cursor.execute(update_query, (
                json.dumps(current_states),
                time.time(),
                update_episode,
                entity_type,
                entity_id
            ))
        else:
            # Create new metadata entry
            insert_query = """
            INSERT INTO entity_metadata
            (entity_type, entity_id, entity_name, current_states, last_updated, last_episode)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            
            cursor.execute(insert_query, (
                entity_type,
                entity_id,
                entity_name,
                json.dumps({state_type: state_value}),
                time.time(),
                episode
            ))
        
        conn.commit()
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Error updating entity metadata: {e}")
        return False

def get_entity_name(entity_type: str, entity_id: int) -> str:
    """
    Get the name of an entity based on its type and ID
    
    Args:
        entity_type: Type of entity ('character', 'faction', 'location', etc.)
        entity_id: ID of the entity
        
    Returns:
        Entity name or a fallback identifier if not found
    """
    try:
        name = None
        
        if entity_type == "character":
            query = "SELECT name FROM characters WHERE id = ?"
            rows = execute_query(query, (entity_id,), fetch_all=False)
            if rows:
                name = rows[0]["name"]
        
        elif entity_type == "faction":
            query = "SELECT name FROM factions WHERE name = ?"  # Factions use name as ID
            rows = execute_query(query, (entity_id,), fetch_all=False)
            if rows:
                name = rows[0]["name"]
        
        elif entity_type == "location":
            query = "SELECT name FROM locations WHERE name = ?"  # Locations use name as ID
            rows = execute_query(query, (entity_id,), fetch_all=False)
            if rows:
                name = rows[0]["name"]
        
        # Add more entity types as needed
        
        # Check metadata table as fallback
        if not name:
            query = "SELECT entity_name FROM entity_metadata WHERE entity_type = ? AND entity_id = ?"
            rows = execute_query(query, (entity_type, entity_id), fetch_all=False)
            if rows and rows[0]["entity_name"]:
                name = rows[0]["entity_name"]
        
        return name or f"{entity_type}_{entity_id}"
    
    except QueryError as e:
        logger.error(f"Error getting entity name: {e}")
        return f"{entity_type}_{entity_id}"

def compare_episodes(episode1: str, episode2: str) -> int:
    """
    Compare two episode identifiers to determine chronological order
    
    Args:
        episode1: First episode identifier
        episode2: Second episode identifier
        
    Returns:
        -1 if episode1 is earlier than episode2
         0 if they are equal
         1 if episode1 is later than episode2
    """
    if episode1 == episode2:
        return 0
        
    # Try to extract season and episode numbers
    pattern = r'S(\d+)E(\d+)'
    
    match1 = re.match(pattern, episode1)
    match2 = re.match(pattern, episode2)
    
    if match1 and match2:
        # Both match the pattern, compare numerically
        s1, e1 = int(match1.group(1)), int(match1.group(2))
        s2, e2 = int(match2.group(1)), int(match2.group(2))
        
        if s1 < s2:
            return -1
        elif s1 > s2:
            return 1
        else:
            # Same season, compare episode numbers
            if e1 < e2:
                return -1
            elif e1 > e2:
                return 1
            else:
                return 0
    
    # Try other common formats like "Chapter X"
    chapter_pattern = r'Chapter (\d+)'
    
    match1 = re.match(chapter_pattern, episode1)
    match2 = re.match(chapter_pattern, episode2)
    
    if match1 and match2:
        c1 = int(match1.group(1))
        c2 = int(match2.group(1))
        
        return -1 if c1 < c2 else (1 if c1 > c2 else 0)
    
    # Fallback to string comparison if formats don't match
    return -1 if episode1 < episode2 else (1 if episode1 > episode2 else 0)

# Testing Functions

def create_test_database(db_path: str) -> bool:
    """
    Create a test database with necessary tables for testing
    
    Args:
        db_path: Path to the test database file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Remove existing test database if it exists
        if os.path.exists(db_path):
            os.remove(db_path)
            
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create characters table
        cursor.execute("""
        CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            aliases TEXT,
            description TEXT,
            personality TEXT
        )
        """)
        
        # Create character_relationships table
        cursor.execute("""
        CREATE TABLE character_relationships (
            id INTEGER PRIMARY KEY,
            character1_id INTEGER NOT NULL,
            character2_id INTEGER NOT NULL,
            dynamic TEXT,
            FOREIGN KEY (character1_id) REFERENCES characters(id),
            FOREIGN KEY (character2_id) REFERENCES characters(id),
            UNIQUE(character1_id, character2_id)
        )
        """)
        
        # Create events table
        cursor.execute("""
        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            cause TEXT,
            consequences TEXT,
            status TEXT,
            chunk_tag TEXT
        )
        """)
        
        # Create factions table
        cursor.execute("""
        CREATE TABLE factions (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            ideology TEXT,
            hidden_agendas TEXT,
            current_activity TEXT
        )
        """)
        
        # Create locations table
        cursor.execute("""
        CREATE TABLE locations (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            status TEXT,
            historical_significance TEXT
        )
        """)
        
        # Create secrets table
        cursor.execute("""
        CREATE TABLE secrets (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL,
            entity_id INTEGER,
            entity_name TEXT,
            secret_type TEXT,
            details TEXT
        )
        """)
        
        # Create entity_state_history table
        cursor.execute("""
        CREATE TABLE entity_state_history (
            id INTEGER PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            state_type TEXT NOT NULL,
            state_value TEXT,
            episode TEXT NOT NULL,
            timestamp REAL,
            narrative_time TEXT,
            chunk_id TEXT,
            confidence REAL DEFAULT 1.0,
            source TEXT,
            notes TEXT,
            created_at REAL,
            is_active INTEGER DEFAULT 1
        )
        """)
        
        # Create entity_metadata table
        cursor.execute("""
        CREATE TABLE entity_metadata (
            id INTEGER PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            entity_name TEXT,
            current_states TEXT,
            last_updated REAL,
            last_episode TEXT,
            UNIQUE(entity_type, entity_id)
        )
        """)
        
        # Create relationship_state_history table
        cursor.execute("""
        CREATE TABLE relationship_state_history (
            id INTEGER PRIMARY KEY,
            entity1_type TEXT NOT NULL,
            entity1_id INTEGER NOT NULL,
            entity2_type TEXT NOT NULL,
            entity2_id INTEGER NOT NULL,
            relationship_type TEXT NOT NULL,
            state_value TEXT,
            symmetrical INTEGER DEFAULT 0,
            episode TEXT NOT NULL,
            timestamp REAL,
            narrative_time TEXT,
            chunk_id TEXT,
            confidence REAL DEFAULT 1.0,
            source TEXT,
            notes TEXT,
            created_at REAL,
            is_active INTEGER DEFAULT 1
        )
        """)
        
        # Create relationship_metadata table
        cursor.execute("""
        CREATE TABLE relationship_metadata (
            id INTEGER PRIMARY KEY,
            entity1_type TEXT NOT NULL,
            entity1_id INTEGER NOT NULL,
            entity2_type TEXT NOT NULL,
            entity2_id INTEGER NOT NULL,
            current_states TEXT,
            last_updated REAL,
            last_episode TEXT,
            UNIQUE(entity1_type, entity1_id, entity2_type, entity2_id)
        )
        """)
        
        # Create hierarchical memory tables
        cursor.execute("""
        CREATE TABLE top_level_memory (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            start_episode TEXT,
            end_episode TEXT,
            entities TEXT,
            embedding_id TEXT UNIQUE
        )
        """)
        
        cursor.execute("""
        CREATE TABLE mid_level_memory (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            episode TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            entities TEXT,
            parent_ids TEXT,
            embedding_id TEXT UNIQUE
        )
        """)
        
        cursor.execute("""
        CREATE TABLE memory_links (
            id INTEGER PRIMARY KEY,
            source_level TEXT NOT NULL,
            source_id TEXT NOT NULL,
            target_level TEXT NOT NULL,
            target_id TEXT NOT NULL,
            link_type TEXT NOT NULL,
            relevance_score REAL,
            UNIQUE(source_level, source_id, target_level, target_id, link_type)
        )
        """)
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created test database at {db_path}")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Error creating test database: {e}")
        return False

def populate_test_data(db_path: str) -> bool:
    """
    Populate the test database with sample data
    
    Args:
        db_path: Path to the test database file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Insert sample characters
        characters = [
            (1, "V", "Vincent, Vince", "A skilled mercenary with a mysterious past", "Rebellious, determined, adaptable"),
            (2, "Johnny Silverhand", "Robert John Linder", "Legendary rockerboy and anti-corporate terrorist", "Passionate, anti-authoritarian, charismatic"),
            (3, "Jackie Welles", "Jack, Jackie Boy", "V's best friend and partner in crime", "Loyal, ambitious, good-hearted")
        ]
        
        cursor.executemany(
            "INSERT INTO characters (id, name, aliases, description, personality) VALUES (?, ?, ?, ?, ?)",
            characters
        )
        
        # Insert sample character relationships
        relationships = [
            (1, 1, 2, "Complex mental construct relationship"),
            (2, 1, 3, "Best friends and partners")
        ]
        
        cursor.executemany(
            "INSERT INTO character_relationships (id, character1_id, character2_id, dynamic) VALUES (?, ?, ?, ?)",
            relationships
        )
        
        # Insert sample events
        events = [
            (1, "The Heist", "V and Jackie's ambition to become legends", "Jackie's death, V's implantation with the Relic", "Completed", "EP1_HEIST"),
            (2, "Meeting with Evelyn Parker", "The need to steal the Relic", "Planning The Heist", "Completed", "EP1_EVELYN")
        ]
        
        cursor.executemany(
            "INSERT INTO events (event_id, description, cause, consequences, status, chunk_tag) VALUES (?, ?, ?, ?, ?, ?)",
            events
        )
        
        # Insert sample factions
        factions = [
            (1, "Arasaka", "Corporate domination and control", "Seeking immortality tech", "Recovering from attack"),
            (2, "Afterlife", "Merc code and profit", "Running the major league merc scene", "Active in Night City")
        ]
        
        cursor.executemany(
            "INSERT INTO factions (id, name, ideology, hidden_agendas, current_activity) VALUES (?, ?, ?, ?, ?)",
            factions
        )
        
        # Insert sample locations
        locations = [
            (1, "Night City", "A megalopolis in Free State of Northern California", "Active", "Birthplace of corporate dominance"),
            (2, "Afterlife", "Legendary mercenary bar and hub", "Active", "Former morgue turned merc bar")
        ]
        
        cursor.executemany(
            "INSERT INTO locations (id, name, description, status, historical_significance) VALUES (?, ?, ?, ?, ?)",
            locations
        )
        
        # Insert entity states
        entity_states = [
            ("character", 1, "health", "critical", "S1E1", time.time(), None, "EP1_HEIST", 1.0, "system", "After the heist", time.time(), 1),
            ("character", 3, "status", "deceased", "S1E1", time.time(), None, "EP1_HEIST", 1.0, "system", "Died during the heist", time.time(), 1)
        ]
        
        cursor.executemany(
            """INSERT INTO entity_state_history 
               (entity_type, entity_id, state_type, state_value, episode, timestamp, narrative_time, 
                chunk_id, confidence, source, notes, created_at, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            entity_states
        )
        
        # Insert entity metadata
        entity_metadata = [
            ("character", 1, "V", json.dumps({"health": "critical"}), time.time(), "S1E1"),
            ("character", 3, "Jackie Welles", json.dumps({"status": "deceased"}), time.time(), "S1E1")
        ]
        
        cursor.executemany(
            """INSERT INTO entity_metadata
               (entity_type, entity_id, entity_name, current_states, last_updated, last_episode)
               VALUES (?, ?, ?, ?, ?, ?)""",
            entity_metadata
        )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Populated test database at {db_path} with sample data")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Error populating test database: {e}")
        return False

def test_connection_functions() -> bool:
    """Test database connection functions"""
    print("Testing connection functions...")
    
    try:
        # Test get_connection
        conn = get_connection()
        if not conn:
            print("✗ Failed to get database connection")
            return False
            
        print("✓ Successfully created database connection")
        
        # Test connection caching
        conn2 = get_connection()
        if conn is not conn2:
            print("✗ Connection caching failed")
            return False
            
        print("✓ Connection caching works")
        
        return True
        
    except Exception as e:
        print(f"✗ Connection function tests failed: {e}")
        return False

def test_character_functions() -> bool:
    """Test character-related functions"""
    print("Testing character functions...")
    
    try:
        # Test get_characters
        characters = get_characters()
        if len(characters) != 3:
            print(f"✗ Expected 3 characters, got {len(characters)}")
            return False
            
        print(f"✓ Successfully retrieved {len(characters)} characters")
        
        # Test get_character_by_id
        character = get_character_by_id(1)
        if not character or character["name"] != "V":
            print(f"✗ Failed to retrieve character by ID or incorrect data returned")
            return False
            
        print(f"✓ Successfully retrieved character by ID: {character['name']}")
        
        # Test get_character_by_name
        character = get_character_by_name("Johnny Silverhand")
        if not character or character["id"] != 2:
            print(f"✗ Failed to retrieve character by name or incorrect data returned")
            return False
            
        print(f"✓ Successfully retrieved character by name: {character['name']}")
        
        # Test search_characters
        results = search_characters("mercenary")
        if len(results) != 1 or results[0]["name"] != "V":
            print(f"✗ Character search failed or incorrect results")
            return False
            
        print(f"✓ Character search returned expected results")
        
        return True
        
    except Exception as e:
        print(f"✗ Character function tests failed: {e}")
        return False

def test_relationship_functions() -> bool:
    """Test relationship-related functions"""
    print("Testing relationship functions...")
    
    try:
        # Test update_relationship_state and get_relationship_current_state
        success = update_relationship_state(
            "character", 1, "character", 2, "trust", "low", 
            episode="S1E1", symmetrical=True
        )
        
        if not success:
            print("✗ Failed to update relationship state")
            return False
            
        print("✓ Successfully updated relationship state")
        
        # Verify relationship was stored
        state = get_relationship_current_state("character", 1, "character", 2, "trust")
        if state != "low":
            print(f"✗ Expected relationship state 'low', got '{state}'")
            return False
            
        print(f"✓ Successfully retrieved relationship state: {state}")
        
        # Test symmetrical relationship (other direction)
        state = get_relationship_current_state("character", 2, "character", 1, "trust")
        if state != "low":
            print(f"✗ Symmetrical relationship not working, expected 'low', got '{state}'")
            return False
            
        print(f"✓ Successfully verified symmetrical relationship state: {state}")
        
        return True
        
    except Exception as e:
        print(f"✗ Relationship function tests failed: {e}")
        return False

def test_entity_state_functions() -> bool:
    """Test entity state-related functions"""
    print("Testing entity state functions...")
    
    try:
        # Test update_entity_state and get_entity_current_state
        success = update_entity_state(
            "character", 1, "location", "Afterlife", 
            episode="S1E2", source="system"
        )
        
        if not success:
            print("✗ Failed to update entity state")
            return False
            
        print("✓ Successfully updated entity state")
        
        # Verify state was stored
        state = get_entity_current_state("character", 1, "location")
        if state != "Afterlife":
            print(f"✗ Expected entity state 'Afterlife', got '{state}'")
            return False
            
        print(f"✓ Successfully retrieved entity state: {state}")
        
        # Test get_entity_state_history
        history = get_entity_state_history("character", 1)
        if len(history) < 2:
            print(f"✗ Expected at least 2 state history entries, got {len(history)}")
            return False
            
        print(f"✓ Successfully retrieved entity state history with {len(history)} entries")
        
        # Test get_entity_state_at_episode
        episode_state = get_entity_state_at_episode("character", 1, "S1E1", "health")
        if episode_state != "critical":
            print(f"✗ Expected entity state at episode 'critical', got '{episode_state}'")
            return False
            
        print(f"✓ Successfully retrieved entity state at specific episode: {episode_state}")
        
        return True
        
    except Exception as e:
        print(f"✗ Entity state function tests failed: {e}")
        return False

def test_memory_functions() -> bool:
    """Test hierarchical memory functions"""
    print("Testing memory functions...")
    
    try:
        # Test add_top_level_memory
        top_id = add_top_level_memory(
            memory_type="story_arc",
            title="The Relic Storyline",
            description="V's journey to remove the Relic from their head",
            start_episode="S1E1"
        )
        
        if not top_id:
            print("✗ Failed to add top-level memory")
            return False
            
        print(f"✓ Successfully added top-level memory with ID: {top_id}")
        
        # Test add_mid_level_memory
        mid_id = add_mid_level_memory(
            memory_type="episode_summary",
            episode="S1E1",
            title="The Heist Goes Wrong",
            content="V and Jackie's heist to steal the Relic ends in tragedy",
            parent_ids=[top_id]
        )
        
        if not mid_id:
            print("✗ Failed to add mid-level memory")
            return False
            
        print(f"✓ Successfully added mid-level memory with ID: {mid_id}")
        
        # Test get_memory_level
        top_memories = get_memory_level("top")
        if len(top_memories) != 1:
            print(f"✗ Expected 1 top-level memory, got {len(top_memories)}")
            return False
            
        print(f"✓ Successfully retrieved top-level memories")
        
        # Test get_memory_links
        links = get_memory_links("top", str(top_id))
        if not links or len(links) != 1:
            print(f"✗ Expected 1 memory link, got {len(links) if links else 0}")
            return False
            
        print(f"✓ Successfully retrieved memory links")
        
        return True
        
    except Exception as e:
        print(f"✗ Memory function tests failed: {e}")
        return False

def test_episode_comparison() -> bool:
    """Test the episode comparison function"""
    print("Testing episode comparison function...")
    
    try:
        # Test same episode
        if compare_episodes("S1E1", "S1E1") != 0:
            print("✗ Same episodes should return 0")
            return False
            
        # Test earlier season
        if compare_episodes("S1E5", "S2E1") != -1:
            print("✗ Earlier season should return -1")
            return False
            
        # Test later season
        if compare_episodes("S2E1", "S1E5") != 1:
            print("✗ Later season should return 1")
            return False
            
        # Test earlier episode same season
        if compare_episodes("S1E1", "S1E2") != -1:
            print("✗ Earlier episode in same season should return -1")
            return False
            
        # Test later episode same season
        if compare_episodes("S1E2", "S1E1") != 1:
            print("✗ Later episode in same season should return 1")
            return False
            
        # Test chapter format
        if compare_episodes("Chapter 1", "Chapter 2") != -1:
            print("✗ Earlier chapter should return -1")
            return False
            
        print("✓ Episode comparison function passes all tests")
        return True
        
    except Exception as e:
        print(f"✗ Episode comparison tests failed: {e}")
        return False

def run_all_tests() -> bool:
    """Run all tests and return overall success status"""
    print("\n=== Running SQLite Database Module Tests ===\n")
    
    # Create test database
    test_db_path = "test_nightcity.db"
    if not create_test_database(test_db_path):
        print("✗ Failed to create test database")
        return False
        
    # Update settings to use test database
    global settings
    original_db_path = settings["db_path"]
    settings["db_path"] = test_db_path
    
    try:
        # Populate test data
        if not populate_test_data(test_db_path):
            print("✗ Failed to populate test database")
            return False
            
        # Run test suites
        tests = [
            test_connection_functions,
            test_character_functions,
            test_relationship_functions,
            test_entity_state_functions,
            test_memory_functions,
            test_episode_comparison
        ]
        
        success = True
        for test_func in tests:
            test_result = test_func()
            success = success and test_result
            print()  # Add newline for readability
            
        if success:
            print("\n✓ All tests passed successfully!")
        else:
            print("\n✗ Some tests failed!")
            
        return success
        
    except Exception as e:
        print(f"\n✗ Test execution failed: {e}")
        return False
        
    finally:
        # Restore original settings
        settings["db_path"] = original_db_path
        
        # Close all connections
        close_all_connections()
        
        # Cleanup: remove test database
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except:
            pass

def main():
    """
    Main function for the module
    
    When run as a script, this function parses command line arguments
    and performs the requested actions.
    """
    parser = argparse.ArgumentParser(description="SQLite Database Access Module for Night City Stories")
    parser.add_argument("--test", action="store_true", help="Run module tests")
    parser.add_argument("--init", action="store_true", help="Initialize database with schema")
    parser.add_argument("--clear", action="store_true", help="Clear all data from database")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()
    
    # Load settings
    load_settings()
    
    # Set verbose logging if requested
    if args.verbose:
        settings["verbose_logging"] = True
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    if args.test:
        # Run tests
        import prove
        if hasattr(prove, 'run_test_suite') and callable(getattr(prove, 'run_test_suite')):
            # Use centralized testing if available
            try:
                result = prove.run_test_suite("db_sqlite", run_all_tests)
                return 0 if result else 1
            except Exception as e:
                logger.error(f"Error running tests through prove module: {e}")
                # Fall back to direct testing
                return 0 if run_all_tests() else 1
        else:
            # Run tests directly
            return 0 if run_all_tests() else 1
    
    elif args.init:
        # Initialize database schema
        db_path = settings["db_path"]
        if os.path.exists(db_path):
            logger.warning(f"Database already exists at {db_path}")
            return 1
        
        if create_test_database(db_path):
            logger.info(f"Database initialized at {db_path}")
            return 0
        else:
            logger.error(f"Failed to initialize database at {db_path}")
            return 1
    
    elif args.clear:
        # Clear all data from database
        db_path = settings["db_path"]
        if not os.path.exists(db_path):
            logger.warning(f"Database does not exist at {db_path}")
            return 1
        
        try:
            # Close all connections
            close_all_connections()
            
            # Remove and recreate the database
            os.remove(db_path)
            create_test_database(db_path)
            
            logger.info(f"Database cleared at {db_path}")
            return 0
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
            return 1
    
    else:
        # No arguments provided, show help
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())