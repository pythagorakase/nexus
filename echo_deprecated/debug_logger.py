#!/usr/bin/env python3
"""
Centralized Debug Logger for Unified Output Across Scripts
"""

def debug_print(title, message, separator="="):
    """Prints a formatted debug message."""
    print(f"\n{separator * 5} {title} {separator * 5}")
    print(message)
    print(separator * (len(title) + 12))

def debug_json(title, data):
    """Prints JSON data in a formatted debug block."""
    import json
    debug_print(title, json.dumps(data, indent=2))

