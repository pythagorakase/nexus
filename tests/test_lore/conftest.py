"""
pytest configuration and fixtures for LORE tests.
"""

import pytest
import logging
import json
import psycopg2
from pathlib import Path
from typing import Dict, Any, Generator
from unittest.mock import Mock, MagicMock
import sys

# Configure logging for tests
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add nexus module to path
nexus_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(nexus_root))


@pytest.fixture(scope="session")
def settings() -> Dict[str, Any]:
    """Load test settings for LORE testing."""
    # Use test-specific settings file
    test_settings_path = Path(__file__).parent / "lore_test_settings.json"
    with open(test_settings_path, 'r') as f:
        return json.load(f)


@pytest.fixture(scope="session")
def test_scenes() -> Dict[str, int]:
    """Map test scene IDs from lore_test_scenes.md."""
    return {
        # Dialogue-Heavy Scenes
        "dialogue_offer": 2,           # S01E01_002 - Interrogation/Offer
        "dialogue_world": 17,          # S01E01_017 - Clarification/World-building
        "dialogue_revelation": 41,     # S01E02_009 - Revelation/Confrontation
        
        # Action Scenes  
        "action_ambush": 5,            # S01E01_005 - Ambush/Combat
        "action_infiltration": 10,     # S01E01_010 - Infiltration/Hacking
        
        # Investigation
        "investigate_trace": 7,        # S01E01_007 - Digital trace
        "investigate_database": 60,    # S01E03_014 - Database search
        
        # Transitions
        "transition_escape": 16,       # S01E01_016 - Escape/Journey
        "transition_acquire": 25,      # S01E01_025 - Acquisition/Stealth
        "transition_vision": 50,       # S01E03_004 - Introspective/Vision Quest
        
        # Revelations
        "reveal_twist": 35,            # S01E02_003 - Plot Twist
        "reveal_conspiracy": 52,       # S01E03_006 - Conspiracy Deepens
        "reveal_identity": 376,        # S02E04_041 - Identity/Origin
        
        # Emotional
        "emotion_character": 67,       # S01E03_021 - Character Development
        "emotion_relationship": 518,   # S03E01_006 - Relationship Dynamics
        "emotion_morning": 888,        # S04E01_023 - Relationship Development
        "emotion_breakdown": 910,      # S04E02_019 - Breakdown/Vulnerability
        "emotion_intimacy": 537        # S03E03_010 - Vulnerability/Intimacy
    }


@pytest.fixture
def db_connection(settings) -> Generator[psycopg2.extensions.connection, None, None]:
    """Provide database connection for tests."""
    # Get database config from settings
    db_config = settings.get("Database", {})
    
    conn = psycopg2.connect(
        dbname=db_config.get("name", "NEXUS"),
        user=db_config.get("user", "pythagor"),
        host=db_config.get("host", "localhost"),
        port=db_config.get("port", 5432)
    )
    
    try:
        yield conn
    finally:
        conn.rollback()  # Rollback any test changes
        conn.close()


@pytest.fixture
def sample_chunks(db_connection, test_scenes) -> Dict[str, Dict]:
    """Load sample chunks from database for testing."""
    chunks = {}
    cursor = db_connection.cursor()
    
    for scene_name, chunk_id in test_scenes.items():
        cursor.execute("""
            SELECT 
                id,
                raw_text,
                season,
                episode,
                scene,
                world_layer,
                world_time
            FROM narrative_view
            WHERE id = %s
        """, (chunk_id,))
        
        row = cursor.fetchone()
        if row:
            chunks[scene_name] = {
                'id': row[0],
                'raw_text': row[1],
                'season': row[2],
                'episode': row[3],
                'scene': row[4],
                'world_layer': row[5],
                'world_time': row[6]
            }
    
    cursor.close()
    return chunks


@pytest.fixture
def mock_lm_studio() -> Mock:
    """Mock LM Studio client for testing without actual LLM."""
    mock_client = MagicMock()
    
    # Mock completions endpoint
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(text="Mocked LLM response for testing")
    ]
    mock_client.completions.create.return_value = mock_response
    
    return mock_client


@pytest.fixture
def test_token_limit() -> int:
    """Token limit for quick testing iterations."""
    return 20000  # 20k tokens as specified


@pytest.fixture
def mock_turn_context():
    """Create a mock TurnContext for testing."""
    context = MagicMock()
    context.phase_states = {}
    context.token_counts = {}
    context.chunk_ids = []
    context.user_input = ""
    return context


@pytest.fixture
def isolation_db(db_connection):
    """
    Provide isolated database state for destructive tests.
    Creates a savepoint before test and rolls back after.
    """
    cursor = db_connection.cursor()
    cursor.execute("SAVEPOINT test_isolation")
    
    yield db_connection
    
    cursor.execute("ROLLBACK TO SAVEPOINT test_isolation")
    cursor.close()


@pytest.fixture
def clean_logs(tmp_path):
    """Provide clean temporary directory for test logs."""
    log_dir = tmp_path / "test_logs"
    log_dir.mkdir()
    
    # Configure test logger
    test_logger = logging.getLogger("nexus.lore.test")
    handler = logging.FileHandler(log_dir / "test.log")
    handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    test_logger.addHandler(handler)
    
    yield log_dir
    
    # Cleanup
    test_logger.removeHandler(handler)
    handler.close()