"""Read-only repository defaults and registry metadata for the settings card."""

import logging
import re
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Response
from pydantic import BaseModel

# Python 3.11+ ships tomllib; mirror the loader's fallback for older runtimes.
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python <3.11
    import tomli as tomllib  # type: ignore

from nexus.config.settings_models import (
    APEXSettings,
    materialize_model_selections,
)

logger = logging.getLogger("nexus.api.settings_endpoints")

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Resolved relative to the process CWD, matching every other load_settings()
# caller in the API layer (the narrative service runs from the repo root).
NEXUS_TOML = Path("nexus.toml")


def _read_raw_settings() -> Dict[str, Any]:
    """Load the persisted roster and settings as a plain dict."""
    if not NEXUS_TOML.exists():
        raise FileNotFoundError(f"Configuration file not found: {NEXUS_TOML}")
    with open(NEXUS_TOML, "rb") as f:
        return tomllib.load(f)


def _field_constraint(model: type[BaseModel], field: str, attr: str) -> Any:
    """Extract a constraint value (pattern/ge/le) from a Pydantic field."""
    for meta in model.model_fields[field].metadata:
        value = getattr(meta, attr, None)
        if value is not None:
            return value
    raise RuntimeError(
        f"{model.__name__}.{field} is missing the expected '{attr}' constraint"
    )


# Resolved eagerly so a renamed/removed Pydantic constraint fails at import
# (server startup) rather than on the first GET /api/settings request.
_APEX_PROVIDER_PATTERN: str = _field_constraint(APEXSettings, "provider", "pattern")


def _build_settings_meta(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the client-facing metadata block from config + Pydantic models.

    Providers flagged ``ui_visible = false`` in the api_models registry (the
    TEST mock server) are excluded from every list served here - the settings
    pane is a UI-facing model surface. The ``True`` default mirrors
    ``ProviderModels.ui_visible``; backend/CLI callers read the registry
    through the loader and are unaffected.
    """
    api_models = raw.get("global", {}).get("model", {}).get("api_models", {})
    visible = {
        provider: cfg
        for provider, cfg in api_models.items()
        if cfg.get("ui_visible", True)
    }

    models = [
        {
            "id": entry["id"],
            "provider": provider,
            "label": entry.get("label", entry["id"]),
        }
        for provider, cfg in visible.items()
        for entry in cfg.get("models", [])
    ]

    apex_allowed_providers = [
        provider
        for provider, cfg in visible.items()
        if re.fullmatch(_APEX_PROVIDER_PATTERN, provider) or cfg.get("base_url")
    ]

    return {
        "models": models,
        "apex_allowed_providers": apex_allowed_providers,
    }


def _build_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Raw settings + legacy aliases + derived metadata, minus secrets refs."""
    raw = materialize_model_selections(raw)
    payload = dict(raw)
    # 1Password reference strings are bootstrap-only config; the browser has
    # no business seeing them even though they contain no secret material.
    payload.pop("secrets", None)
    payload["Agent Settings"] = {
        "global": raw.get("global", {}),
        "LORE": raw.get("lore", {}),
        "MEMNON": raw.get("memnon", {}),
    }
    payload["API Settings"] = {"apex": raw.get("apex", {})}
    payload["settings_meta"] = _build_settings_meta(raw)
    return payload


@router.head("")
async def head_settings() -> Response:
    """Connectivity probe (useNarrativeEngine polls HEAD /api/settings).

    FastAPI's APIRoute does not auto-serve HEAD from GET handlers (unlike
    bare Starlette routes), so the probe needs this explicit handler.
    Raises - and therefore returns 500 - if the config file is unreadable,
    matching the retired Express behavior.
    """
    _read_raw_settings()
    return Response(status_code=200)


@router.get("")
async def get_settings() -> Dict[str, Any]:
    """Serve the full settings payload for the React client."""
    return _build_payload(_read_raw_settings())
