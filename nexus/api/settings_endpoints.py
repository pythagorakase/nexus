"""
FastAPI endpoints for the operator settings surface (GET/PATCH /api/settings).

GET serves the raw nexus.toml contents (with @provider.role references left
unresolved so the client can show role-level bindings), plus the legacy
"Agent Settings"/"API Settings" aliases the React client predates, plus a
derived ``settings_meta`` block (model role options, apex provider allowlist,
typewriter bounds) so the client never hardcodes config semantics.

PATCH accepts a typed subset of safe-to-edit keys and persists them through
``nexus.config.loader.save_settings``, which validates the merged document
against the Pydantic Settings model and preserves comments/formatting via
tomlkit. Keys outside this subset (active embedding model, test database
suffix, reranker paths, ...) are intentionally not writable from the UI.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Python 3.11+ ships tomllib; mirror the loader's fallback for older runtimes.
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python <3.11
    import tomli as tomllib  # type: ignore

from nexus.config.loader import save_settings
from nexus.config.settings_models import (
    MODEL_ROLE_PREFIX,
    APEXSettings,
    UISettings,
)

logger = logging.getLogger("nexus.api.settings_endpoints")

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Resolved relative to the process CWD, matching every other load_settings()
# caller in the API layer (the narrative service runs from the repo root).
NEXUS_TOML = Path("nexus.toml")

ThemeId = Literal["veil", "gilded", "vector"]


class FontSlotsPatch(BaseModel):
    """Partial font slot update for one theme.

    ``display`` (the marquee slot) is locked in the settings pane per the
    design system's marquee rule, but stays writable here deliberately:
    the pane's RESET TO KEEPERS action PATCHes the full keeper matrix
    (display included), and the API remains the operator escape hatch for
    rebinding the marquee without hand-editing nexus.toml.
    """

    model_config = ConfigDict(extra="forbid")

    body: Optional[str] = None
    menu: Optional[str] = None
    display: Optional[str] = None


class SettingsPatchRequest(BaseModel):
    """The safe-to-edit settings subset accepted by PATCH /api/settings."""

    model_config = ConfigDict(extra="forbid")

    theme: Optional[ThemeId] = Field(
        default=None, description="Active NEXUS IRIS theme (ui.theme)"
    )
    fonts: Optional[Dict[ThemeId, FontSlotsPatch]] = Field(
        default=None, description="Per-theme font slot choices (ui.fonts.*)"
    )
    typewriter_ms_per_char: Optional[int] = Field(
        default=None, description="Typewriter reveal speed (ui.typewriter_ms_per_char)"
    )
    test_mode: Optional[bool] = Field(
        default=None, description="Test write routing (global.narrative.test_mode)"
    )
    apex_model_ref: Optional[str] = Field(
        default=None,
        description=(
            "Role reference for live narrative turns, e.g. '@anthropic.deep' "
            "(apex.model; apex.provider is derived from the reference)"
        ),
    )
    wizard_model_ref: Optional[str] = Field(
        default=None,
        description="Role reference for the new-story wizard (wizard.default_model)",
    )
    apex_context_window: Optional[int] = Field(
        default=None,
        description="LORE context budget (lore.token_budget.apex_context_window)",
    )


def _read_raw_settings() -> Dict[str, Any]:
    """Load nexus.toml as a plain dict without resolving model references."""
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
_TYPEWRITER_BOUNDS: Dict[str, int] = {
    "min": _field_constraint(UISettings, "typewriter_ms_per_char", "ge"),
    "max": _field_constraint(UISettings, "typewriter_ms_per_char", "le"),
}


def _build_settings_meta(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the client-facing metadata block from config + Pydantic models."""
    api_models = raw.get("global", {}).get("model", {}).get("api_models", {})
    labels_by_id: Dict[str, str] = {}
    for provider_cfg in api_models.values():
        for entry in provider_cfg.get("models", []):
            labels_by_id[entry["id"]] = entry.get("label", entry["id"])

    model_roles: List[Dict[str, str]] = []
    for provider, provider_cfg in api_models.items():
        for role, model_id in provider_cfg.get("roles", {}).items():
            model_roles.append(
                {
                    "ref": f"{MODEL_ROLE_PREFIX}{provider}.{role}",
                    "provider": provider,
                    "role": role,
                    "model_id": model_id,
                    "label": labels_by_id.get(model_id, model_id),
                }
            )

    apex_allowed_providers = [
        provider
        for provider in api_models
        if re.fullmatch(_APEX_PROVIDER_PATTERN, provider)
    ]

    return {
        "model_roles": model_roles,
        "apex_allowed_providers": apex_allowed_providers,
        "typewriter": dict(_TYPEWRITER_BOUNDS),
    }


def _build_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Raw settings + legacy aliases + derived metadata, minus secrets refs."""
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


def _provider_from_ref(ref: str, source: str) -> str:
    """Extract the provider from an '@provider.role' reference or raise 422."""
    if not ref.startswith(MODEL_ROLE_PREFIX) or "." not in ref:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{source}: expected an '@provider.role' reference "
                f"(e.g., '@openai.default'), got '{ref}'"
            ),
        )
    provider, _, _ = ref[len(MODEL_ROLE_PREFIX) :].partition(".")
    return provider


def _updates_from_patch(patch: SettingsPatchRequest) -> Dict[str, Any]:
    """Map the typed patch onto dot-notation save_settings updates."""
    updates: Dict[str, Any] = {}
    if patch.theme is not None:
        updates["ui.theme"] = patch.theme
    if patch.fonts is not None:
        for theme_id, slots in patch.fonts.items():
            for slot in ("body", "menu", "display"):
                value = getattr(slots, slot)
                if value is not None:
                    updates[f"ui.fonts.{theme_id}.{slot}"] = value
    if patch.typewriter_ms_per_char is not None:
        updates["ui.typewriter_ms_per_char"] = patch.typewriter_ms_per_char
    if patch.test_mode is not None:
        updates["global.narrative.test_mode"] = patch.test_mode
    if patch.apex_model_ref is not None:
        updates["apex.model"] = patch.apex_model_ref
        updates["apex.provider"] = _provider_from_ref(
            patch.apex_model_ref, "apex_model_ref"
        )
    if patch.wizard_model_ref is not None:
        # Format check up front; provider/role existence is validated by the
        # Settings model's resolution pass inside save_settings.
        _provider_from_ref(patch.wizard_model_ref, "wizard_model_ref")
        updates["wizard.default_model"] = patch.wizard_model_ref
    if patch.apex_context_window is not None:
        updates["lore.token_budget.apex_context_window"] = patch.apex_context_window
    return updates


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


@router.patch("")
async def patch_settings(patch: SettingsPatchRequest) -> Dict[str, Any]:
    """Persist a safe-subset settings update and return the fresh payload.

    Concurrency posture: save_settings does an unlocked read-merge-write on
    nexus.toml. That is safe for the deployed shape - a single-operator app
    on a single-worker uvicorn process, where the event loop serializes
    handlers. Running this API with multiple workers would reintroduce a
    lost-update race and would need file locking here first.
    """
    updates = _updates_from_patch(patch)
    if not updates:
        raise HTTPException(status_code=400, detail="No supported settings provided")

    try:
        save_settings(updates, path=NEXUS_TOML)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info("Applied settings update: %s", sorted(updates))
    return _build_payload(_read_raw_settings())
