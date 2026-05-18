"""Shared constants for Orrery tag application.

Used by both the offline slot 2 backfill applicator
(``scripts/apply_slot2_semantic_tags.py``) and the inline Skald tag writer
(``nexus.agents.orrery.tag_writer``). Keeping them here prevents the two call
sites from drifting on which tag categories are valid for which entity kind
and which proposed-name aliases canonicalize to which registered tag.
"""

from __future__ import annotations

from typing import Mapping


ALLOWED_CATEGORIES: Mapping[str, frozenset[str]] = {
    "character": frozenset(
        {
            "bodyform",
            "capacity",
            "disposition",
            "orrery_need_modifier",
            "orrery_signal",
            "orrery_state",
            "profession_lite",
            "role",
            "state",
        }
    ),
    "faction": frozenset(
        {
            "hidden_agenda_class",
            "history_class",
            "ideology_axis",
            "legitimacy_status",
            "operational_secrecy",
            "power_posture",
            "resource_class",
        }
    ),
    "place": frozenset({"place_affordance"}),
}


CANONICAL_TAGS: Mapping[str, str] = {
    "bridge_linked": "bridge_aware",
    "captive_subject": "captive",
    "collapse_survivor": "trauma_survivor",
    "corporate_defector": "corporate_exile",
    "digital_consciousness": "digital_mind",
    "disaster_survivor": "trauma_survivor",
    "echo_survivor": "trauma_survivor",
    "estranged_parent": "parent",
    "ex_corporate": "corporate_exile",
    "found_family_anchor": "extended_household",
    "found_family_member": "extended_household",
    "shadow_broker": "broker",
    "trauma_history": "trauma_survivor",
}
