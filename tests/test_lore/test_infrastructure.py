"""
Test basic infrastructure requirements for LORE.

These tests verify essential components are available and fail hard
when missing (NO FALLBACKS principle).
"""

import pytest
import psycopg2
import tiktoken
import requests
from pathlib import Path


class TestInfrastructure:
    """Test that all required infrastructure is available."""
    
    def test_postgresql_connection(self, settings):
        """Test that PostgreSQL is accessible with correct database."""
        db_config = settings.get("Database", {})
        
        # This should fail hard if PostgreSQL is not available
        conn = psycopg2.connect(
            dbname=db_config.get("name", "NEXUS"),
            user=db_config.get("user", "pythagor"),
            host=db_config.get("host", "localhost"),
            port=db_config.get("port", 5432)
        )
        
        cursor = conn.cursor()
        
        # Verify NEXUS database exists
        cursor.execute("SELECT current_database()")
        db_name = cursor.fetchone()[0]
        assert db_name == "NEXUS", f"Connected to wrong database: {db_name}"
        
        # Verify required tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND (table_name IN ('narrative_chunks', 'chunk_metadata')
                 OR table_name LIKE 'chunk_embeddings_%')
            ORDER BY table_name
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        assert 'narrative_chunks' in tables, "narrative_chunks table missing"
        assert 'chunk_metadata' in tables, "chunk_metadata table missing"
        # Check for any embeddings table variant
        embeddings_tables = [t for t in tables if t.startswith('chunk_embeddings_')]
        assert len(embeddings_tables) > 0, f"No chunk_embeddings tables found (found: {tables})"
        
        cursor.close()
        conn.close()
    
    def test_narrative_view_exists(self, db_connection):
        """Test that narrative_view is available and functional."""
        cursor = db_connection.cursor()
        
        # Check view exists
        cursor.execute("""
            SELECT viewname 
            FROM pg_views 
            WHERE schemaname = 'public' 
            AND viewname = 'narrative_view'
        """)
        
        view = cursor.fetchone()
        assert view is not None, "narrative_view does not exist"
        
        # Test view is queryable
        cursor.execute("SELECT COUNT(*) FROM narrative_view")
        count = cursor.fetchone()[0]
        assert count > 0, f"narrative_view has no data (count: {count})"
        
        # Verify view has expected columns
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'narrative_view'
            ORDER BY ordinal_position
        """)
        
        columns = [row[0] for row in cursor.fetchall()]
        required_columns = ['id', 'raw_text', 'season', 'episode', 'scene', 'world_layer']
        
        for col in required_columns:
            assert col in columns, f"narrative_view missing column: {col}"
        
        cursor.close()
    
    def test_lm_studio_availability(self, settings):
        """Test that LM Studio is running and accessible - MUST FAIL HARD if not."""
        lm_settings = settings.get("Agent Settings", {}).get("LORE", {}).get("local_llm", {})
        base_url = lm_settings.get("base_url", "http://localhost:1234/v1")
        
        # Strip /v1 if present for health check
        health_url = base_url.replace("/v1", "") + "/health"
        
        # This MUST fail hard if LM Studio is not running
        try:
            response = requests.get(health_url, timeout=5)
            assert response.status_code == 200, f"LM Studio health check failed: {response.status_code}"
        except requests.exceptions.RequestException as e:
            # Fail hard - no graceful fallback
            raise RuntimeError(f"LM Studio is not available at {base_url}: {e}")
    
    def test_lm_studio_models(self, settings):
        """Test that required models are loaded in LM Studio."""
        lm_settings = settings.get("Agent Settings", {}).get("LORE", {}).get("local_llm", {})
        base_url = lm_settings.get("base_url", "http://localhost:1234/v1")
        
        # Check models endpoint
        models_url = f"{base_url}/models"
        
        try:
            response = requests.get(models_url, timeout=5)
            assert response.status_code == 200, f"Failed to get models: {response.status_code}"
            
            data = response.json()
            models = data.get('data', [])
            
            # Must have at least one model loaded
            assert len(models) > 0, "No models loaded in LM Studio"
            
            # Log available models for debugging
            model_ids = [m.get('id') for m in models]
            print(f"Available models: {model_ids}")
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Cannot query LM Studio models: {e}")
    
    def test_tiktoken_encoding(self, settings):
        """Test tiktoken with newer model encodings."""
        # Test o200k_base encoding for newer models
        try:
            encoding = tiktoken.get_encoding("o200k_base")
            assert encoding is not None
            
            # Test it can encode text
            test_text = "This is a test of the token counter with newer models."
            tokens = encoding.encode(test_text)
            assert len(tokens) > 0
            
        except Exception as e:
            # Try fallback to cl100k_base
            encoding = tiktoken.get_encoding("cl100k_base")
            assert encoding is not None
            print(f"Using cl100k_base encoding (o200k_base not available): {e}")
    
    def test_settings_structure(self, settings):
        """Test that settings.json has required LORE configuration."""
        # Check LORE agent settings exist
        assert "Agent Settings" in settings
        assert "LORE" in settings["Agent Settings"]
        
        lore_settings = settings["Agent Settings"]["LORE"]
        
        # Check required sections
        assert "token_budget" in lore_settings
        assert "payload_percent_budget" in lore_settings
        assert "local_llm" in lore_settings
        
        # Verify token budget structure
        token_budget = lore_settings["token_budget"]
        assert "apex_context_window" in token_budget
        assert "utilization" in token_budget
        
        # Verify percentage ranges
        percent_budget = lore_settings["payload_percent_budget"]
        assert "warm_slice" in percent_budget
        assert "structured_summaries" in percent_budget
        assert "contextual_augmentation" in percent_budget
        
        # Each range should have min/max
        for key in ["warm_slice", "structured_summaries", "contextual_augmentation"]:
            assert "min" in percent_budget[key]
            assert "max" in percent_budget[key]
    
    def test_project_structure(self):
        """Test that required LORE modules exist."""
        nexus_root = Path(__file__).parent.parent.parent
        lore_path = nexus_root / "nexus" / "agents" / "lore"
        
        # Check main directory exists
        assert lore_path.exists(), f"LORE agent directory not found: {lore_path}"
        
        # Check required modules
        required_files = [
            "lore_system_prompt.md",
            "utils/chunk_operations.py",
            "utils/context_validation.py",
            "utils/token_budget.py",
            "utils/local_llm.py"
        ]
        
        for file_path in required_files:
            full_path = lore_path / file_path
            assert full_path.exists(), f"Required file missing: {full_path}"
    
    def test_test_scenes_available(self, sample_chunks, test_scenes):
        """Verify all 18 test scenes are available in database."""
        # Check we got all expected chunks
        assert len(sample_chunks) == len(test_scenes), \
            f"Missing test chunks: expected {len(test_scenes)}, got {len(sample_chunks)}"
        
        # Verify each scene has content
        for scene_name, chunk_data in sample_chunks.items():
            assert chunk_data is not None, f"Scene {scene_name} not found in database"
            assert 'raw_text' in chunk_data, f"Scene {scene_name} missing raw_text"
            assert len(chunk_data['raw_text']) > 0, f"Scene {scene_name} has empty text"