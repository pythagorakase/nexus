#!/usr/bin/env python3
"""
Utility module for NEXUS IR Evaluation System

This module provides utility functions for common operations such as:
- Loading and saving JSON files
- Creating and formatting queries
- Handling temporary files
- Formatting text

These functions are used across the IR evaluation system modules.
"""

import os
import sys
import json
import tempfile
import logging
from typing import Dict, List, Any, Tuple, Optional, Set

# Make sure we can import from the parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.utils")

def load_json(path: str) -> Dict[str, Any]:
    """
    Load JSON data from file.
    
    Args:
        path: Path to the JSON file
        
    Returns:
        Dictionary containing the loaded data or empty dict on error
    """
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON from {path}: {e}")
        return {}

def save_json(data: Dict[str, Any], path: str) -> bool:
    """
    Save JSON data to file.
    
    Args:
        data: Data to save
        path: Path to save the file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved data to {path}")
        return True
    except Exception as e:
        logger.error(f"Error saving JSON to {path}: {e}")
        return False

def extract_memnon_settings(settings_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract MEMNON settings from settings.json.
    
    Args:
        settings_data: Settings data
        
    Returns:
        Dictionary with MEMNON settings
    """
    if "Agent Settings" in settings_data and "MEMNON" in settings_data["Agent Settings"]:
        return settings_data["Agent Settings"]["MEMNON"]
    return {}

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
        # Apply selective overrides
        for key, value in memnon_override.items():
            if key in settings_copy["Agent Settings"]["MEMNON"]:
                if isinstance(value, dict) and isinstance(settings_copy["Agent Settings"]["MEMNON"][key], dict):
                    # Merge dictionaries
                    settings_copy["Agent Settings"]["MEMNON"][key].update(value)
                else:
                    # Replace value
                    settings_copy["Agent Settings"]["MEMNON"][key] = value
    
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='nexus_settings_')
    os.close(fd)
    
    # Write settings to temporary file
    with open(temp_path, 'w') as f:
        json.dump(settings_copy, f, indent=2)
    
    return temp_path

def get_query_data_by_category(golden_queries_data: Dict[str, Any]) -> Dict[str, List[Tuple[str, str, Dict[str, Any]]]]:
    """
    Extract queries grouped by category from golden_queries.json.
    
    Args:
        golden_queries_data: Golden queries data
        
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

def format_result_text(text: str, truncate: bool = False, max_length: int = 500) -> str:
    """
    Format result text for display, optionally with truncation and newlines.
    
    Args:
        text: The text to format
        truncate: Whether to truncate the text (default: False)
        max_length: Maximum length if truncating (default: 500)
        
    Returns:
        Formatted text
    """
    if not text:
        return ""
    
    # Replace literal newlines with actual newlines
    formatted = text.replace("\\n", "\n")
    
    # Truncate if requested and if too long
    if truncate and len(formatted) > max_length:
        truncated = formatted[:max_length]
        # Try to truncate at a sensible point
        last_period = truncated.rfind(".")
        last_newline = truncated.rfind("\n")
        
        cutoff = max(last_period, last_newline)
        if cutoff > max_length * 0.7:  # Only use cutoff if it's reasonably far along
            truncated = truncated[:cutoff+1]
        
        formatted = truncated + "..."
    
    return formatted

def get_timestamp_string() -> str:
    """
    Get a formatted timestamp string for file names.
    
    Returns:
        Timestamp string in format YYYYmmDD_HHMMSS
    """
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def get_run_name(config_type: str) -> str:
    """
    Generate a run name with timestamp.
    
    Args:
        config_type: Type of configuration (e.g., 'control', 'experiment')
        
    Returns:
        Formatted run name
    """
    return f"{config_type}_{get_timestamp_string()}"

def clean_temp_files(temp_files: List[str]) -> None:
    """
    Clean up temporary files.
    
    Args:
        temp_files: List of file paths to clean up
    """
    for file_path in temp_files:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Removed temporary file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {file_path}: {e}")

if __name__ == "__main__":
    # Test code if run directly
    print("Utils module - Utility functions for NEXUS IR Evaluation System")
    print("This module is intended to be imported, not run directly.")