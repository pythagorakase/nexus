"""
Configuration loader for NEXUS.

Loads and validates settings from nexus.toml using Pydantic models.
Falls back to settings.json for backward compatibility during migration.
"""

import shutil
import sys
from pathlib import Path
from typing import Union, Dict, Any, List, Optional
import json
import logging

import tomlkit

# Try Python 3.11+ built-in tomllib, fall back to tomli
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        raise ImportError(
            "TOML support requires Python 3.11+ or the 'tomli' package. "
            "Install with: pip install tomli"
        )

from .settings_models import Settings

logger = logging.getLogger("nexus.config.loader")


def save_settings(
    updates: Dict[str, Any],
    path: Union[str, Path] = "nexus.toml",
    validate: bool = True,
    backup: bool = True,
) -> None:
    """
    Save partial updates to nexus.toml while preserving comments and formatting.

    Args:
        updates: Dictionary of updates using dot-notation keys.
                 Example: {"global.model.default_model": "@openai.default"}
        path: Path to TOML file (default: nexus.toml)
        validate: If True, validate the merged config against Pydantic models
                  before writing. Raises ValidationError if invalid.
        backup: If True, create a .bak file before writing.

    Raises:
        FileNotFoundError: If the TOML file doesn't exist
        pydantic.ValidationError: If validate=True and merged config is invalid
        ValueError: If updates contain invalid key paths
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    # Load existing file with tomlkit (preserves structure)
    with open(path, "r") as f:
        doc = tomlkit.load(f)

    # Apply updates using nested key navigation
    for key_path, value in updates.items():
        _set_nested_value(doc, key_path, value)

    # Validate merged config against Pydantic models
    if validate:
        merged_dict = _tomlkit_to_dict(doc)
        Settings(**merged_dict)  # Raises ValidationError if invalid

    # Create backup
    if backup:
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)

    # Write back using tomlkit (preserves comments)
    with open(path, "w") as f:
        tomlkit.dump(doc, f)


def _set_nested_value(doc: tomlkit.TOMLDocument, key_path: str, value: Any) -> None:
    """Set a value in a tomlkit document using dot-notation path."""
    keys = key_path.split(".")
    target = doc

    # Navigate to parent, creating intermediate tables if needed
    for key in keys[:-1]:
        if key not in target:
            target[key] = tomlkit.table()
        target = target[key]

    # Set the final value with appropriate tomlkit type
    final_key = keys[-1]
    if isinstance(value, list):
        arr = tomlkit.array()
        arr.extend(value)
        # Preserve multiline style if existing value is multiline
        # tomlkit doesn't track this on parse, so check string representation
        if final_key in target:
            existing = target[final_key]
            if hasattr(existing, "as_string") and "\n" in existing.as_string():
                arr.multiline(True)
        target[final_key] = arr
    else:
        target[final_key] = value


def _tomlkit_to_dict(doc: tomlkit.TOMLDocument) -> Dict[str, Any]:
    """Convert tomlkit document to plain dict for Pydantic validation."""

    def unwrap(item: Any) -> Any:
        if isinstance(item, dict):
            return {k: unwrap(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [unwrap(v) for v in item]
        elif hasattr(item, "unwrap"):
            return item.unwrap()
        return item

    return unwrap(doc)


def get_available_api_models() -> List[str]:
    """
    Get available API model IDs from nexus.toml configuration.

    Reads fresh from config on each call to ensure changes are picked up
    without requiring server restart. Raises if config is unavailable —
    no fallback defaults, since stale fallbacks were the original drift bug.

    Returns:
        List of available model IDs from the active registry.
    """
    return [m["id"] for m in get_all_api_models()]


def get_api_models_by_provider() -> Dict[str, List[dict]]:
    """
    Get API models grouped by provider, sourced from nexus.toml.

    Returns:
        Dictionary mapping provider name to list of model dicts.
        Each model dict contains: id, label, description
    """
    settings = load_settings()
    return {
        provider: [m.model_dump() for m in config.models]
        for provider, config in settings.global_.model.api_models.items()
        if config.models
    }


def get_all_api_models() -> List[dict]:
    """
    Get flat list of all API models with provider info.

    Returns:
        List of model dicts, each containing: id, label, description, provider
    """
    result = []
    for provider, models in get_api_models_by_provider().items():
        for model in models:
            result.append({**model, "provider": provider})
    return result


def get_provider_for_model(model_id: str) -> Optional[str]:
    """
    Look up which provider a model belongs to.

    Args:
        model_id: A registry model identifier from nexus.toml's api_models section

    Returns:
        Provider name ("openai", "anthropic", "test") or None if not found
    """
    for provider, models in get_api_models_by_provider().items():
        if any(m["id"] == model_id for m in models):
            return provider
    return None


def load_settings(path: Union[str, Path] = "nexus.toml") -> Settings:
    """
    Load and validate NEXUS configuration.

    Args:
        path: Path to configuration file (nexus.toml or settings.json)

    Returns:
        Validated Settings object with type-safe access to configuration

    Raises:
        FileNotFoundError: If configuration file doesn't exist
        pydantic.ValidationError: If configuration is invalid
        ValueError: If file format is not supported

    Examples:
        >>> settings = load_settings()
        >>> settings.lore.debug
        True
        >>> # settings.apex.model resolves to a concrete ID from the api_models
        >>> # registry (e.g. whatever openai.default points at).
    """
    path = Path(path)

    # Try nexus.toml first
    if not path.exists():
        # Fall back to settings.json for backward compatibility
        legacy_path = Path("settings.json")
        if legacy_path.exists():
            print(
                "⚠️  WARNING: Using legacy settings.json. "
                "Please migrate to nexus.toml for better validation and comments."
            )
            return _load_from_json(legacy_path)
        else:
            raise FileNotFoundError(
                f"Configuration file not found: {path}\n" f"Also checked: {legacy_path}"
            )

    # Load based on file extension
    if path.suffix == ".toml":
        return _load_from_toml(path)
    elif path.suffix == ".json":
        print(
            "⚠️  WARNING: Using legacy settings.json. "
            "Please migrate to nexus.toml for better validation and comments."
        )
        return _load_from_json(path)
    else:
        raise ValueError(f"Unsupported configuration format: {path.suffix}")


def _load_from_toml(path: Path) -> Settings:
    """Load configuration from TOML file."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    try:
        settings = Settings(**data)
        return settings
    except Exception as e:
        print(f"❌ Error validating {path}:", file=sys.stderr)
        print(f"   {e}", file=sys.stderr)
        raise


def _load_from_json(path: Path) -> Settings:
    """
    Load configuration from legacy JSON file.

    This function attempts to map the old settings.json structure to the new
    Settings model. May not support all legacy keys.
    """
    with open(path, "r") as f:
        data = json.load(f)

    # Transform legacy structure to new structure
    # Legacy has "Agent Settings" with nested agents, we want flat structure
    legacy_agent_settings = data.get("Agent Settings", {})
    legacy_global = legacy_agent_settings.get("global", {})
    legacy_model = dict(legacy_global.get("model", {}))
    legacy_model.pop("possible_values", None)
    legacy_model.pop("description", None)
    if "llm" in data or "llm" in legacy_agent_settings:
        logger.debug("Ignoring legacy local LLM router config from settings.json")
    # If api_models is missing from legacy JSON, the Settings validator will
    # surface a clear error rather than silently filling in stale defaults.

    legacy_new_story = data.get("API Settings", {}).get("new_story", {})

    transformed_data = {
        "global": {
            "model": legacy_model,
            "narrative": legacy_global.get("narrative", {}),
        },
        "lore": legacy_agent_settings.get("LORE", {}),
        "memnon": legacy_agent_settings.get("MEMNON", {}),
        "memory": data.get("memory", {}),
        "apex": data.get("API Settings", {}).get("apex", {}),
        "wizard": {
            "default_model": legacy_new_story.get("model", "@openai.default"),
            "fallback_model": legacy_new_story.get("fallback_model"),
            "message_history_limit": legacy_new_story.get("message_history_limit", 20),
            "max_retries": legacy_new_story.get("max_retries", 2),
            "max_tokens": legacy_new_story.get("max_tokens", 2048),
            "enable_streaming": legacy_new_story.get("enable_streaming", True),
        },
    }

    try:
        settings = Settings(**transformed_data)
        return settings
    except Exception as e:
        print(f"❌ Error validating legacy {path}:", file=sys.stderr)
        print(f"   {e}", file=sys.stderr)
        print(
            f"   Note: Legacy settings.json may not be fully compatible.",
            file=sys.stderr,
        )
        print(f"   Please migrate to nexus.toml.", file=sys.stderr)
        raise


def load_settings_as_dict(path: Union[str, Path] = "nexus.toml") -> Dict[str, Any]:
    """
    Load settings and return as dict for backward compatibility.

    This preserves the old Dict[str, Any] interface for code that hasn't been
    migrated to use the Settings model directly.

    Args:
        path: Path to configuration file

    Returns:
        Dictionary representation of settings
    """
    settings = load_settings(path)
    settings_dict = settings.model_dump()

    # Preserve legacy structure for callers expecting "Agent Settings" and "API Settings"
    legacy_agent_settings = {
        "global": settings_dict.get("global", {}),
        "LORE": settings_dict.get("lore", {}),
        "MEMNON": settings_dict.get("memnon", {}),
    }
    legacy_api_settings = {"apex": settings_dict.get("apex", {})}

    return {
        **settings_dict,
        "Agent Settings": legacy_agent_settings,
        "API Settings": legacy_api_settings,
    }
