"""Explicitly allowlisted display configuration for the player client."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from nexus.config import load_settings
from nexus.config.settings_models import UIAnnouncerSettings

router = APIRouter(prefix="/api/config", tags=["ui-config"])


class UIConfigResponse(BaseModel):
    """Each field is an allowlisted display tunable; add new tunables here by name."""

    model_config = ConfigDict(extra="forbid")

    announcer: UIAnnouncerSettings


@router.get("/ui")
def get_ui_config() -> UIConfigResponse:
    """Return only the player client's explicitly named display tunables."""
    return UIConfigResponse(announcer=load_settings().ui.announcer)
