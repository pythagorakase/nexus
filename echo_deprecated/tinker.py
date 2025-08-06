#!/usr/bin/env python3
"""
tinker.py: Compatibility wrapper for config_manager.py

DEPRECATED: This module is maintained for backward compatibility only.
New code should import config_manager directly.

This file provides backward compatibility for code that expects tinker.py,
by delegating all calls to config_manager.py.
"""

import config_manager
import warnings

# Show deprecation warning when imported
warnings.warn(
    "The tinker module is deprecated. Please use config_manager instead.", 
    DeprecationWarning, 
    stacklevel=2
)

# Delegate all functions to config_manager
def load_config(*args, **kwargs):
    return config_manager.load_config(*args, **kwargs)

def get(*args, **kwargs):
    return config_manager.get(*args, **kwargs)

def set(*args, **kwargs):
    return config_manager.set(*args, **kwargs)

def save_config(*args, **kwargs):
    return config_manager.save_config(*args, **kwargs)

def reset_to_defaults(*args, **kwargs):
    return config_manager.reset_to_defaults(*args, **kwargs)

def get_section(*args, **kwargs):
    return config_manager.get_section(*args, **kwargs)

def get_environment(*args, **kwargs):
    return config_manager.get_environment(*args, **kwargs)

def is_production(*args, **kwargs):
    return config_manager.is_production(*args, **kwargs)

def is_testing(*args, **kwargs):
    return config_manager.is_testing(*args, **kwargs)

def setup_for_testing(*args, **kwargs):
    return config_manager.setup_for_testing(*args, **kwargs)

def validate_config(*args, **kwargs):
    return config_manager.validate_config(*args, **kwargs)

def print_config(*args, **kwargs):
    return config_manager.print_config(*args, **kwargs)

def close_log_handlers(*args, **kwargs):
    return config_manager.close_log_handlers(*args, **kwargs)

# Make sure reset_module_state is available for testing
def reset_module_state(*args, **kwargs):
    return config_manager.reset_module_state(*args, **kwargs)

# Aliases for backward compatibility
save = save_config
load = load_config