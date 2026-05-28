"""Shared aliases for Orrery tag application.

Category/entity-kind compatibility lives in the database table
``tag_category_registry``. This module only keeps proposed-name aliases that
canonicalize to existing registered tags.
"""

from __future__ import annotations

from typing import Mapping


CANONICAL_TAGS: Mapping[str, str] = {
    "bereaved": "grieving",
    "bodyform:android": "inorganic",
    "bodyform:construct": "inorganic",
    "bodyform:non_corporeal": "virtual",
    "bodyform:undead": "undead",
    "bridge_linked": "bridge_aware",
    "captive_subject": "captive",
    "collapse_survivor": "trauma_survivor",
    "corporate_defector": "corporate_exile",
    "digital_consciousness": "virtual",
    "digital_mind": "virtual",
    "disaster_survivor": "trauma_survivor",
    "echo_survivor": "trauma_survivor",
    "estranged_parent": "parent",
    "ex_corporate": "corporate_exile",
    "found_family_anchor": "extended_household",
    "found_family_member": "extended_household",
    "grieving_recent_partner": "grieving",
    "shadow_broker": "broker",
    "trauma_history": "trauma_survivor",
}
