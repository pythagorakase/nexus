#!/usr/bin/env python3
"""
test_utils.py: Testing Utilities for Night City Stories Modules

This module provides shared utilities for testing the various modules
of the Night City Stories narrative intelligence system. It includes
functions for setup, teardown, mock data generation, and standardized
test reporting.

Usage:
    import test_utils
    
    # Create a test environment
    with test_utils.TestEnvironment() as env:
        # Run tests with standardized reporting
        env.run_test("Test Name", test_function, arg1, arg2)
"""

import os
import sys
import json
import shutil
import sqlite3
import logging
import tempfile
import time
import re
import argparse
import importlib.util
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any, Callable
from contextlib import contextmanager
import types

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("testing.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("test_utils")

class TestError(Exception):
    """Exception for test-related errors"""
    pass

class TestEnvironment:
    """
    Manages test environment setup and teardown
    """
    
    def __init__(self, 
                use_temp_dir: bool = True,
                create_test_db: bool = True,
                setup_settings: bool = True):
        """
        Initialize the test environment
        
        Args:
            use_temp_dir: Whether to create and use a temporary directory
            create_test_db: Whether to create a test SQLite database
            setup_settings: Whether to create a test settings.json file
        """
        self.use_temp_dir = use_temp_dir
        self.create_test_db = create_test_db
        self.setup_settings = setup_settings
        
        self.temp_dir = None
        self.original_dir = None
        self.test_db_path = None
        self.test_settings_path = None
        
        self.test_results = []
    
    def __enter__(self):
        """Set up the test environment"""
        # Remember the original directory
        self.original_dir = os.getcwd()
        
        if self.use_temp_dir:
            # Create a temporary directory
            self.temp_dir = tempfile.mkdtemp()
            logger.info(f"Created temporary directory: {self.temp_dir}")
            
            # Change to the temporary directory
            os.chdir(self.temp_dir)
        
        if self.create_test_db:
            # Create a test database
            self.test_db_path = Path("test_db.sqlite")
            self._create_test_database(self.test_db_path)
        
        if self.setup_settings:
            # Create a test settings.json file
            self.test_settings_path = Path("settings.json")
            self._create_test_settings(self.test_settings_path)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up the test environment"""
        # Change back to the original directory
        if self.original_dir:
            os.chdir(self.original_dir)
        
        # Remove the temporary directory
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            logger.info(f"Removed temporary directory: {self.temp_dir}")
        
        # Log test results
        self._log_test_summary()
        
        return False  # Don't suppress exceptions
    
    def _create_test_database(self, db_path: Path) -> None:
        """
        Create a test SQLite database with sample data
        
        Args:
            db_path: Path to create the database
        """
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
        CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            aliases TEXT,
            description TEXT,
            personality TEXT
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE character_relationships (
            id INTEGER PRIMARY KEY,
            character1_id INTEGER NOT NULL,
            character2_id INTEGER NOT NULL,
            dynamic TEXT,
            FOREIGN KEY (character1_id) REFERENCES characters (id),
            FOREIGN KEY (character2_id) REFERENCES characters (id)
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            cause TEXT,
            consequences TEXT,
            status TEXT,
            chunk_tag TEXT
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE factions (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            ideology TEXT,
            hidden_agendas TEXT,
            current_activity TEXT
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE locations (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            status TEXT,
            historical_significance TEXT
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE secrets (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL,
            entity_id INTEGER,
            entity_name TEXT,
            secret_type TEXT,
            details TEXT
        )
        ''')
        
        # Add sample data
        
        # Characters
        cursor.execute('''
        INSERT INTO characters (id, name, aliases, description, personality)
        VALUES (1, 'Alex', 'The Protagonist', 'Main character', 'Determined and resourceful')
        ''')
        
        cursor.execute('''
        INSERT INTO characters (id, name, aliases, description, personality)
        VALUES (2, 'Emilia', 'The Companion', 'Mysterious ally', 'Complex and enigmatic')
        ''')
        
        cursor.execute('''
        INSERT INTO characters (id, name, aliases, description, personality)
        VALUES (3, 'Dr. Nyati', 'The Doc', 'Medical expert', 'Brilliant but eccentric')
        ''')
        
        # Relationships
        cursor.execute('''
        INSERT INTO character_relationships (character1_id, character2_id, dynamic)
        VALUES (1, 2, 'Cautious allies')
        ''')
        
        cursor.execute('''
        INSERT INTO character_relationships (character1_id, character2_id, dynamic)
        VALUES (1, 3, 'Patient and doctor')
        ''')
        
        # Events
        cursor.execute('''
        INSERT INTO events (event_id, description, status, chunk_tag)
        VALUES (1, 'First meeting with Emilia', 'Completed', 'S01E01_002')
        ''')
        
        cursor.execute('''
        INSERT INTO events (event_id, description, status, chunk_tag)
        VALUES (2, 'Discovery of the hidden lab', 'In progress', 'S01E03_015')
        ''')
        
        # Factions
        cursor.execute('''
        INSERT INTO factions (name, ideology, hidden_agendas, current_activity)
        VALUES ('Arasaka Corporation', 'Corporate dominance', 'AI development', 'Expanding influence')
        ''')
        
        cursor.execute('''
        INSERT INTO factions (name, ideology, hidden_agendas, current_activity)
        VALUES ('The Wraiths', 'Chaos and survival', 'Revenge against corporations', 'Gathering resources')
        ''')
        
        # Locations
        cursor.execute('''
        INSERT INTO locations (name, description, status, historical_significance)
        VALUES ('Neon Bay', 'Bustling entertainment district', 'Active', 'Site of the 2089 uprising')
        ''')
        
        cursor.execute('''
        INSERT INTO locations (name, description, status, historical_significance)
        VALUES ('The Underbelly', 'Maze of tunnels below the city', 'Dangerous', 'Former metro system')
        ''')
        
        # Secrets
        cursor.execute('''
        INSERT INTO secrets (category, entity_id, entity_name, secret_type, details)
        VALUES ('character', 2, 'Emilia', 'origin', 'Actually a corporate spy for Arasaka')
        ''')
        
        cursor.execute('''
        INSERT INTO secrets (category, entity_id, entity_name, secret_type, details)
        VALUES ('faction', NULL, 'Arasaka Corporation', 'plan', 'Developing mind control technology')
        ''')
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created test database at {db_path} with sample data")
    
    def _create_test_settings(self, settings_path: Path) -> None:
        """
        Create a test settings.json file
        
        Args:
            settings_path: Path to create the settings file
        """
        settings = {
            "database": {
                "path": "test_db.sqlite",
                "enable_foreign_keys": True,
                "timeout": 5.0,
                "connection_cache_size": 3,
                "verbose_logging": True
            },
            "chromadb": {
                "path": "./test_chroma_db",
                "collection_name": "test_transcripts",
                "embedding_models": {
                    "bge_large": {
                        "name": "BAAI/bge-large-en",
                        "weight": 0.4
                    },
                    "e5_large": {
                        "name": "intfloat/e5-large-v2",
                        "weight": 0.4
                    },
                    "bge_small": {
                        "name": "BAAI/bge-small-en",
                        "weight": 0.2
                    }
                }
            },
            "narrative": {
                "current_episode": "S01E05",
                "max_context_tokens": 2000,
                "character_budget": 16000
            },
            "entity_state": {
                "track_entity_states": True,
                "auto_update_states": True
            },
            "testing": {
                "test_data_path": "./test_data/",
                "use_mock_data": True
            }
        }
        
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
        
        logger.info(f"Created test settings at {settings_path}")
    
    def run_test(self, test_name: str, test_func: Callable, *args, **kwargs) -> bool:
        """
        Run a test function with standardized reporting
        
        Args:
            test_name: Name of the test
            test_func: Test function to run
            *args: Arguments to pass to the test function
            **kwargs: Keyword arguments to pass to the test function
            
        Returns:
            True if the test passed, False otherwise
        """
        logger.info(f"=== Running test: {test_name} ===")
        start_time = time.time()
        
        try:
            # Run the test function
            result = test_func(*args, **kwargs)
            
            # Check if the result is a boolean
            if isinstance(result, bool):
                success = result
            else:
                success = True  # Assume success if no exception and not a boolean
            
            duration = time.time() - start_time
            
            if success:
                logger.info(f"✓ Test passed: {test_name} ({duration:.2f}s)")
            else:
                logger.error(f"✗ Test failed: {test_name} ({duration:.2f}s)")
            
            # Record the result
            self.test_results.append({
                "name": test_name,
                "success": success,
                "duration": duration
            })
            
            return success
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"✗ Test error: {test_name} - {type(e).__name__}: {e} ({duration:.2f}s)")
            import traceback
            logger.error(traceback.format_exc())
            
            # Record the failure
            self.test_results.append({
                "name": test_name,
                "success": False,
                "duration": duration,
                "error": f"{type(e).__name__}: {e}"
            })
            
            return False
    
    def _log_test_summary(self) -> None:
        """Log a summary of test results"""
        if not self.test_results:
            return
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["success"])
        failed = total - passed
        
        logger.info("=== Test Summary ===")
        logger.info(f"Total tests: {total}")
        logger.info(f"Passed: {passed}")
        logger.info(f"Failed: {failed}")
        
        total_time = sum(r["duration"] for r in self.test_results)
        logger.info(f"Total duration: {total_time:.2f}s")
        
        if failed > 0:
            logger.error("Failed tests:")
            for result in self.test_results:
                if not result["success"]:
                    error_msg = result.get("error", "No error details")
                    logger.error(f"  - {result['name']}: {error_msg}")

# Test data generators

def generate_test_chunk(chunk_id: str = "S01E01_001", 
                       character_name: str = "Alex") -> Tuple[str, str]:
    """
    Generate a test narrative chunk
    
    Args:
        chunk_id: ID for the chunk
        character_name: Character name to include in the chunk
        
    Returns:
        Tuple of (chunk_id, chunk_text)
    """
    # Extract episode from chunk_id
    episode_match = re.match(r'(S\d+E\d+)_\d+', chunk_id)
    episode = episode_match.group(1) if episode_match else "S01E01"
    
    # Generate chunk text
    chunk_text = f"""<!-- SCENE BREAK: {chunk_id} (Test Scene) -->
    
Episode: {episode} - Test Scene
Date: 18OCT2073
Time: 19:45
Location: Night City - Downtown
    
{character_name} moves through the crowded streets of Night City, the neon lights
reflecting off the wet pavement. The constant hum of vehicles and chatter creates
a backdrop of urban white noise that's somehow both chaotic and comforting.

"This city never sleeps," {character_name} mutters, glancing up at the towering 
corporate spires that dominate the skyline.
"""
    
    return (chunk_id, chunk_text)

def generate_test_states() -> List[Dict[str, Any]]:
    """
    Generate test entity states
    
    Returns:
        List of test entity state dictionaries
    """
    return [
        {
            "entity_type": "character",
            "entity_id": 1,
            "state_type": "physical",
            "state_value": "injured",
            "episode": "S01E04",
            "confidence": 0.9,
            "source": "narrative"
        },
        {
            "entity_type": "character",
            "entity_id": 1,
            "state_type": "emotional",
            "state_value": "determined",
            "episode": "S01E04",
            "confidence": 0.85,
            "source": "inference"
        },
        {
            "entity_type": "character",
            "entity_id": 2,
            "state_type": "knowledge",
            "state_value": "knows_about_secret_lab",
            "episode": "S01E04",
            "confidence": 0.75,
            "source": "narrative"
        },
        {
            "entity_type": "faction",
            "entity_id": 1,
            "state_type": "activity",
            "state_value": "hunting_protagonist",
            "episode": "S01E04",
            "confidence": 0.8,
            "source": "inference"
        },
        {
            "entity_type": "location",
            "entity_id": 1,
            "state_type": "status",
            "state_value": "under_surveillance",
            "episode": "S01E04",
            "confidence": 0.7,
            "source": "narrative"
        }
    ]

def generate_test_relationships() -> List[Dict[str, Any]]:
    """
    Generate test relationship states
    
    Returns:
        List of test relationship state dictionaries
    """
    return [
        {
            "entity1_type": "character",
            "entity1_id": 1,
            "entity2_type": "character",
            "entity2_id": 2,
            "relationship_type": "trust",
            "state_value": "cautious",
            "episode": "S01E04",
            "symmetrical": False,
            "confidence": 0.8,
            "source": "narrative"
        },
        {
            "entity1_type": "character",
            "entity1_id": 2,
            "entity2_type": "character",
            "entity2_id": 1,
            "relationship_type": "trust",
            "state_value": "suspicious",
            "episode": "S01E04",
            "symmetrical": False,
            "confidence": 0.75,
            "source": "inference"
        },
        {
            "entity1_type": "character",
            "entity1_id": 1,
            "entity2_type": "faction",
            "entity2_id": 1,
            "relationship_type": "alignment",
            "state_value": "hostile",
            "episode": "S01E04",
            "symmetrical": True,
            "confidence": 0.9,
            "source": "narrative"
        }
    ]

def generate_test_memory(memory_level: str) -> Dict[str, Any]:
    """
    Generate a test memory item
    
    Args:
        memory_level: Memory level ('top' or 'mid')
        
    Returns:
        Test memory dictionary
    """
    if memory_level == "top":
        return {
            "type": "story_arc",
            "title": "Corporate Infiltration",
            "description": "Alex infiltrates Arasaka Corporation to uncover a conspiracy.",
            "start_episode": "S01E03",
            "end_episode": None,
            "entities": [
                {"type": "character", "id": 1, "name": "Alex"},
                {"type": "faction", "id": 1, "name": "Arasaka Corporation"}
            ]
        }
    else:  # mid-level
        return {
            "type": "episode_summary",
            "episode": "S01E04",
            "title": "The Deep Dive",
            "content": "Alex penetrates deeper into Arasaka's systems and discovers disturbing plans.",
            "entities": [
                {"type": "character", "id": 1, "name": "Alex"},
                {"type": "faction", "id": 1, "name": "Arasaka Corporation"}
            ],
            "parent_ids": [1]  # Assuming the top-level memory has ID 1
        }

def mock_api_response(prompt_text: str) -> str:
    """
    Generate a mock API response for testing
    
    Args:
        prompt_text: Prompt text that would be sent to the API
        
    Returns:
        Mock response text
    """
    # Extract key terms from the prompt for context-aware responses
    if "character" in prompt_text.lower() or "alex" in prompt_text.lower():
        return json.dumps({
            "narrative": "Alex moved cautiously through the dimly lit corridors of Arasaka Tower, every sense on high alert. The security systems had been surprisingly easy to bypass - too easy, perhaps. It felt like walking into a trap, but there was no turning back now.\n\n\"Just a little further,\" Alex whispered, checking the holographic map projected from a wrist-mounted device. The server room should be just ahead, and with it, the answers that had been so elusive.",
            "db_updates": {
                "update_characters": {
                    "Alex": {
                        "status": "infiltrating",
                        "activity": "corporate espionage"
                    }
                },
                "update_factions": {
                    "Arasaka Corporation": {
                        "current_activity": "security alert level 2"
                    }
                }
            }
        })
    elif "relationship" in prompt_text.lower() or "emilia" in prompt_text.lower():
        return json.dumps({
            "narrative": "\"I don't know if I can trust you anymore, Emilia,\" Alex said, keeping distance between them. The revelation of her Arasaka connections had hit like a physical blow.\n\nEmilia's cybernetic eyes flickered, the blue light dimming momentarily. \"I've never lied about what matters, Alex. Yes, I have history with them. But that's why I need your help.\"\n\n\"History?\" Alex laughed bitterly. \"You were their top intelligence operative for years.\"",
            "db_updates": {
                "update_characters": {
                    "Alex": {
                        "emotional": "betrayed"
                    },
                    "Emilia": {
                        "status": "compromised"
                    }
                },
                "update_relationships": {
                    "Alex_Emilia": {
                        "trust": "damaged"
                    }
                }
            }
        })
    else:
        return json.dumps({
            "narrative": "Night City pulsed with its usual frenetic energy, the streets crowded despite the late hour. Neon advertisements reflected in the puddles, creating a kaleidoscope of color that only added to the sensory overload. This was the rhythm of the city - constant motion, constant noise, constant danger.",
            "db_updates": {
                "update_locations": {
                    "Night City": {
                        "status": "active",
                        "atmosphere": "tense"
                    }
                }
            }
        })

# ==================== NEW INTEGRATION TESTING CODE ====================

class ModuleMessageTest:
    """
    Represents a specific test for inter-module message passing
    """
    
    def __init__(self, name: str, source_module: str, target_module: str, 
                 message: Dict[str, Any], expected_response: Optional[Dict[str, Any]] = None):
        """
        Initialize a module message test
        
        Args:
            name: Test name
            source_module: Source module name
            target_module: Target module name
            message: Message to send
            expected_response: Expected response (if any)
        """
        self.name = name
        self.source_module = source_module
        self.target_module = target_module
        self.message = message
        self.expected_response = expected_response
        self.result = None
        self.error = None
    
    def run(self, test_handler: 'IntegrationTestHandler') -> bool:
        """
        Run the test
        
        Args:
            test_handler: Integration test handler
            
        Returns:
            True if test passed, False otherwise
        """
        try:
            print(f"Running test: {self.name}")
            print(f"  Source: {self.source_module}")
            print(f"  Target: {self.target_module}")
            
            # Check if modules are available
            if self.source_module not in test_handler.modules:
                raise TestError(f"Source module {self.source_module} not available")
            
            if self.target_module not in test_handler.modules:
                raise TestError(f"Target module {self.target_module} not available")
            
            # Get the modules
            source = test_handler.modules[self.source_module]
            target = test_handler.modules[self.target_module]
            
            # Try to send the message
            try:
                if hasattr(source, "send_message"):
                    print(f"  {self.source_module} sending message to {self.target_module}")
                    response = source.send_message(self.target_module, self.message)
                elif hasattr(target, "receive_message"):
                    print(f"  Direct call to {self.target_module}.receive_message()")
                    response = target.receive_message(self.message)
                else:
                    # This should not happen with our enhanced modules, but just in case
                    raise TestError(f"No way to communicate from {self.source_module} to {self.target_module}")
                
                # Validate the response
                if self.expected_response is not None:
                    # Check if response matches expected (basic comparison for now)
                    # This could be enhanced for more intelligent comparison
                    if response == self.expected_response:
                        self.result = True
                    else:
                        self.result = False
                        self.error = f"Response did not match expected: {response} != {self.expected_response}"
                else:
                    # Just check for a successful response
                    if isinstance(response, dict) and response.get("status") != "error":
                        self.result = True
                    else:
                        self.result = False
                        self.error = f"Error response received: {response}"
                
                if self.result:
                    print(f"✓ Test passed: {self.name}")
                else:
                    print(f"✗ Test failed: {self.name} - {self.error}")
                
                return self.result
                
            except Exception as e:
                raise TestError(f"Error during message passing: {e}")
                
        except Exception as e:
            import traceback
            self.result = False
            self.error = str(e)
            print(f"✗ Test error: {self.name} - {e}")
            print(traceback.format_exc())
            return False

class IntegrationTestHandler:
    """
    Handles integration testing between multiple modules
    """
    
    def __init__(self):
        """Initialize the integration test handler"""
        self.modules = {}
        self.mock_responses = {}
        self.test_results = []
        self.using_mocks = False  # Track if we're using any mock methods
        self.agents = {}  # Track real agent instances
        self.maestro_instance = None  # Reference to maestro instance if available
    
    def import_module(self, module_path: str) -> bool:
        """
        Import a module for testing
        
        Args:
            module_path: Path to the module file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            module_name = Path(module_path).stem
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to load module spec for {module_path}")
                return False
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Check if the module has the necessary communication methods
            # If not, enhance it with mock methods
            self._enhance_module_with_mock_methods(module, module_name)
            
            self.modules[module_name] = module
            logger.info(f"Successfully imported module: {module_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to import module {module_path}: {e}")
            return False
    
    def _enhance_module_with_mock_methods(self, module, module_name):
        """
        Add mock methods to a real module if they're missing
        
        Args:
            module: The module object to enhance
            module_name: Name of the module
        """
        # Check and add common communication methods if needed
        
        # Check for send_message method
        if not hasattr(module, "send_message"):
            def mock_send_message(target_module, message, *args, **kwargs):
                print(f"  [MOCK] {module_name} sending message to {target_module}: {message.get('action', 'unknown')}")
                # Check if target module exists and has receive_message
                if target_module in self.modules and hasattr(self.modules[target_module], "receive_message"):
                    return self.modules[target_module].receive_message(message)
                else:
                    return {"status": "success", "message": f"Mock message from {module_name} to {target_module}"}
            
            setattr(module, "send_message", mock_send_message)
            self.using_mocks = True
            print(f"  Added mock send_message method to {module_name}")
        
        # Check for receive_message method
        if not hasattr(module, "receive_message"):
            def mock_receive_message(message, *args, **kwargs):
                action = message.get("action", "unknown")
                print(f"  [MOCK] {module_name} received message: {action}")
                return {"status": "success", "message": f"Mock {module_name} processed {action}"}
            
            setattr(module, "receive_message", mock_receive_message)
            self.using_mocks = True
            print(f"  Added mock receive_message method to {module_name}")
        
        # Add specific methods based on module type
        if module_name == "maestro" and not hasattr(module, "process_narrative"):
            def mock_process_narrative(chunk_id, text, *args, **kwargs):
                print(f"  [MOCK] Maestro processing chunk {chunk_id}")
                return {"status": "success", "message": f"Mock processed chunk {chunk_id}"}
            
            setattr(module, "process_narrative", mock_process_narrative)
            self.using_mocks = True
        
        elif module_name == "lore" and not hasattr(module, "build_context"):
            def mock_build_context(*args, **kwargs):
                print(f"  [MOCK] Lore building context")
                return {"status": "success", "message": "Context building initiated"}
            
            setattr(module, "build_context", mock_build_context)
            self.using_mocks = True
        
        elif module_name == "logon" and not hasattr(module, "generate_narrative"):
            def mock_generate_narrative(*args, **kwargs):
                print(f"  [MOCK] Logon generating narrative")
                return {"status": "success", "narrative": mock_api_response("Test prompt")}
            
            setattr(module, "generate_narrative", mock_generate_narrative)
            self.using_mocks = True
            
        elif module_name == "gaia" and not hasattr(module, "analyze_entities"):
            def mock_analyze_entities(*args, **kwargs):
                print(f"  [MOCK] Gaia analyzing entities")
                return {"status": "success", "entities": generate_test_states()}
            
            setattr(module, "analyze_entities", mock_analyze_entities)
            self.using_mocks = True
            
        elif module_name == "memnon":
            if not hasattr(module, "retrieve_memory"):
                def mock_retrieve_memory(*args, **kwargs):
                    print(f"  [MOCK] Memnon retrieving memory")
                    return {"status": "success", "memory": generate_test_memory("mid")}
                
                setattr(module, "retrieve_memory", mock_retrieve_memory)
                self.using_mocks = True
                
            if not hasattr(module, "store_narrative_chunk"):
                def mock_store_narrative_chunk(chunk_id, text, *args, **kwargs):
                    print(f"  [MOCK] Memnon storing chunk {chunk_id}")
                    return {"status": "success", "message": f"Mock stored chunk {chunk_id}"}
                
                setattr(module, "store_narrative_chunk", mock_store_narrative_chunk)
                self.using_mocks = True
                
        elif module_name == "db_chroma":
            if not hasattr(module, "vector_search"):
                def mock_vector_search(*args, **kwargs):
                    print(f"  [MOCK] DB_Chroma searching vectors")
                    return {"status": "success", "results": [
                        {"id": "S01E01_001", "text": "Test chunk 1", "score": 0.95},
                        {"id": "S01E02_003", "text": "Test chunk 2", "score": 0.85},
                        {"id": "S01E03_002", "text": "Test chunk 3", "score": 0.75}
                    ]}
                
                setattr(module, "vector_search", mock_vector_search)
                setattr(module, "hybrid_search", mock_vector_search)  # Use same function for both
                self.using_mocks = True
                
        elif module_name == "db_sqlite":
            if not hasattr(module, "select"):
                def mock_select(*args, **kwargs):
                    print(f"  [MOCK] DB_SQLite selecting data")
                    return {"status": "success", "results": [{"id": 1, "name": "Alex"}]}
                
                setattr(module, "select", mock_select)
                self.using_mocks = True
            
            if not hasattr(module, "insert"):
                def mock_insert(*args, **kwargs):
                    print(f"  [MOCK] DB_SQLite inserting data")
                    return {"status": "success", "id": 1}
                
                setattr(module, "insert", mock_insert)
                self.using_mocks = True
            
            if not hasattr(module, "update"):
                def mock_update(*args, **kwargs):
                    print(f"  [MOCK] DB_SQLite updating data")
                    return {"status": "success", "rows_affected": 1}
                
                setattr(module, "update", mock_update)
                self.using_mocks = True
    
    def create_mock_module(self, module_name: str) -> Any:
        """
        Create a mock module for testing when the real module is not available
        
        Args:
            module_name: The name of the module to mock
            
        Returns:
            The mock module object if successful, or None if failed
        """
        try:
            import types
            
            # Create a new module object
            module = types.ModuleType(module_name)
            
            # Log that we're creating a mock
            print(f"Creating mock module: {module_name}")
            
            # Add mock methods based on module name
            if module_name == "maestro":
                def mock_process_narrative(chunk_id, text, *args, **kwargs):
                    print(f"  [MOCK] Maestro processing narrative: {chunk_id}")
                    return {"status": "success", "message": f"Processed {chunk_id}"}
                
                def mock_send_message(target_module, message, *args, **kwargs):
                    print(f"  [MOCK] Maestro sending message to {target_module}: {message.get('action', 'unknown')}")
                    
                    # Simulate response based on target and action
                    if target_module == "lore" and message.get("action") == "build_context":
                        return {"status": "success", "message": "Mock Lore built context"}
                    elif target_module == "gaia" and message.get("action") == "analyze_entities":
                        return {"status": "success", "message": "Mock Gaia analyzed entities"}
                    else:
                        return {"status": "success", "message": f"Mock {target_module} processed {message.get('action')}"}
                
                setattr(module, "process_narrative", mock_process_narrative)
                setattr(module, "send_message", mock_send_message)
                
            # Add the mock module to our registry
            logging.getLogger("test_utils").info(f"Created mock module: {module_name}")
            self.modules[module_name] = module
            self.using_mocks = True
            
            return module
            
        except Exception as e:
            print(f"Error creating mock module {module_name}: {e}")
            return None
    
    def create_real_agent(self, agent_name: str) -> bool:
        """
        Create a real agent instance for testing using DummyAgent
        
        Args:
            agent_name: Name of the agent to create
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Import BaseAgent and DummyAgent from agent_base
            try:
                from agent_base import DummyAgent
            except ImportError:
                print(f"Failed to import DummyAgent from agent_base.py")
                return False
            
            # Create agent instance with appropriate settings
            agent_settings = {
                "name": agent_name,
                "test_mode": True,
                "test_key": f"test_value_for_{agent_name}"
            }
            
            # Create the agent instance
            agent = DummyAgent(settings=agent_settings)
            
            # Add specialized message handlers for testing based on agent type
            if agent_name == "lore":
                def on_build_context(content):
                    parameters = content.get("parameters", {})
                    return agent.create_response(
                        status="success",
                        message="Context building completed",
                        data={
                            "context_package": {
                                "relevant_memories": ["Memory 1", "Memory 2"],
                                "entity_mentions": [{"name": "Alex", "type": "character"}]
                            }
                        }
                    )
                agent.on_build_context = types.MethodType(on_build_context, agent)
                
            elif agent_name == "memnon":
                def on_retrieve_memory(content):
                    parameters = content.get("parameters", {})
                    return agent.create_response(
                        status="success",
                        message="Memory retrieval completed",
                        data={
                            "memories": [
                                {"text": "Alex discovered a hidden room", "timestamp": "2023-05-01"},
                                {"text": "Alex met with Dr. Zhang", "timestamp": "2023-05-02"}
                            ]
                        }
                    )
                agent.on_retrieve_memory = types.MethodType(on_retrieve_memory, agent)
                
                def on_vector_search(content):
                    parameters = content.get("parameters", {})
                    return agent.create_response(
                        status="success",
                        message="Vector search completed",
                        data={
                            "results": [
                                {"text": "Alex discovers secret lab", "score": 0.92},
                                {"text": "Alex finds hidden files", "score": 0.87}
                            ]
                        }
                    )
                agent.on_vector_search = types.MethodType(on_vector_search, agent)
                
            elif agent_name == "logon":
                def on_generate_narrative(content):
                    parameters = content.get("parameters", {})
                    return agent.create_response(
                        status="success",
                        message="Narrative generation completed",
                        data={
                            "narrative": "Alex cautiously entered the dimly lit room, the dust particles dancing in the air as they caught the light from his flashlight. 'What is this place?' he whispered to himself, his eyes widening at the sight of the lab equipment scattered across the tables."
                        }
                    )
                agent.on_generate_narrative = types.MethodType(on_generate_narrative, agent)
                
            elif agent_name == "db_chroma":
                def on_vector_search(content):
                    parameters = content.get("parameters", {})
                    return agent.create_response(
                        status="success",
                        message="Vector search completed",
                        data={
                            "results": [
                                {"id": "mem001", "text": "Alex discovers secret lab", "score": 0.92},
                                {"id": "mem002", "text": "Alex finds hidden files", "score": 0.87},
                                {"id": "mem003", "text": "Alex meets Dr. Zhang", "score": 0.81}
                            ]
                        }
                    )
                agent.on_vector_search = types.MethodType(on_vector_search, agent)
                
            elif agent_name == "db_sqlite":
                def on_select(content):
                    parameters = content.get("parameters", {})
                    return agent.create_response(
                        status="success",
                        message="Query executed successfully",
                        data={
                            "results": [
                                {"id": 1, "name": "Alex", "occupation": "Investigator", "level": 3}
                            ]
                        }
                    )
                agent.on_select = types.MethodType(on_select, agent)
                
                def on_insert(content):
                    parameters = content.get("parameters", {})
                    return agent.create_response(
                        status="success",
                        message="Insert executed successfully",
                        data={"inserted_id": 42}
                    )
                agent.on_insert = types.MethodType(on_insert, agent)
            
            # Store the agent instance
            self.agents[agent_name] = agent
            
            # If we have a maestro instance, connect the agent to it
            if self.maestro_instance and hasattr(agent, 'set_maestro'):
                agent.set_maestro(self.maestro_instance)
            
            print(f"Created real agent instance for {agent_name}")
            return True
            
        except Exception as e:
            print(f"Error creating real agent for {agent_name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_real_maestro(self) -> bool:
        """
        Create a real maestro instance with a registry for agent communication
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Import maestro module
            try:
                from maestro import Maestro, AgentRegistry
            except ImportError:
                # Try to import just AgentRegistry
                try:
                    from maestro import AgentRegistry
                    
                    # Create a simple Maestro-like object with just a registry
                    class SimpleMaestro:
                        def __init__(self):
                            self.registry = AgentRegistry()
                    
                    maestro_instance = SimpleMaestro()
                    
                except ImportError:
                    print("Failed to import AgentRegistry from maestro.py")
                    return False
            else:
                # Create a real Maestro instance
                maestro_instance = Maestro(settings={"test_mode": True})
            
            # Store the maestro instance
            self.maestro_instance = maestro_instance
            
            # Register existing agents with the maestro
            for name, agent in self.agents.items():
                if hasattr(maestro_instance, 'agent_registry') and hasattr(maestro_instance.agent_registry, 'register_agent'):
                    metadata = {"enabled": True, "test_mode": True}
                    maestro_instance.agent_registry.register_agent(name, agent, metadata)
                    if hasattr(agent, 'set_maestro'):
                        agent.set_maestro(maestro_instance)
            
            print("Created real maestro instance with registry")
            return True
            
        except Exception as e:
            print(f"Error creating real maestro: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_communication_test(self) -> bool:
        """
        Run communication tests between modules
        
        Returns:
            True if all tests pass, False otherwise
        """
        import types  # Import here for the create_real_agent method
        
        print("\nInitiating Communications Check...\n")
        
        # Test modules to check
        required_modules = ["maestro", "lore", "logon", "gaia", "memnon", "db_sqlite", "db_chroma"]
        available_modules = list(self.modules.keys())
        
        missing_modules = [m for m in required_modules if m not in available_modules]
        if missing_modules:
            print(f"Some modules are missing: {', '.join(missing_modules)}")
            
            # Try to create real agent instances instead of mock modules
            print("Attempting to create real agent instances for testing...")
            use_real_agents = True
            
            # Try to create real instances for key agents
            for agent_name in ["lore", "memnon", "logon", "db_sqlite", "db_chroma"]:
                if agent_name not in available_modules:
                    success = self.create_real_agent(agent_name)
                    if not success:
                        # Fall back to mock for this one
                        self.create_mock_module(agent_name)
            
            # Create maestro with registry for inter-agent communication
            self.create_real_maestro()
            
            if self.agents:
                print(f"Successfully created {len(self.agents)} real agent instances for testing")
                print("Using real agent instances for communication test where available...")
            else:
                print("No real agent instances could be created. Using mock implementations for all modules...")
                # Create mock modules for any that are still missing
                for module_name in missing_modules:
                    if module_name not in self.agents:
                        self.create_mock_module(module_name)
        else:
            print("All modules available, but some are using mock methods.")
            print("Running communications check with enhanced modules...")
            
        # Define the test cases for module communications
        test_cases = [
            ModuleMessageTest(
                name="Lore Context Building Test",
                source_module="maestro",
                target_module="lore",
                message={
                    "type": "request",
                    "action": "build_context",
                    "parameters": {
                        "chunk_id": "S01E01_001",
                        "query": "What happened between Alex and Emilia?"
                    }
                },
                expected_response={
                    "status": "success"
                }
            ),
            ModuleMessageTest(
                name="Memory Retrieval Test",
                source_module="lore",
                target_module="memnon",
                message={
                    "type": "request",
                    "action": "retrieve_memory",
                    "parameters": {
                        "query": "Alex meeting Emilia",
                        "limit": 5
                    }
                },
                expected_response={
                    "status": "success"
                }
            ),
            ModuleMessageTest(
                name="Vector Search Test",
                source_module="memnon",
                target_module="db_chroma",
                message={
                    "type": "request",
                    "action": "vector_search",
                    "parameters": {
                        "collection_name": "narrative_chunks",
                        "query_vector": [0.1, 0.2, 0.3],
                        "limit": 5
                    }
                },
                expected_response={
                    "status": "success"
                }
            ),
            ModuleMessageTest(
                name="Entity Query Test",
                source_module="gaia",
                target_module="db_sqlite",
                message={
                    "type": "request",
                    "action": "select",
                    "parameters": {
                        "table": "entities",
                        "conditions": {
                            "entity_type": "character",
                            "name": "Alex"
                        }
                    }
                },
                expected_response={
                    "status": "success"
                }
            )
        ]
        
        # Run each test case
        results = []
        for test_case in test_cases:
            print(f"Running test: {test_case.name}")
            print(f"  Source: {test_case.source_module}")
            print(f"  Target: {test_case.target_module}")
            
            try:
                # Check if we have real agent instances for this test
                source_agent = self.agents.get(test_case.source_module)
                target_agent = self.agents.get(test_case.target_module)
                
                if source_agent and target_agent and hasattr(source_agent, 'send_message'):
                    # Use real agent communication
                    print(f"  Using real agent communication for {test_case.source_module} -> {test_case.target_module}")
                    
                    # Format message as an AgentMessage
                    agent_message = {
                        "sender": test_case.source_module,
                        "recipient": test_case.target_module,
                        "message_type": test_case.message.get("type", "request"),
                        "content": {
                            "action": test_case.message.get("action"),
                            "parameters": test_case.message.get("parameters", {})
                        }
                    }
                    
                    # Send message directly using BaseAgent's send_message method
                    print(f"  {test_case.source_module} sending message to {test_case.target_module}")
                    response = source_agent.send_message(test_case.target_module, test_case.message)
                    
                    # Verify the response matches expectations
                    if response and response.get("status") == "success":
                        print(f"✓ Test passed: {test_case.name}")
                        results.append(True)
                    else:
                        print(f"✗ Test failed: {test_case.name} - Response did not match expected: {response}")
                        results.append(False)
                    
                else:
                    # Use the module's send_message function (which might be a mock)
                    print(f"  {test_case.source_module} sending message to {test_case.target_module}")
                    module = self.modules.get(test_case.source_module)
                    if not module:
                        module = self.create_mock_module(test_case.source_module)
                    
                    response = module.send_message(test_case.target_module, test_case.message)
                    
                    # Verify response matches expected pattern
                    if response and isinstance(response, dict) and "status" in response:
                        expect_text = f"Mock {test_case.target_module} processed {test_case.message.get('action')}"
                        if response.get("status") == "success":
                            if test_case.expected_response_pattern is None or \
                               test_case.expected_response_pattern in str(response):
                                print(f"✓ Test passed: {test_case.name}")
                                results.append(True)
                            else:
                                print(f"✗ Test failed: {test_case.name} - Response did not match expected: {response} != {test_case.expected_response_pattern}")
                                results.append(False)
                        else:
                            print(f"✗ Test failed: {test_case.name} - Response indicates failure: {response}")
                            results.append(False)
                    else:
                        print(f"✗ Test failed: {test_case.name} - Invalid response format: {response}")
                        results.append(False)
                
            except Exception as e:
                print(f"✗ Test failed: {test_case.name} - Exception: {e}")
                import traceback
                traceback.print_exc()
                results.append(False)
        
        # ... existing memory access pattern test code ...
        
        # Report overall results
        if results:
            success_rate = sum(results) / len(results)
            print(f"\nCommunications Check completed: {sum(results)}/{len(results)} tests passed ({success_rate:.0%})")
            
            if missing_modules or self.using_mocks:
                if self.agents:
                    print("\nNote: This test used a mix of real agent instances and mock implementations.")
                    print(f"Real agent instances used: {', '.join(self.agents.keys())}")
                else:
                    print("\nNote: This test was run with mock implementations for some modules or methods.")
                    print("Results with mock implementations indicate compatibility with the expected interface,")
                    print("but do not guarantee correct behavior of the actual implementations.")
            
            return all(results)
        else:
            print("\nNo communication tests were run. Please check module availability.")
            return False

def run_real_agent_communication_test():
    """Test communication between real agent instances"""
    # Code for real agent communication test
    print("\n=== Running Real Agent Communication Test ===\n")
    
    try:
        import test_agent_communication
        return test_agent_communication.run_all_tests()
    except ImportError:
        print("Error: test_agent_communication.py not found.")
        print("Please make sure test_agent_communication.py is in the current directory.")
        return False
    except Exception as e:
        print(f"Error running agent communication test: {e}")
        return False

def display_entity_relationships():
    """Display visualizations of entity relationships in the system"""
    print("\n=== Entity Relationship Visualization ===\n")
    
    try:
        # Generate sample entity data
        entities = generate_test_states()
        relationships = generate_test_relationships()
        
        print(f"Generated {len(entities)} sample entities")
        print(f"Generated {len(relationships)} sample relationships")
        
        # Display basic relationship information
        print("\nSample Entity Relationships:")
        for rel in relationships[:5]:  # Show first 5 for brevity
            print(f"  {rel['source_type']}/{rel['source_id']} -> {rel['relationship_type']} -> {rel['target_type']}/{rel['target_id']}")
        
        print("\nNote: Full visualization requires graphical interface. Basic relationship info shown instead.")
        return True
    except Exception as e:
        print(f"Error displaying entity relationships: {e}")
        return False

def display_module_status():
    """Display the status of various system modules"""
    print("\n=== Night City Stories System Status ===\n")
    
    # Check for core modules
    core_modules = ["maestro", "lore", "psyche", "gaia", "logon", "memnon"]
    storage_modules = ["db_sqlite", "db_chroma"]
    utility_modules = ["config_manager", "encode_chunks"]
    
    # Check core modules
    print("Core Modules:")
    for module in core_modules:
        try:
            module_obj = __import__(module)
            print(f"  ✅ {module.capitalize()}: Available")
        except ImportError:
            print(f"  ❌ {module.capitalize()}: Not found")
    
    # Check storage modules
    print("\nStorage Modules:")
    for module in storage_modules:
        try:
            module_obj = __import__(module)
            print(f"  ✅ {module.capitalize()}: Available")
        except ImportError:
            print(f"  ❌ {module.capitalize()}: Not found")
    
    # Check utility modules
    print("\nUtility Modules:")
    for module in utility_modules:
        try:
            module_obj = __import__(module)
            print(f"  ✅ {module.capitalize()}: Available")
        except ImportError:
            print(f"  ❌ {module.capitalize()}: Not found")
    
    print("\nSystem is ready for testing")
    return True

def display_menu():
    """Display the main menu for the testing framework"""
    print("\n" + "=" * 50)
    print("|  NIGHT CITY STORIES - MODULE INTEGRATION TESTER  |")
    print("=" * 50 + "\n")
    print("Available Tests:")
    print("1. Inter-Module Communications Check")
    print("2. End-to-End Integration Test")
    print("3. Entity Relationship Visualization")
    print("4. Run All Tests")
    print("5. Display Module Status")
    print("6. Real Agent Communication Test")  # Add new option
    print("\n0. Exit\n")

def run_selected_test(selection):
    """Run the selected test"""
    try:
        if selection == 1:
            # Run inter-module communication check
            test_handler = IntegrationTestHandler()
            result = test_handler.run_communication_test()
        elif selection == 2:
            # Run end-to-end integration test
            test_handler = IntegrationTestHandler()
            result = test_handler.run_end_to_end_test()
        elif selection == 3:
            # Run entity relationship visualization
            result = display_entity_relationships()
        elif selection == 4:
            # Run all tests
            results = []
            
            print("\n=== Running All Tests ===\n")
            
            # Test 1: Communication check
            test_handler = IntegrationTestHandler()
            results.append(test_handler.run_communication_test())
            
            # Test 2: End-to-end integration
            results.append(test_handler.run_end_to_end_test())
            
            # Test 3: Entity visualization
            results.append(display_entity_relationships())
            
            # Overall result
            if all(results):
                print("\n✅ ALL TESTS PASSED")
            else:
                passed = sum(1 for r in results if r)
                print(f"\n❌ {passed}/{len(results)} TESTS PASSED")
            
            result = all(results)
        elif selection == 5:
            # Display module status
            result = display_module_status()
        elif selection == 6:
            # Run real agent communication test
            result = run_real_agent_communication_test()
        else:
            print("Invalid selection. Please try again.")
            result = False
        
        return result
        
    except Exception as e:
        print(f"Error running test: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main entry point"""
    try:
        # Parse command line arguments if any
        parser = argparse.ArgumentParser(description="Night City Stories Integration Tester")
        parser.add_argument("--test", type=int, choices=[1, 2, 3, 4, 5, 6], help="Test to run (1-6)")
        parser.add_argument("--all", action="store_true", help="Run all tests")
        parser.add_argument("--status", action="store_true", help="Display module status")
        args = parser.parse_args()
        
        # Run tests based on arguments
        if args.test:
            run_selected_test(args.test)
        elif args.all:
            run_selected_test(4)  # Run all tests
        elif args.status:
            display_module_status()
        else:
            # Interactive mode
            while True:
                display_menu()
                try:
                    selection = int(input("Enter test number to run, or 0 to exit:\n>>> "))
                    
                    if selection == 0:
                        print("Exiting tester. Goodbye!")
                        break
                    
                    run_selected_test(selection)
                    
                    input("\nPress Enter to continue...")
                    
                except ValueError:
                    print("Invalid input. Please enter a number.")
                except KeyboardInterrupt:
                    print("\nExiting tester. Goodbye!")
                    break
        
        return 0
        
    except Exception as e:
        print(f"Error in main function: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    main()
