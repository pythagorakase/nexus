"""NEXUS configuration loading and validation."""

from .settings_models import Settings
from .loader import (
    load_settings,
    load_settings_as_dict,
    get_available_api_models,
    get_gateway_cors_allowed_origins,
    get_local_models_settings,
    get_native_structured_output_override,
    get_openai_compatible_endpoint,
    resolve_model_ref,
    save_settings,
)

__all__ = [
    "Settings",
    "load_settings",
    "load_settings_as_dict",
    "get_available_api_models",
    "get_gateway_cors_allowed_origins",
    "get_local_models_settings",
    "get_native_structured_output_override",
    "get_openai_compatible_endpoint",
    "resolve_model_ref",
    "save_settings",
]
