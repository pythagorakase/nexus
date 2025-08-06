#!/usr/bin/env python3
"""
Load Storytelling Settings from settings.json
"""

import json
from pathlib import Path

SETTINGS_FILE = Path("settings.json")

def load_storytelling_rules():
    """Loads storytelling rules from settings.json."""
    if not SETTINGS_FILE.exists():
        print("⚠️ Warning: settings.json not found. Using default storytelling rules.")
        return {}

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
        return settings.get("storytelling_rules", {})
    except Exception as e:
        print(f"⚠️ Error loading storytelling rules: {e}")
        return {}

