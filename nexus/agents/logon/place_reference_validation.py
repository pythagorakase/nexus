"""Validate writer-owned places while Gaia can still declare new entities."""

from __future__ import annotations

from typing import Any, Iterable

from pydantic_ai import ModelRetry

from nexus.agents.logon.skald_wire import PlaceRef, PresenceDelta, PresenceRef
from nexus.api.native_structured_output import WireContractViolation
from nexus.presence.roster import resolve_place_update
from nexus.prompts.registry import PromptId, load


def place_reference_sites(
    presence: PresenceDelta | None,
) -> Iterable[tuple[str, PlaceRef | PresenceRef]]:
    """Yield every explicit place that hydration carries into references."""
    if presence is None:
        return
    if presence.scene_reset is not None:
        yield "presence.scene_reset.place", presence.scene_reset.place
    for index, reference in enumerate(presence.transit):
        yield f"presence.transit[{index}]", reference
    for index, reference in enumerate(presence.mentions):
        if reference.kind == "place":
            yield f"presence.mentions[{index}]", reference


def validate_place_references(
    presence: PresenceDelta | None,
    declarations: Iterable[Any],
    cur: Any,
    *,
    allow_declarations: bool,
) -> None:
    """Require existing identities or enabled, exact same-turn declarations.

    The finished writer output is immutable. Gaia can repair a missing
    declaration, but cannot repair a fabricated ID or ambiguous writer name.
    Reuse staging's resolver, including its authoritative-ID and alias rules.
    """
    pending = frozenset(
        declaration.name
        for declaration in declarations
        if declaration.kind == "place" and allow_declarations
    )
    missing = []
    for path, reference in place_reference_sites(presence):
        try:
            resolve_place_update(
                cur,
                identifier=reference.id,
                name=reference.name,
                pending_names=pending,
            )
        except WireContractViolation as exc:
            if reference.id is not None or not allow_declarations:
                raise WireContractViolation(f"{path}: {exc}") from exc
            missing.append(f"- {path}: {reference.name!r}")
        except ValueError as exc:
            raise WireContractViolation(f"{path}: {exc}") from exc
    if missing:
        raise ModelRetry(
            load(PromptId.RETRY_PLACE_REFERENCES, FORMATTED="\n".join(missing))
        )
