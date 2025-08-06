#!/usr/bin/env python3
"""
Settings comparison and synchronization module for NEXUS IR Evaluation System

This module provides functions for comparing control and experimental settings
and synchronizing them in either direction.

Main functions:
- compare_settings: Compare control and experimental settings and display differences
- sync_experimental_to_control: Reset experimental settings to match control settings
- sync_control_to_experimental: Update control settings with experimental settings
"""

import os
import sys
import json
import copy
import logging
from typing import Dict, List, Any, Tuple, Optional, Set

# Make sure we can import from the parent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.settings_compare")

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON data from file."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON from {path}: {e}")
        return {}

def compare_settings(settings_path: str, golden_queries_path: str) -> Dict[str, Any]:
    """
    Compare control and experimental settings and return a dictionary of differences.
    
    Args:
        settings_path: Path to settings.json
        golden_queries_path: Path to golden_queries.json
        
    Returns:
        Dictionary with differences
    """
    # Get settings.json
    settings_content = load_json(settings_path)
    golden_queries_content = load_json(golden_queries_path)
    
    # Extract MEMNON settings
    memnon_settings = {}
    if "Agent Settings" in settings_content and "MEMNON" in settings_content["Agent Settings"]:
        memnon_settings = settings_content["Agent Settings"]["MEMNON"]
    
    # Extract experimental settings
    experimental_settings = {}
    if "settings" in golden_queries_content:
        experimental_settings = golden_queries_content["settings"]
    
    # Create a dictionary to hold differences
    differences = {
        "control": memnon_settings,
        "experimental": experimental_settings,
        "diffs": {}
    }
    
    # Compare retrieval settings
    control_retrieval = memnon_settings.get("retrieval", {})
    exp_retrieval = experimental_settings.get("retrieval", {})
    
    # Basic retrieval settings
    retrieval_diffs = {}
    basic_settings = [
        ("structured_data_enabled", "structured_data"),
        ("max_results", "max_results"),
        ("relevance_threshold", "relevance_threshold"),
        ("entity_boost_factor", "entity_boost_factor")
    ]
    
    for control_key, exp_key in basic_settings:
        control_value = control_retrieval.get(control_key, "N/A")
        exp_value = exp_retrieval.get(exp_key, "N/A")
        
        if control_value != exp_value:
            retrieval_diffs[control_key] = {
                "control": control_value,
                "experimental": exp_value
            }
    
    # Hybrid search settings
    control_hybrid = control_retrieval.get("hybrid_search", {})
    exp_hybrid = exp_retrieval.get("hybrid_search", {})
    
    hybrid_diffs = {}
    hybrid_settings = [
        "enabled",
        "vector_weight_default",
        "text_weight_default",
        "target_model",
        "temporal_boost_factor",
        "use_query_type_weights",
        "use_query_type_temporal_factors"
    ]
    
    for key in hybrid_settings:
        control_value = control_hybrid.get(key, "N/A")
        exp_value = exp_hybrid.get(key, "N/A")
        
        if control_value != exp_value:
            hybrid_diffs[key] = {
                "control": control_value,
                "experimental": exp_value
            }
    
    # Per-query type weights
    control_weights_by_query_type = control_hybrid.get("weights_by_query_type", {})
    exp_weights_by_query_type = exp_hybrid.get("weights_by_query_type", {})
    
    weights_by_query_type_diffs = {}
    query_types = set(list(control_weights_by_query_type.keys()) + list(exp_weights_by_query_type.keys()))
    
    for query_type in query_types:
        control_type_config = control_weights_by_query_type.get(query_type, {})
        exp_type_config = exp_weights_by_query_type.get(query_type, {})
        
        control_vector = control_type_config.get("vector", "N/A")
        control_text = control_type_config.get("text", "N/A")
        
        exp_vector = exp_type_config.get("vector", "N/A")
        exp_text = exp_type_config.get("text", "N/A")
        
        if control_vector != exp_vector or control_text != exp_text:
            weights_by_query_type_diffs[query_type] = {
                "control": {
                    "vector": control_vector,
                    "text": control_text
                },
                "experimental": {
                    "vector": exp_vector,
                    "text": exp_text
                }
            }
    
    # Per-query temporal boost factors
    control_temporal_factors = control_hybrid.get("temporal_boost_factors", {})
    exp_temporal_factors = exp_hybrid.get("temporal_boost_factors", {})
    
    temporal_factors_diffs = {}
    query_types_temporal = set(list(control_temporal_factors.keys()) + list(exp_temporal_factors.keys()))
    
    for query_type in query_types_temporal:
        control_factor = control_temporal_factors.get(query_type, "N/A")
        exp_factor = exp_temporal_factors.get(query_type, "N/A")
        
        if control_factor != exp_factor:
            temporal_factors_diffs[query_type] = {
                "control": control_factor,
                "experimental": exp_factor
            }
    
    # Model settings
    control_models = memnon_settings.get("models", {})
    exp_models = experimental_settings.get("models", {})
    
    model_diffs = {}
    all_models = set(list(control_models.keys()) + list(exp_models.keys()))
    
    for model in all_models:
        control_model_config = control_models.get(model, {})
        exp_model_config = exp_models.get(model, {})
        
        control_active = control_model_config.get("is_active", False)
        control_weight = control_model_config.get("weight", 0.0)
        
        exp_active = exp_model_config.get("is_active", False)
        exp_weight = exp_model_config.get("weight", 0.0)
        
        if control_active != exp_active or control_weight != exp_weight:
            model_diffs[model] = {
                "control": {
                    "is_active": control_active,
                    "weight": control_weight
                },
                "experimental": {
                    "is_active": exp_active,
                    "weight": exp_weight
                }
            }
    
    # Add differences to the result dictionary
    if retrieval_diffs:
        differences["diffs"]["retrieval"] = retrieval_diffs
    
    if hybrid_diffs:
        if "retrieval" not in differences["diffs"]:
            differences["diffs"]["retrieval"] = {}
        differences["diffs"]["retrieval"]["hybrid_search"] = hybrid_diffs
    
    if weights_by_query_type_diffs:
        if "retrieval" not in differences["diffs"]:
            differences["diffs"]["retrieval"] = {}
        if "hybrid_search" not in differences["diffs"]["retrieval"]:
            differences["diffs"]["retrieval"]["hybrid_search"] = {}
        differences["diffs"]["retrieval"]["hybrid_search"]["weights_by_query_type"] = weights_by_query_type_diffs
    
    if temporal_factors_diffs:
        if "retrieval" not in differences["diffs"]:
            differences["diffs"]["retrieval"] = {}
        if "hybrid_search" not in differences["diffs"]["retrieval"]:
            differences["diffs"]["retrieval"]["hybrid_search"] = {}
        differences["diffs"]["retrieval"]["hybrid_search"]["temporal_boost_factors"] = temporal_factors_diffs
    
    if model_diffs:
        differences["diffs"]["models"] = model_diffs
    
    return differences

def display_settings_comparison(settings_path: str, golden_queries_path: str) -> None:
    """
    Display a comparison of control and experimental settings in a table format.
    
    Args:
        settings_path: Path to settings.json
        golden_queries_path: Path to golden_queries.json
    """
    # Get settings.json
    settings_content = load_json(settings_path)
    golden_queries_content = load_json(golden_queries_path)
    
    # Extract MEMNON settings
    memnon_settings = {}
    if "Agent Settings" in settings_content and "MEMNON" in settings_content["Agent Settings"]:
        memnon_settings = settings_content["Agent Settings"]["MEMNON"]
    
    # Extract experimental settings
    experimental_settings = {}
    if "settings" in golden_queries_content:
        experimental_settings = golden_queries_content["settings"]
    
    # Print the header
    print("\n" + "="*80)
    print("Settings Comparison: Control vs. Experimental")
    print("="*80)
    
    # Print basic retrieval settings
    print("\nGeneral Settings")
    print("-" * 80)
    print(f"{'Parameter':<30}|{'Control':<25}|{'Experimental':<25}")
    print("-" * 80)
    
    # Get retrieval settings
    control_retrieval = memnon_settings.get("retrieval", {})
    exp_retrieval = experimental_settings.get("retrieval", {})
    
    # Print basic retrieval settings
    basic_settings = [
        ("structured_data_enabled", "structured_data"),
        ("max_results", "max_results"),
        ("relevance_threshold", "relevance_threshold"),
        ("entity_boost_factor", "entity_boost_factor")
    ]
    
    for control_key, exp_key in basic_settings:
        control_value = control_retrieval.get(control_key, "N/A")
        exp_value = exp_retrieval.get(exp_key, "N/A")
        
        # Highlight differences with an asterisk
        highlight = " *" if control_value != exp_value else ""
        print(f"{control_key:<30}|{str(control_value):<25}|{str(exp_value):<25}{highlight}")
    
    # Print hybrid search settings
    print("\nHybrid Search Settings")
    print("-" * 80)
    print(f"{'Parameter':<30}|{'Control':<25}|{'Experimental':<25}")
    print("-" * 80)
    
    control_hybrid = control_retrieval.get("hybrid_search", {})
    exp_hybrid = exp_retrieval.get("hybrid_search", {})
    
    hybrid_settings = [
        "enabled",
        "vector_weight_default",
        "text_weight_default",
        "target_model",
        "temporal_boost_factor",
        "use_query_type_weights",
        "use_query_type_temporal_factors"
    ]
    
    for key in hybrid_settings:
        control_value = control_hybrid.get(key, "N/A")
        exp_value = exp_hybrid.get(key, "N/A")
        
        # Highlight differences with an asterisk
        highlight = " *" if control_value != exp_value else ""
        print(f"{key:<30}|{str(control_value):<25}|{str(exp_value):<25}{highlight}")
    
    # Print per-query type weights table
    print("\nPer-Query Type Weights")
    print("-" * 80)
    print(f"{'Query Type':<15}|{'Vector (Control)':<18}|{'Text (Control)':<18}|{'Vector (Exp)':<18}|{'Text (Exp)':<18}")
    print("-" * 80)
    
    control_weights_by_query_type = control_hybrid.get("weights_by_query_type", {})
    exp_weights_by_query_type = exp_hybrid.get("weights_by_query_type", {})
    
    # Combine query types from both configurations
    query_types = set(list(control_weights_by_query_type.keys()) + list(exp_weights_by_query_type.keys()))
    
    for query_type in sorted(query_types):
        control_type_config = control_weights_by_query_type.get(query_type, {})
        exp_type_config = exp_weights_by_query_type.get(query_type, {})
        
        control_vector = control_type_config.get("vector", "N/A")
        control_text = control_type_config.get("text", "N/A")
        
        exp_vector = exp_type_config.get("vector", "N/A")
        exp_text = exp_type_config.get("text", "N/A")
        
        # Highlight differences
        highlight = " *" if control_vector != exp_vector or control_text != exp_text else ""
        print(f"{query_type:<15}|{str(control_vector):<18}|{str(control_text):<18}|{str(exp_vector):<18}|{str(exp_text):<18}{highlight}")
    
    # Print per-query temporal boost factors table
    print("\nPer-Query Temporal Boost Factors")
    print("-" * 80)
    print(f"{'Query Type':<15}|{'Boost Factor (Control)':<25}|{'Boost Factor (Exp)':<25}")
    print("-" * 80)
    
    control_temporal_factors = control_hybrid.get("temporal_boost_factors", {})
    exp_temporal_factors = exp_hybrid.get("temporal_boost_factors", {})
    
    # Combine query types from both configurations
    query_types_temporal = set(list(control_temporal_factors.keys()) + list(exp_temporal_factors.keys()))
    
    for query_type in sorted(query_types_temporal):
        control_factor = control_temporal_factors.get(query_type, "N/A")
        exp_factor = exp_temporal_factors.get(query_type, "N/A")
        
        # Highlight differences
        highlight = " *" if control_factor != exp_factor else ""
        print(f"{query_type:<15}|{str(control_factor):<25}|{str(exp_factor):<25}{highlight}")
    
    # Print model settings
    print("\nEmbedding Models")
    print("-" * 80)
    print(f"{'Model':<20}|{'Status (Control)':<15}|{'Weight (Control)':<15}|{'Status (Exp)':<15}|{'Weight (Exp)':<15}")
    print("-" * 80)
    
    control_models = memnon_settings.get("models", {})
    exp_models = experimental_settings.get("models", {})
    
    # Combine models from both configurations
    all_models = set(list(control_models.keys()) + list(exp_models.keys()))
    
    for model in sorted(all_models):
        control_model_config = control_models.get(model, {})
        exp_model_config = exp_models.get(model, {})
        
        control_active = control_model_config.get("is_active", False)
        control_weight = control_model_config.get("weight", 0.0)
        
        exp_active = exp_model_config.get("is_active", False)
        exp_weight = exp_model_config.get("weight", 0.0)
        
        # Highlight differences
        highlight = " *" if control_active != exp_active or control_weight != exp_weight else ""
        print(f"{model:<20}|{str(control_active):<15}|{str(control_weight):<15}|{str(exp_active):<15}|{str(exp_weight):<15}{highlight}")
    
    # Explain the asterisks
    print("\nNote: Entries marked with * indicate differences between control and experimental settings.\n")

def create_backup(file_path: str) -> bool:
    """
    Create a backup of the specified file with .bak extension.
    If a backup already exists, overwrite it.
    
    Args:
        file_path: Path to the file to back up
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import shutil
        backup_path = f"{file_path}.bak"
        
        # Create backup
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup of {file_path} at {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Error creating backup of {file_path}: {e}")
        return False

def sync_experimental_to_control(settings_path: str, golden_queries_path: str) -> bool:
    """
    Reset experimental settings in golden_queries.json to match control settings in settings.json.
    
    Args:
        settings_path: Path to settings.json
        golden_queries_path: Path to golden_queries.json
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Load settings.json and golden_queries.json
        settings_content = load_json(settings_path)
        golden_queries_content = load_json(golden_queries_path)
        
        # Create backup before making changes
        if not create_backup(golden_queries_path):
            logger.warning(f"Failed to create backup of {golden_queries_path}, proceeding with caution")
        
        # Extract MEMNON settings
        memnon_settings = {}
        if "Agent Settings" in settings_content and "MEMNON" in settings_content["Agent Settings"]:
            memnon_settings = settings_content["Agent Settings"]["MEMNON"]
        
        # Update experimental settings with control settings
        if "settings" not in golden_queries_content:
            golden_queries_content["settings"] = {}
        
        # Handle retrieval settings specifically
        if "retrieval" in memnon_settings:
            golden_queries_content["settings"]["retrieval"] = copy.deepcopy(memnon_settings["retrieval"])
            
            # Adjust name difference between structured_data_enabled and structured_data
            if "structured_data_enabled" in golden_queries_content["settings"]["retrieval"]:
                golden_queries_content["settings"]["structured_data"] = golden_queries_content["settings"]["retrieval"]["structured_data_enabled"]
                
            # Ensure weights_by_query_type and temporal_boost_factors transfer correctly
            if "hybrid_search" in memnon_settings["retrieval"]:
                if "weights_by_query_type" in memnon_settings["retrieval"]["hybrid_search"]:
                    golden_queries_content["settings"]["retrieval"]["hybrid_search"]["weights_by_query_type"] = \
                        copy.deepcopy(memnon_settings["retrieval"]["hybrid_search"]["weights_by_query_type"])
                
                if "temporal_boost_factors" in memnon_settings["retrieval"]["hybrid_search"]:
                    golden_queries_content["settings"]["retrieval"]["hybrid_search"]["temporal_boost_factors"] = \
                        copy.deepcopy(memnon_settings["retrieval"]["hybrid_search"]["temporal_boost_factors"])
        
        # Copy models
        if "models" in memnon_settings:
            golden_queries_content["settings"]["models"] = copy.deepcopy(memnon_settings["models"])
        
        # Save updated golden_queries.json
        with open(golden_queries_path, 'w') as f:
            json.dump(golden_queries_content, f, indent=4)
        
        logger.info("Experimental settings have been reset to match control settings")
        return True
        
    except Exception as e:
        logger.error(f"Error syncing experimental settings to control: {e}")
        return False

def sync_control_to_experimental(settings_path: str, golden_queries_path: str) -> bool:
    """
    Update control settings in settings.json with experimental settings from golden_queries.json.
    
    Args:
        settings_path: Path to settings.json
        golden_queries_path: Path to golden_queries.json
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Load settings.json and golden_queries.json
        settings_content = load_json(settings_path)
        golden_queries_content = load_json(golden_queries_path)
        
        # Create backup before making changes
        if not create_backup(settings_path):
            logger.warning(f"Failed to create backup of {settings_path}, proceeding with caution")
        
        # Check if MEMNON settings exist
        if "Agent Settings" not in settings_content:
            settings_content["Agent Settings"] = {}
        if "MEMNON" not in settings_content["Agent Settings"]:
            settings_content["Agent Settings"]["MEMNON"] = {}
        
        # Extract experimental settings
        experimental_settings = {}
        if "settings" in golden_queries_content:
            experimental_settings = golden_queries_content["settings"]
        
        # Copy retrieval settings
        if "retrieval" in experimental_settings:
            exp_retrieval = copy.deepcopy(experimental_settings["retrieval"])
            
            # Handle structured_data vs structured_data_enabled name difference
            if "structured_data" in experimental_settings:
                exp_retrieval["structured_data_enabled"] = experimental_settings["structured_data"]
            
            # Ensure weights_by_query_type and temporal_boost_factors transfer correctly
            if "hybrid_search" in experimental_settings["retrieval"]:
                if "weights_by_query_type" in experimental_settings["retrieval"]["hybrid_search"]:
                    exp_retrieval["hybrid_search"]["weights_by_query_type"] = \
                        copy.deepcopy(experimental_settings["retrieval"]["hybrid_search"]["weights_by_query_type"])
                
                if "temporal_boost_factors" in experimental_settings["retrieval"]["hybrid_search"]:
                    exp_retrieval["hybrid_search"]["temporal_boost_factors"] = \
                        copy.deepcopy(experimental_settings["retrieval"]["hybrid_search"]["temporal_boost_factors"])
            
            settings_content["Agent Settings"]["MEMNON"]["retrieval"] = exp_retrieval
        
        # Copy models
        if "models" in experimental_settings:
            settings_content["Agent Settings"]["MEMNON"]["models"] = copy.deepcopy(experimental_settings["models"])
        
        # Save updated settings.json
        with open(settings_path, 'w') as f:
            json.dump(settings_content, f, indent=4)
        
        logger.info("Control settings have been updated with experimental settings")
        return True
        
    except Exception as e:
        logger.error(f"Error syncing control settings to experimental: {e}")
        return False

def show_settings_management_menu(settings_path: str, golden_queries_path: str) -> None:
    """
    Display a menu for managing settings, including comparison and synchronization options.
    
    Args:
        settings_path: Path to settings.json
        golden_queries_path: Path to golden_queries.json
    """
    # Display comparison first
    display_settings_comparison(settings_path, golden_queries_path)
    
    # Options for managing settings
    print("\nSettings Management Options:")
    print("1. Reset experimental settings to match control settings")
    print("2. Adopt experimental settings as new control settings")
    print("3. Return to main menu")
    
    try:
        choice = input("\nSelect an option (1-3): ").strip()
        
        if choice == "1":
            # Confirm action
            confirm = input("\nThis will overwrite experimental settings in golden_queries.json "
                          "with control settings from settings.json.\n"
                          "A backup will be created as golden_queries.json.bak. Continue? (y/n): ").lower()
            
            if confirm == 'y':
                if sync_experimental_to_control(settings_path, golden_queries_path):
                    print("\nExperimental settings have been reset to match control settings.")
                    print(f"Backup created at {golden_queries_path}.bak")
                    # Display updated comparison
                    display_settings_comparison(settings_path, golden_queries_path)
                else:
                    print("\nFailed to sync experimental settings to control.")
            else:
                print("Operation cancelled.")
                
        elif choice == "2":
            # Confirm action
            confirm = input("\nThis will update control settings in settings.json "
                          "with experimental settings from golden_queries.json.\n"
                          "A backup will be created as settings.json.bak. Continue? (y/n): ").lower()
            
            if confirm == 'y':
                if sync_control_to_experimental(settings_path, golden_queries_path):
                    print("\nControl settings have been updated with experimental settings.")
                    print(f"Backup created at {settings_path}.bak")
                    # Display updated comparison
                    display_settings_comparison(settings_path, golden_queries_path)
                else:
                    print("\nFailed to sync control settings to experimental.")
            else:
                print("Operation cancelled.")
                
        elif choice == "3":
            print("Returning to main menu.")
            return
        else:
            print("Invalid choice. Returning to main menu.")
    except Exception as e:
        logger.error(f"Error in settings management: {e}")
        print(f"Error: {e}")

# Command line interface for direct use
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Compare and manage NEXUS IR evaluation settings")
    parser.add_argument('--settings', type=str, default=os.path.join(parent_dir, "..", "settings.json"),
                      help='Path to settings.json')
    parser.add_argument('--golden_queries', type=str, default=os.path.join(parent_dir, "golden_queries.json"),
                      help='Path to golden_queries.json')
    parser.add_argument('--action', type=str, choices=['compare', 'sync_to_control', 'sync_to_experimental', 'menu'],
                      default='menu', help='Action to perform')
    
    args = parser.parse_args()
    
    if args.action == 'compare':
        display_settings_comparison(args.settings, args.golden_queries)
    elif args.action == 'sync_to_control':
        if sync_experimental_to_control(args.settings, args.golden_queries):
            print("Experimental settings have been reset to match control settings.")
        else:
            print("Failed to sync experimental settings to control.")
    elif args.action == 'sync_to_experimental':
        if sync_control_to_experimental(args.settings, args.golden_queries):
            print("Control settings have been updated with experimental settings.")
        else:
            print("Failed to sync control settings to experimental.")
    else:  # args.action == 'menu'
        show_settings_management_menu(args.settings, args.golden_queries)