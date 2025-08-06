#!/usr/bin/env python3
"""
NEXUS IR Evaluation System - PostgreSQL Version (DEBUG)
Enhanced debug version for troubleshooting A/B testing issues
"""

import os
import sys
import json
import time
import datetime
import logging
import tempfile
import subprocess
import argparse
from typing import Dict, List, Any, Tuple, Optional, Set
from pathlib import Path

# Add parent directory to path
parent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, parent_dir)

# Import IR evaluation modules
from pg_db import IRDatabasePG
from scripts.pg_qrels import PGQRELSManager
from scripts.ir_metrics import calculate_all_metrics, average_metrics_by_category

# Set up enhanced logging
logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(logs_dir, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,  # Use DEBUG level for more verbose output
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(logs_dir, "ir_eval_debug.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.ir_eval_debug")

# Constants
DEFAULT_GOLDEN_QUERIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_queries.json")
DEFAULT_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
CONTROL_CONFIG_NAME = "control"
EXPERIMENT_CONFIG_NAME = "experiment"

# Ensure results directory exists
os.makedirs(RESULTS_DIR, exist_ok=True)

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON data from file."""
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            logger.debug(f"Loaded JSON data from {path}")
            return data
    except Exception as e:
        logger.error(f"Error loading JSON from {path}: {e}")
        return {}

def save_json(data: Dict[str, Any], path: str) -> bool:
    """Save JSON data to file."""
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved data to {path}")
        return True
    except Exception as e:
        logger.error(f"Error saving JSON to {path}: {e}")
        return False

def extract_memnon_settings(settings_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract MEMNON settings from settings.json."""
    memnon_settings = {}
    if "Agent Settings" in settings_data and "MEMNON" in settings_data["Agent Settings"]:
        memnon_settings = settings_data["Agent Settings"]["MEMNON"]
        logger.debug(f"Extracted MEMNON settings, keys: {list(memnon_settings.keys())}")
    else:
        logger.warning("Could not find MEMNON settings in settings data")
    return memnon_settings

def create_temp_settings_file(settings_data: Dict[str, Any], memnon_override: Dict[str, Any]) -> str:
    """
    Create a temporary settings file with modified MEMNON settings.
    
    Args:
        settings_data: The original settings data
        memnon_override: The MEMNON settings to override
    
    Returns:
        Path to the temporary settings file
    """
    # Create a deep copy to avoid modifying the original
    settings_copy = json.loads(json.dumps(settings_data))
    
    # Override MEMNON settings
    if "Agent Settings" in settings_copy and "MEMNON" in settings_copy["Agent Settings"]:
        logger.debug(f"Base settings before override: {json.dumps(settings_copy['Agent Settings']['MEMNON'].get('retrieval', {}).get('hybrid_search', {}), indent=2)}")
        logger.debug(f"Override settings to apply: {json.dumps(memnon_override.get('retrieval', {}).get('hybrid_search', {}), indent=2)}")
        
        # Apply selective overrides
        for key, value in memnon_override.items():
            if key in settings_copy["Agent Settings"]["MEMNON"]:
                if isinstance(value, dict) and isinstance(settings_copy["Agent Settings"]["MEMNON"][key], dict):
                    # Special handling for models to preserve local_path settings
                    if key == "models":
                        for model_name, model_config in value.items():
                            if model_name in settings_copy["Agent Settings"]["MEMNON"]["models"]:
                                # Preserve local_path from original settings
                                local_path = settings_copy["Agent Settings"]["MEMNON"]["models"][model_name].get("local_path")
                                if local_path:
                                    if model_name not in settings_copy["Agent Settings"]["MEMNON"]["models"]:
                                        settings_copy["Agent Settings"]["MEMNON"]["models"][model_name] = {}
                                    settings_copy["Agent Settings"]["MEMNON"]["models"][model_name].update(model_config)
                                    settings_copy["Agent Settings"]["MEMNON"]["models"][model_name]["local_path"] = local_path
                                    logger.debug(f"Preserved local_path for model {model_name}: {local_path}")
                            else:
                                settings_copy["Agent Settings"]["MEMNON"]["models"][model_name] = model_config
                                logger.debug(f"Added new model {model_name}")
                    else:
                        # For non-model dictionaries, regular update
                        pre_update = json.dumps(settings_copy["Agent Settings"]["MEMNON"][key])
                        settings_copy["Agent Settings"]["MEMNON"][key].update(value)
                        post_update = json.dumps(settings_copy["Agent Settings"]["MEMNON"][key])
                        logger.debug(f"Updated {key} settings: {pre_update} -> {post_update}")
                else:
                    # Replace value
                    prev_value = settings_copy["Agent Settings"]["MEMNON"].get(key, "None")
                    settings_copy["Agent Settings"]["MEMNON"][key] = value
                    logger.debug(f"Replaced {key}: {prev_value} -> {value}")
        
        # Debug log the settings for troubleshooting
        logger.debug(f"Final experimental settings with hybrid_search config: " +
                   f"{json.dumps(settings_copy['Agent Settings']['MEMNON'].get('retrieval', {}).get('hybrid_search', {}), indent=2)}")
    
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='nexus_settings_')
    os.close(fd)
    
    # Write settings to temporary file
    with open(temp_path, 'w') as f:
        json.dump(settings_copy, f, indent=2)
    
    logger.info(f"Created temporary settings file at {temp_path}")
    
    # Verify file content
    with open(temp_path, 'r') as f:
        debug_settings = json.load(f)
        hybrid_settings = debug_settings.get("Agent Settings", {}).get("MEMNON", {}).get("retrieval", {}).get("hybrid_search", {})
        logger.debug(f"Temporary settings file hybrid search content: {hybrid_settings}")
    
    return temp_path

def get_query_data_by_category(golden_queries_data: Dict[str, Any]) -> Dict[str, List[Tuple[str, str, Dict[str, Any]]]]:
    """
    Extract queries grouped by category from golden_queries.json.
    
    Returns:
        Dictionary mapping category names to lists of (name, query_text, query_info) tuples
    """
    queries_by_category = {}
    
    for category, queries in golden_queries_data.items():
        if category != "settings" and isinstance(queries, dict):
            if category not in queries_by_category:
                queries_by_category[category] = []
                
            for name, info in queries.items():
                if isinstance(info, dict) and "query" in info:
                    queries_by_category[category].append((name, info["query"], info))
    
    return queries_by_category

def test_run_golden_queries():
    """
    Test function to explicitly run golden queries with both control and experimental settings.
    """
    # Load settings and golden queries
    settings_path = DEFAULT_SETTINGS_PATH
    golden_queries_path = DEFAULT_GOLDEN_QUERIES_PATH
    
    settings_data = load_json(settings_path)
    golden_queries_data = load_json(golden_queries_path)
    
    # Extract experimental settings from golden_queries.json
    experimental_settings = None
    if "settings" in golden_queries_data:
        experimental_settings = {}
        if "retrieval" in golden_queries_data["settings"]:
            experimental_settings["retrieval"] = golden_queries_data["settings"]["retrieval"]
        if "models" in golden_queries_data["settings"]:
            experimental_settings["models"] = golden_queries_data["settings"]["models"]
    
    if not experimental_settings:
        logger.error("No experimental settings found in golden_queries.json")
        return
    
    # Create database connection
    db = IRDatabasePG()
    
    # Run with control settings first
    logger.info("="*80)
    logger.info("RUNNING CONTROL CONFIGURATION")
    logger.info("="*80)
    
    try:
        # Add the local scripts directory to the Python path
        local_scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
        if local_scripts_dir not in sys.path:
            sys.path.insert(0, local_scripts_dir)
        
        # Ensure golden_queries_module is in latest version
        if 'golden_queries_module' in sys.modules:
            import importlib
            importlib.reload(sys.modules['golden_queries_module'])
            logger.info("Reloaded existing golden_queries_module")
        
        # Import the module properly
        logger.info(f"Attempting to import golden_queries_module from: {local_scripts_dir}")
        import golden_queries_module
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        control_run_name = f"Control {timestamp}"
        
        # Run control configuration
        logger.info(f"Running control with settings path: {settings_path}")
        results_data = golden_queries_module.run_queries(
            golden_queries_path=golden_queries_path,
            settings_path=settings_path,
            limit=2,  # Just run a couple queries for testing
            k=5,
            hybrid=None,
            category="event"
        )
        
        # Check settings that were actually used
        if "settings" in results_data:
            hybrid_settings = results_data["settings"].get("hybrid_search", {})
            logger.info(f"Control run used hybrid settings: {hybrid_settings}")
        
        # Save results to database
        control_run_id = db.add_run(
            name=control_run_name, 
            settings=results_data.get("settings", {}), 
            config_type=CONTROL_CONFIG_NAME, 
            description="Control run from debug script"
        )
        
        if control_run_id:
            # Save query results to database
            query_results = results_data.get("query_results", [])
            if not db.save_results(control_run_id, query_results):
                logger.error("Failed to save control results to database")
            else:
                logger.info(f"Saved control run {control_run_id} to database")
        
    except Exception as e:
        logger.error(f"Error running control configuration: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # Now run with experimental settings
    logger.info("\n" + "="*80)
    logger.info("RUNNING EXPERIMENTAL CONFIGURATION")
    logger.info("="*80)
    
    try:
        # Create temporary settings file with experimental settings
        temp_settings_path = create_temp_settings_file(settings_data, experimental_settings)
        
        # Explicitly check the content of the temporary settings file
        with open(temp_settings_path, 'r') as f:
            temp_settings = json.load(f)
            hybrid_settings = temp_settings.get("Agent Settings", {}).get("MEMNON", {}).get("retrieval", {}).get("hybrid_search", {})
            logger.info(f"Temporary settings file hybrid search content: {hybrid_settings}")
        
        # Reload golden_queries_module to ensure clean state
        if 'golden_queries_module' in sys.modules:
            import importlib
            importlib.reload(sys.modules['golden_queries_module'])
            logger.info("Reloaded golden_queries_module for experimental run")
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        exp_run_name = f"Experiment {timestamp}"
        
        # Run experimental configuration
        logger.info(f"Running experiment with settings path: {temp_settings_path}")
        results_data = golden_queries_module.run_queries(
            golden_queries_path=golden_queries_path,
            settings_path=temp_settings_path,
            limit=2,  # Just run a couple queries for testing
            k=5,
            hybrid=None,
            category="event"
        )
        
        # Check settings that were actually used
        if "settings" in results_data:
            hybrid_settings = results_data["settings"].get("hybrid_search", {})
            logger.info(f"Experiment run used hybrid settings: {hybrid_settings}")
        
        # Save results to database
        exp_run_id = db.add_run(
            name=exp_run_name, 
            settings=results_data.get("settings", {}), 
            config_type=EXPERIMENT_CONFIG_NAME, 
            description="Experimental run from debug script"
        )
        
        if exp_run_id:
            # Save query results to database
            query_results = results_data.get("query_results", [])
            if not db.save_results(exp_run_id, query_results):
                logger.error("Failed to save experimental results to database")
            else:
                logger.info(f"Saved experimental run {exp_run_id} to database")
        
        # Clean up temporary file
        if os.path.exists(temp_settings_path):
            os.remove(temp_settings_path)
            logger.info(f"Cleaned up temporary settings file {temp_settings_path}")
    
    except Exception as e:
        logger.error(f"Error running experimental configuration: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    print("Running debug test of IR evaluation system...")
    test_run_golden_queries()
    print("Debug test complete. Check logs for details.")