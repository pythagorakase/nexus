"""Load-time vocabulary for canonical Orrery world-event types."""

from __future__ import annotations

from functools import lru_cache


NON_TEMPLATE_EVENT_TYPES = frozenset(
    {
        "backstory_revealed",
        "backstory_secret_authored",
        "captivity_ended",
        "circumstance_reversed",
        "claim_propagated",
        "confrontation_resolved",
        "cured",
        "death_recorded",
        "discovered",
        "escaped",
        "exposed",
        "faction_realignment",
        "recovered_from_illness",
        "regained_consciousness",
        "relationship_drift_drained",
        "relationship_drift_milestone",
        "revealed",
        "threat_removed",
        "unmasked",
    }
)


@lru_cache(maxsize=1)
def known_event_types() -> frozenset[str]:
    """Return the active event vocabulary available during config loading."""

    from nexus.agents.orrery.templates import BUILTIN_TEMPLATES

    event_types = set(NON_TEMPLATE_EVENT_TYPES)
    for template in BUILTIN_TEMPLATES:
        for branch in template.branches:
            event_types.add(branch.event_type)
            if branch.signal_event_type is not None:
                event_types.add(branch.signal_event_type)
    return frozenset(event_types)
