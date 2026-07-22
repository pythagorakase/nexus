"""Shared prompt and structured call for place-coordinate authoring."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

from nexus.agents.logon.apex_schema import Coordinates


_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "orrery" / "geo_authoring.md"
)


class GeoAuthoringResponse(BaseModel):
    """Structured coordinate proposal shared by maturation and backfill."""

    coordinates: Coordinates = Field(
        description="Plausible real-Earth coordinates for the physical place."
    )

    model_config = ConfigDict(extra="forbid")


def render_geo_authoring_prompt(
    *,
    place_name: str,
    place_summary: Optional[str],
    zone_name: str,
    zone_summary: Optional[str],
) -> str:
    """Render the single prompt shape used by maturation and backfill."""

    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    replacements = {
        "{{PLACE_NAME}}": place_name,
        "{{PLACE_SUMMARY}}": place_summary or "(no summary supplied)",
        "{{ZONE_NAME}}": zone_name,
        "{{ZONE_SUMMARY}}": zone_summary or "(no zone summary supplied)",
    }
    for marker, value in replacements.items():
        prompt = prompt.replace(marker, value)
    return prompt.strip()


def geo_prompt_from_context(context: Mapping[str, Any]) -> Optional[str]:
    """Render a prompt when a maturation packet carries place GIS context."""

    geo = context.get("geo_authoring")
    if not isinstance(geo, Mapping) or not geo.get("required"):
        return None
    return render_geo_authoring_prompt(
        place_name=str(geo["place_name"]),
        place_summary=geo.get("place_summary"),
        zone_name=str(geo["zone_name"]),
        zone_summary=geo.get("zone_summary"),
    )


def author_place_coordinates(
    *,
    model: str,
    max_tokens: int,
    place_name: str,
    place_summary: Optional[str],
    zone_name: str,
    zone_summary: Optional[str],
) -> GeoAuthoringResponse:
    """Call the configured native structured-output provider once."""

    from nexus.api.config_utils import get_wizard_retry_budget
    from nexus.api.native_structured_output import build_native_structured_provider

    prompt = render_geo_authoring_prompt(
        place_name=place_name,
        place_summary=place_summary,
        zone_name=zone_name,
        zone_summary=zone_summary,
    )
    provider = build_native_structured_provider(
        model=model,
        max_tokens=max_tokens,
        system_prompt=prompt,
        structured_output_retries=get_wizard_retry_budget(),
    )
    response, _llm_response = provider.get_structured_completion(
        prompt,
        GeoAuthoringResponse,
    )
    if not isinstance(response, GeoAuthoringResponse):
        raise TypeError(
            "GIS authoring returned "
            f"{type(response).__name__}, expected GeoAuthoringResponse"
        )
    return response
