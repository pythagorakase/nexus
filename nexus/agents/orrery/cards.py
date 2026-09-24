"""Shared rendered card selection and turn-local references."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from nexus.agents.orrery.ambient import AMBIENT_EXPOSURE_TEMPLATE_ID
from nexus.config.settings_models import OrreryPromptSettings


def card_key(card: Mapping[str, Any]) -> str:
    """Return the canonical identity, including the template namespace."""
    return f"{card['template_id']}:{card['binding_hash']}"


def rendered_selection(
    snapshot: Mapping[str, Any], settings: Any = None
) -> list[dict[str, str]]:
    """Replay a frozen selection, or select a legacy/unrendered snapshot once."""
    saved = snapshot.get("rendered_cards")
    if saved is not None:
        return [dict(item) for item in saved]
    policy = (
        settings
        if isinstance(settings, OrreryPromptSettings)
        else OrreryPromptSettings.model_validate(settings or {})
    )
    selected = [
        {"kind": kind, "proposal_id": card_key(card)}
        for kind, cards in (
            (
                "resolution",
                snapshot.get("resolutions", [])[: policy.max_rendered_proposals],
            ),
            (
                "scene_pressure",
                snapshot.get("scene_pressures", [])[: policy.max_rendered_pressures],
            ),
        )
        for card in cards
        if kind != "scene_pressure"
        or card.get("prompt_text")
        or card.get("pressure_stub")
    ]
    selected.extend(
        {
            "kind": "scene_pressure",
            "proposal_id": f"{AMBIENT_EXPOSURE_TEMPLATE_ID}:{seed['dedup_key']}",
        }
        for seed in snapshot.get("ambient_scene_seeds", [])
    )
    selected.extend(
        {"kind": "joint_beat", "proposal_id": beat[direction]}
        for beat in snapshot.get("joint_beats", [])[: policy.max_rendered_proposals]
        for direction in ("forward_proposal_id", "reverse_proposal_id")
    )
    return selected


def proposal_handles(selection: Sequence[Mapping[str, str]]) -> dict[str, str]:
    """Assign the shortest unique hash prefix of at least eight characters."""
    keys = sorted({item["proposal_id"] for item in selection})
    handles = {}
    for key in keys:
        template, fingerprint = key.split(":", 1)
        length = min(8, len(fingerprint))
        while any(
            other != key and other.startswith(f"{template}:{fingerprint[:length]}")
            for other in keys
        ):
            length += 1
            if length > len(fingerprint):
                raise ValueError(f"Cannot assign unique Orrery handle for {key!r}")
        handles[key] = f"{template}:{fingerprint[:length]}"
    return handles


def snapshot_from_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Read the same card inputs at the shared writer/Gaia render boundary."""
    return {
        "resolutions": context.get("orrery_imminent_activity") or [],
        "scene_pressures": context.get("orrery_scene_pressures") or [],
        "ambient_scene_seeds": context.get("orrery_ambient_scene_seeds") or [],
        "joint_beats": context.get("orrery_joint_beats") or [],
        "rendered_cards": context.get("orrery_rendered_cards"),
    }
