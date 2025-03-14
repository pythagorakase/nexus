#!/usr/bin/env python3
"""
config_manager.py: Configuration Management Module for Night City Stories

This module provides centralized configuration management for the narrative
intelligence system. It loads settings from settings.json, applies defaults,
and provides a consistent API for all modules to access configuration.

Usage:
    import config_manager as config
    db_path = config.get("database.path")
    
    # Or run standalone to validate configuration
    python config_manager.py
    
    # Or run in interactive mode
    python config_manager.py --interactive
"""

import os
import json
import logging
import atexit
import cmd
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any, Set

# Configure logging
logger = logging.getLogger("config_manager")
# Only set up handlers if they haven't been set up already
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler("config.log")
    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    
    # Register cleanup at exit
    def close_handlers():
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()
    atexit.register(close_handlers)

# Default configuration
DEFAULT_CONFIG = {
    "database": {
        "path": "NightCityStories.db",
        "enable_foreign_keys": True,
        "timeout": 30.0,
        "connection_cache_size": 5,
        "verbose_logging": False
    },
    "chromadb": {
        "path": "./chroma_db",
        "collection_name": "transcripts",
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
        },
        "chunk_marker_regex": r'<!--\s*SCENE BREAK:\s*(S\d+E\d+)_([\d]{3})'
    },
    "narrative": {
        "current_episode": "S01E01",
        "max_context_tokens": 4000,
        "character_budget": 32000,
        "api_model": "gpt-4o",
        "temperature": 0.7
    },
    "memory": {
        "enable_hierarchical_memory": True,
        "confidence_threshold": 0.7,
        "recency_weight": 0.3,
        "relevance_weight": 0.7
    },
    "entity_state": {
        "track_entity_states": True,
        "auto_update_states": True,
        "conflict_resolution": "confidence"  # confidence, recency, or manual
    },
    "logging": {
        "level": "INFO",
        "file_logging": True,
        "console_logging": True
    },
    "testing": {
        "test_data_path": "test_data/",
        "use_mock_data": False
    },
    "paths": {
        "settings_file": "settings.json",
        "output_dir": "output/",
        "log_dir": "logs/"
    },
    "agents": {
        "enable_all_agents": True,
        "lore": {
            "enabled": True,
            "model": "llama3-70b",
            "priority": 1
        },
        "psyche": {
            "enabled": True,
            "model": "phi3-medium",
            "priority": 2
        },
        "gaia": {
            "enabled": True,
            "model": "llama3-70b",
            "priority": 3
        },
        "logon": {
            "enabled": True,
            "model": "gpt-4o",
            "priority": 4
        }
    },
    "orchestration": {
        "max_iterations": 3,
        "timeout": 60,
        "parallel_execution": False,
        "communication_protocol": "json",
        "error_recovery": "fallback"
    },
    "state_management": {
        "save_state": True,
        "state_file": "narrative_state.json",
        "history_limit": 10,
        "compress_old_history": True
    }
}

# Global configuration state - stored at module level
_CONFIG = {}
_CONFIG_LOADED = False

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from the specified path, with fallback to default path
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        Dictionary containing merged configuration (defaults + user settings)
    """
    global _CONFIG, _CONFIG_LOADED
    
    # If config is already loaded and we're not forcing a reload with a specific path,
    # return the current config
    if _CONFIG_LOADED and config_path is None:
        return _CONFIG
    
    # Start with default configuration
    _CONFIG = DEFAULT_CONFIG.copy()
    
    # Determine the config path
    if config_path is None:
        config_path = DEFAULT_CONFIG["paths"]["settings_file"]
    
    settings_path = Path(config_path)
    
    try:
        if settings_path.exists():
            with open(settings_path, "r") as f:
                user_config = json.load(f)
                
            # Deep merge the user configuration into the default configuration
            deep_merge(_CONFIG, user_config)
            logger.info(f"Loaded configuration from {settings_path}")
        else:
            logger.warning(f"Configuration file not found: {settings_path}. Using default configuration.")
    
    except Exception as e:
        logger.error(f"Error loading configuration: {e}. Using default configuration.")
    
    _CONFIG_LOADED = True
    return _CONFIG

def deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge source dictionary into target
    
    Args:
        target: Target dictionary to merge into
        source: Source dictionary to merge from
        
    Returns:
        The modified target dictionary
    """
    for key, value in source.items():
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            # Recursively merge dictionaries
            deep_merge(target[key], value)
        else:
            # Overwrite or add values
            target[key] = value
            
    return target

def get(key_path: str, default: Any = None) -> Any:
    """
    Get a configuration value using dot notation
    
    Args:
        key_path: Path to the configuration value (e.g., "database.path")
        default: Default value to return if the key is not found
        
    Returns:
        The configuration value or the default value
    """
    global _CONFIG, _CONFIG_LOADED
    
    # Ensure configuration is loaded
    if not _CONFIG_LOADED:
        load_config()
    
    # Navigate through the config using the key path
    keys = key_path.split(".")
    current = _CONFIG
    
    try:
        for key in keys:
            current = current[key]
        return current
    except (KeyError, TypeError):
        return default

def set(key_path: str, value: Any) -> bool:
    """
    Set a configuration value using dot notation
    
    Args:
        key_path: Path to the configuration value (e.g., "database.path")
        value: Value to set
        
    Returns:
        True if successful, False otherwise
    """
    global _CONFIG, _CONFIG_LOADED
    
    # Ensure configuration is loaded
    if not _CONFIG_LOADED:
        load_config()
    
    # Navigate through the config using the key path
    keys = key_path.split(".")
    current = _CONFIG
    
    try:
        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        
        # Set the value
        current[keys[-1]] = value
        return True
    except Exception as e:
        logger.error(f"Error setting configuration value for {key_path}: {e}")
        return False

def save_config(config_path: Optional[str] = None) -> bool:
    """
    Save the current configuration to a file
    
    Args:
        config_path: Optional path to save the configuration file
        
    Returns:
        True if the configuration was saved successfully, False otherwise
    """
    global _CONFIG, _CONFIG_LOADED
    
    # Ensure configuration is loaded
    if not _CONFIG_LOADED:
        load_config()
    
    # Determine the config path
    if config_path is None:
        config_path = DEFAULT_CONFIG["paths"]["settings_file"]
    
    settings_path = Path(config_path)
    
    try:
        # Create parent directory if it doesn't exist
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write the configuration to file
        with open(settings_path, "w") as f:
            json.dump(_CONFIG, f, indent=2)
            
        logger.info(f"Saved configuration to {settings_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        return False

def reset_to_defaults() -> None:
    """Reset the configuration to default values"""
    global _CONFIG, _CONFIG_LOADED
    _CONFIG = DEFAULT_CONFIG.copy()
    _CONFIG_LOADED = True
    logger.info("Configuration reset to default values")

def get_section(section: str) -> Dict[str, Any]:
    """
    Get a specific section of the configuration
    
    Args:
        section: Section name (e.g., "database")
        
    Returns:
        Dictionary containing the section's configuration
    """
    global _CONFIG, _CONFIG_LOADED
    
    # Ensure configuration is loaded
    if not _CONFIG_LOADED:
        load_config()
    
    return _CONFIG.get(section, {})

def get_environment() -> str:
    """
    Get the current environment (development, testing, production)
    
    Returns:
        Environment name
    """
    env = os.environ.get("NCS_ENVIRONMENT", "development")
    return env.lower()

def is_production() -> bool:
    """Check if running in production environment"""
    return get_environment() == "production"

def is_testing() -> bool:
    """Check if running in testing environment"""
    return get_environment() == "testing"

def setup_for_testing() -> None:
    """Configure settings for testing environment"""
    # Apply testing-specific settings
    set("database.path", ":memory:")
    set("database.verbose_logging", True)
    set("logging.level", "DEBUG")
    set("testing.use_mock_data", True)
    
    logger.info("Configuration set up for testing environment")

def validate_config() -> List[str]:
    """
    Validate the current configuration
    
    Returns:
        List of validation error messages (empty if valid)
    """
    global _CONFIG, _CONFIG_LOADED
    
    # Ensure configuration is loaded
    if not _CONFIG_LOADED:
        load_config()
    
    errors = []
    
    # Check required settings
    if not get("database.path"):
        errors.append("Database path is not set")
    
    if not get("chromadb.path"):
        errors.append("ChromaDB path is not set")
    
    # Check for valid ranges
    db_timeout = get("database.timeout", 0)
    if not isinstance(db_timeout, (int, float)) or db_timeout <= 0:
        errors.append("Database timeout must be a positive number")
    
    # Check for valid model weights
    model_weights = [
        get("chromadb.embedding_models.bge_large.weight", 0),
        get("chromadb.embedding_models.e5_large.weight", 0),
        get("chromadb.embedding_models.bge_small.weight", 0)
    ]
    
    weight_sum = sum(model_weights)
    if abs(weight_sum - 1.0) > 0.001:  # Allow for floating point imprecision
        errors.append(f"Embedding model weights must sum to 1.0 (current sum: {weight_sum})")
    
    return errors

def print_config(section: Optional[str] = None) -> None:
    """
    Print the current configuration
    
    Args:
        section: Optional section name to print only that section
    """
    global _CONFIG, _CONFIG_LOADED
    
    # Ensure configuration is loaded
    if not _CONFIG_LOADED:
        load_config()
    
    if section:
        print(f"Configuration section: {section}")
        print(json.dumps(get_section(section), indent=2))
    else:
        print("Full configuration:")
        print(json.dumps(_CONFIG, indent=2))

def close_log_handlers():
    """Close all log handlers to prevent resource warnings"""
    # Close handlers for the config_manager logger
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logger.removeHandler(handler)

# Create aliases for backward compatibility with tinker.py
save = save_config
load = load_config

# Initialize configuration on module import
load_config()

def main():
    """Main entry point when run as a script"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Configuration Management Module")
    parser.add_argument("--load", help="Load configuration from the specified file")
    parser.add_argument("--save", help="Save configuration to the specified file")
    parser.add_argument("--validate", action="store_true", help="Validate the configuration")
    parser.add_argument("--reset", action="store_true", help="Reset to default configuration")
    parser.add_argument("--print", action="store_true", help="Print the configuration")
    parser.add_argument("--section", help="Specify a configuration section")
    parser.add_argument("--get", help="Get a configuration value (dot notation)")
    parser.add_argument("--set", help="Set a configuration value (dot notation)")
    parser.add_argument("--value", help="Value to set (used with --set)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Start interactive configuration shell")
    args = parser.parse_args()
    
    if args.load:
        load_config(args.load)
        print(f"Loaded configuration from {args.load}")
    
    if args.reset:
        reset_to_defaults()
        print("Reset configuration to defaults")
    
    if args.get:
        value = get(args.get)
        print(f"{args.get} = {value}")
    
    if args.set and args.value is not None:
        # Try to parse the value as JSON, fall back to string
        try:
            value = json.loads(args.value)
        except json.JSONDecodeError:
            value = args.value
            
        if set(args.set, value):
            print(f"Set {args.set} = {value}")
        else:
            print(f"Failed to set {args.set}")
    
    if args.validate:
        errors = validate_config()
        if errors:
            print("Configuration validation errors:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("Configuration is valid")
    
    if args.print:
        print_config(args.section)
    
    if args.save:
        if save_config(args.save):
            print(f"Saved configuration to {args.save}")
        else:
            print(f"Failed to save configuration to {args.save}")
    
    if args.interactive:
        ConfigShell().cmdloop()
    
    # If no arguments were provided, show help
    if not any(vars(args).values()):
        parser.print_help()

class ConfigShell(cmd.Cmd):
    """Interactive shell for navigating and editing configuration."""
    
    intro = "Welcome to the Night City Stories Configuration Shell. Type help or ? to list commands.\n"
    prompt = "config> "
    
    def __init__(self):
        super().__init__()
        self.current_path = []
        self.update_prompt()
    
    def update_prompt(self):
        """Update the prompt to show the current path"""
        if not self.current_path:
            self.prompt = "config> "
        else:
            path_str = ".".join(self.current_path)
            self.prompt = f"config:{path_str}> "
    
    def get_current_node(self):
        """Get the dictionary node at the current path"""
        global _CONFIG
        
        if not self.current_path:
            return _CONFIG
        
        # Build the key path
        key_path = ".".join(self.current_path)
        
        # Try to get the node
        node = get(key_path)
        
        # Check if it's a dictionary
        if isinstance(node, dict):
            return node
        else:
            return None
    
    def do_ls(self, arg):
        """List items in the current configuration section.
        Usage: ls [pattern]"""
        node = self.get_current_node()
        
        if node is None:
            print("Current path is not a configuration section.")
            return
        
        if not node:
            print("No items in this section.")
            return
        
        # Filter by pattern if provided
        pattern = arg.strip() if arg else None
        
        # Print out keys and their types
        print("\nKey\t\tType\t\tValue")
        print("-" * 60)
        
        for key, value in sorted(node.items()):
            if pattern and pattern not in key:
                continue
                
            value_type = type(value).__name__
            
            # Format the value string based on type
            if isinstance(value, dict):
                value_str = "{...}"
            elif isinstance(value, (list, tuple)):
                value_str = f"{value_type}[{len(value)}]"
            elif isinstance(value, str) and len(value) > 40:
                value_str = f'"{value[:37]}..."'
            else:
                value_str = repr(value)
            
            # Add padding to align columns
            key_pad = "\t\t" if len(key) < 8 else "\t"
            type_pad = "\t\t" if len(value_type) < 8 else "\t"
            
            print(f"{key}{key_pad}{value_type}{type_pad}{value_str}")
    
    def complete_ls(self, text, line, begidx, endidx):
        """Tab completion for ls command"""
        node = self.get_current_node()
        if node is None:
            return []
        
        return [key for key in node.keys() if key.startswith(text)]
    
    def do_cd(self, arg):
        """Change to a different section of the configuration.
        Usage: cd sectionname or cd .. to go up one level"""
        if not arg:
            # Show current path
            if not self.current_path:
                print("Current path: [root]")
            else:
                print(f"Current path: {'.'.join(self.current_path)}")
            return
        
        if arg == "..":
            # Go up one level
            if self.current_path:
                self.current_path.pop()
                self.update_prompt()
            return
        elif arg == "/":
            # Go to root
            self.current_path = []
            self.update_prompt()
            return
        
        # Handle multiple path segments
        segments = arg.split('.')
        
        # Build temporary path to check
        temp_path = self.current_path.copy()
        for segment in segments:
            if segment == "..":
                if temp_path:
                    temp_path.pop()
            else:
                temp_path.append(segment)
        
        # Check if the path exists and is a dictionary
        temp_key_path = ".".join(temp_path)
        temp_node = get(temp_key_path) if temp_path else _CONFIG
        
        if isinstance(temp_node, dict):
            self.current_path = temp_path
            self.update_prompt()
        else:
            print(f"Invalid path: {temp_key_path}")
    
    def complete_cd(self, text, line, begidx, endidx):
        """Tab completion for cd command"""
        node = self.get_current_node()
        if node is None:
            return []
        
        # Add ".." for going up a level
        completions = [".."]
        
        # Add dictionary keys
        for key, value in node.items():
            if isinstance(value, dict) and key.startswith(text):
                completions.append(key)
        
        return completions
    
    def do_cat(self, arg):
        """Display the value of a configuration item.
        Usage: cat key"""
        if not arg:
            print("Usage: cat <key>")
            return
        
        # Build the key path
        if self.current_path:
            key_path = ".".join(self.current_path + [arg])
        else:
            key_path = arg
        
        # Get the value
        value = get(key_path)
        
        if value is None:
            print(f"Key not found: {key_path}")
            return
        
        # Pretty print the value
        if isinstance(value, (dict, list)):
            print(json.dumps(value, indent=2))
        else:
            print(value)
    
    def complete_cat(self, text, line, begidx, endidx):
        """Tab completion for cat command"""
        node = self.get_current_node()
        if node is None:
            return []
        
        return [key for key in node.keys() if key.startswith(text)]
    
    def do_set(self, arg):
        """Set a configuration value.
        Usage: set key value"""
        args = arg.split(maxsplit=1)
        
        if len(args) < 2:
            print("Usage: set <key> <value>")
            return
        
        key, value_str = args
        
        # Build the key path
        if self.current_path:
            key_path = ".".join(self.current_path + [key])
        else:
            key_path = key
        
        # Try to parse the value as JSON
        try:
            value = json.loads(value_str)
        except json.JSONDecodeError:
            # If parsing as JSON fails, use the string value
            value = value_str
        
        # Set the value
        if set(key_path, value):
            print(f"Set {key_path} = {value}")
        else:
            print(f"Failed to set {key_path}")
    
    def complete_set(self, text, line, begidx, endidx):
        """Tab completion for set command"""
        node = self.get_current_node()
        if node is None:
            return []
        
        words = line.split()
        
        if len(words) <= 2:  # completing the key
            return [key for key in node.keys() if key.startswith(text)]
        else:  # completing the value - no completion
            return []
    
    def do_save(self, arg):
        """Save the current configuration.
        Usage: save [filename]"""
        filename = arg.strip() if arg else None
        
        if save_config(filename):
            if filename:
                print(f"Saved configuration to {filename}")
            else:
                print(f"Saved configuration to {get('paths.settings_file')}")
        else:
            print("Failed to save configuration")
    
    def do_load(self, arg):
        """Load configuration from a file.
        Usage: load [filename]"""
        filename = arg.strip() if arg else None
        
        load_config(filename)
        if filename:
            print(f"Loaded configuration from {filename}")
        else:
            print(f"Loaded configuration from {get('paths.settings_file')}")
        
        # Reset the current path, as structure may have changed
        self.current_path = []
        self.update_prompt()
    
    def do_validate(self, arg):
        """Validate the current configuration."""
        errors = validate_config()
        
        if errors:
            print("Configuration validation errors:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("Configuration is valid")
    
    def do_reset(self, arg):
        """Reset configuration to defaults."""
        reset_to_defaults()
        print("Reset configuration to defaults")
        
        # Reset the current path
        self.current_path = []
        self.update_prompt()
    
    def do_find(self, arg):
        """Find configuration keys matching a pattern.
        Usage: find pattern"""
        if not arg:
            print("Usage: find <pattern>")
            return
        
        pattern = arg.lower()
        results = []
        
        def search_dict(d, path=""):
            for key, value in d.items():
                current_path = f"{path}.{key}" if path else key
                
                if pattern in key.lower() or (
                    isinstance(value, str) and pattern in value.lower()
                ):
                    results.append((current_path, value))
                
                if isinstance(value, dict):
                    search_dict(value, current_path)
        
        search_dict(_CONFIG)
        
        if not results:
            print(f"No matches found for '{pattern}'")
            return
        
        print(f"\nFound {len(results)} matches for '{pattern}':")
        print("-" * 60)
        
        for path, value in sorted(results):
            value_type = type(value).__name__
            
            # Format the value string based on type
            if isinstance(value, dict):
                value_str = "{...}"
            elif isinstance(value, (list, tuple)):
                value_str = f"{value_type}[{len(value)}]"
            elif isinstance(value, str) and len(value) > 40:
                value_str = f'"{value[:37]}..."'
            else:
                value_str = repr(value)
            
            print(f"{path}: {value_str}")
    
    def do_pwd(self, arg):
        """Print current configuration path."""
        if not self.current_path:
            print("[root]")
        else:
            print(".".join(self.current_path))
    
    def do_exit(self, arg):
        """Exit the configuration shell."""
        print("Exiting configuration shell.")
        return True
    
    def do_quit(self, arg):
        """Exit the configuration shell."""
        return self.do_exit(arg)
    
    def do_EOF(self, arg):
        """Exit on Ctrl-D."""
        print()  # Add a newline
        return self.do_exit(arg)
    
    def emptyline(self):
        """Do nothing on empty line."""
        pass
    
    def help_commands(self):
        """Print a summary of all commands"""
        print("\nConfiguration Shell Commands:")
        print("-" * 60)
        print("ls [pattern]     - List configuration items in current section")
        print("cd [section]     - Change to a configuration section")
        print("cd ..            - Go up one level")
        print("cd /             - Go to root level")
        print("pwd              - Show current configuration path")
        print("cat <key>        - Show value of a configuration item")
        print("set <key> <value> - Set a configuration value")
        print("find <pattern>   - Find configuration keys matching pattern")
        print("save [filename]  - Save configuration to file")
        print("load [filename]  - Load configuration from file")
        print("validate         - Validate current configuration")
        print("reset            - Reset to default configuration")
        print("exit/quit        - Exit the configuration shell")
        print()

def reset_module_state():
    """
    Completely reset the module state - used for testing purposes.
    This ensures no state is shared between tests.
    """
    global _CONFIG, _CONFIG_LOADED
    _CONFIG = {}
    _CONFIG_LOADED = False
    logger.info("Module state completely reset")

if __name__ == "__main__":
    try:
        main()
    finally:
        close_log_handlers()