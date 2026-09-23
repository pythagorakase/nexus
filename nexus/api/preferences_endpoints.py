"""HTTP read/write surface for player-owned preferences."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from nexus.config.preferences import load_preferences, save_preferences
from nexus.config.settings_models import PreferencesSettings

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


class FontSlotsPatch(BaseModel):
    """A partial font selection for one theme."""

    model_config = ConfigDict(extra="forbid")
    body: str | None = None
    menu: str | None = None
    display: str | None = None


class PreferencesPatch(BaseModel):
    """The player-owned keys accepted by the preferences API."""

    model_config = ConfigDict(extra="forbid")
    theme: Literal["veil", "gilded", "vector"] | None = None
    fonts: dict[Literal["veil", "gilded", "vector"], FontSlotsPatch] | None = None
    wizard_model: str | None = Field(default=None, min_length=1)


@router.get("")
def get_preferences() -> PreferencesSettings:
    """Return persisted player values, or defaults before the first write."""
    return load_preferences()


@router.patch("")
def patch_preferences(patch: PreferencesPatch) -> PreferencesSettings:
    """Persist preferences without changing nexus.toml."""
    updates = patch.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No preferences provided")
    try:
        return save_preferences(updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
