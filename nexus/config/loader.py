"""
Configuration loader for NEXUS.

Loads and validates settings from nexus.toml using Pydantic models.
Falls back to settings.json for backward compatibility during migration.
"""

import sys
from pathlib import Path
from typing import Union, Dict, Any
import json

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


# Cache for available models (avoids repeated config reads)
_available_models_cache: list[str] | None = None


def get_available_api_models() -> list[str]:
    """
    Get available API models from nexus.toml configuration (cached).

    Returns:
        List of available model names from config, or fallback defaults
        if configuration is unavailable.

    Examples:
        >>> models = get_available_api_models()
        >>> "gpt-5.1" in models
        True
    """
    global _available_models_cache
    if _available_models_cache is None:
        try:
            settings = load_settings()
            _available_models_cache = settings.global_.model.available_models
        except Exception:
            # Fallback to hardcoded defaults if config unavailable
            _available_models_cache = ["gpt-5.1", "TEST", "claude"]
    return _available_models_cache


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
        >>> settings.apex.model
        'gpt-5.1'
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
                f"Configuration file not found: {path}\n"
                f"Also checked: {legacy_path}"
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

    transformed_data = {
        "global": {
            "model": legacy_global.get("model", {}),
            "llm": legacy_global.get("llm", {}),
            "narrative": legacy_global.get("narrative", {}),
        },
        "lore": legacy_agent_settings.get("LORE", {}),
        "memnon": legacy_agent_settings.get("MEMNON", {}),
        "memory": data.get("memory", {}),
        "apex": data.get("API Settings", {}).get("apex", {}),
    }

    try:
        settings = Settings(**transformed_data)
        return settings
    except Exception as e:
        print(f"❌ Error validating legacy {path}:", file=sys.stderr)
        print(f"   {e}", file=sys.stderr)
        print(f"   Note: Legacy settings.json may not be fully compatible.", file=sys.stderr)
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
