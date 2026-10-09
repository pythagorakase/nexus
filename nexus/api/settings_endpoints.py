"""Read-only repository defaults and registry metadata for the settings card."""

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

# Python 3.11+ ships tomllib; mirror the loader's fallback for older runtimes.
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python <3.11
    import tomli as tomllib  # type: ignore

from nexus.config.settings_models import (
    APEXSettings,
    materialize_model_selections,
)
from nexus.runtime.home import resolve_config_path

logger = logging.getLogger("nexus.api.settings_endpoints")

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _read_raw_settings() -> Dict[str, Any]:
    """Load the active config's roster and settings as a plain dict.

    The runtime-home locator rule picks the file, so this serves the same
    config load_settings() validates, whatever the working directory.
    """
    path = resolve_config_path()
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with open(path, "rb") as f:
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


class ModelOption(BaseModel):
    """One model the settings picker lists from ``[global.model.api_models]``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str
    label: str


class SettingsMeta(BaseModel):
    """Client-facing metadata derived from the config and the Pydantic models."""

    model_config = ConfigDict(extra="forbid")

    models: List[ModelOption]
    apex_allowed_providers: List[str]


class SettingsPayload(BaseModel):
    """The ``GET /api/settings`` response.

    One field per section of the root ``Settings`` model except ``secrets``,
    plus the derived ``settings_meta`` block. A section stays a dict: the
    endpoint serves the file's values, not the validated defaults. A section
    that ``Settings`` requires is required here; every other section is
    optional, and an unknown top-level section raises.
    """

    model_config = ConfigDict(extra="forbid")

    global_: Dict[str, Any] = Field(..., alias="global")
    local_models: Optional[Dict[str, Any]] = None
    lore: Dict[str, Any]
    orrery: Optional[Dict[str, Any]] = None
    memnon: Dict[str, Any]
    memory: Dict[str, Any]
    storyteller: Dict[str, Any]
    apex: Dict[str, Any]
    summaries: Optional[Dict[str, Any]] = None
    wizard: Dict[str, Any]
    api: Optional[Dict[str, Any]] = None
    character_identity: Optional[Dict[str, Any]] = None
    ui: Dict[str, Any]
    ir_eval: Optional[Dict[str, Any]] = None
    runtime: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, Any]] = None
    settings_meta: SettingsMeta


def _build_settings_meta(raw: Dict[str, Any]) -> SettingsMeta:
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
        ModelOption(
            id=entry["id"],
            provider=provider,
            label=entry.get("label", entry["id"]),
        )
        for provider, cfg in visible.items()
        for entry in cfg.get("models", [])
    ]

    apex_allowed_providers = [
        provider
        for provider, cfg in visible.items()
        if re.fullmatch(_APEX_PROVIDER_PATTERN, provider) or cfg.get("base_url")
    ]

    return SettingsMeta(
        models=models,
        apex_allowed_providers=apex_allowed_providers,
    )


def _build_payload(raw: Dict[str, Any]) -> SettingsPayload:
    """Raw settings under their nexus.toml names + derived metadata, minus secrets.

    ``SettingsPayload`` types the response: an unknown top-level section
    raises, as ``load_settings`` already does.
    """
    raw = materialize_model_selections(raw)
    payload = dict(raw)
    # 1Password reference strings are bootstrap-only config; the browser has
    # no business seeing them even though they contain no secret material.
    payload.pop("secrets", None)
    payload["settings_meta"] = _build_settings_meta(raw)
    return SettingsPayload.model_validate(payload)


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


@router.get("", response_model=SettingsPayload, response_model_exclude_unset=True)
async def get_settings() -> SettingsPayload:
    """Serve the full settings payload for the React client."""
    return _build_payload(_read_raw_settings())
