"""Offline tests for the Orrery audit payload builders.

The slot-backed explained resolver is exercised against real databases in
tests/test_api/test_orrery_dev_endpoints.py; everything here is pure
introspection over the builtin templates and the checked-in nexus.toml —
no mocks, no database.
"""

from __future__ import annotations

import json

from nexus.agents.orrery.audit import (
    NOT_APPLICABLE_REASON,
    build_catalog,
)
from nexus.agents.orrery.substrate import (
    CONSTRAINED_TAGS,
    DRAMATIC_CONTACT_TAGS,
    DRIVE_BAND_ORDER,
    ESTABLISHED_PARTNER_RELATIONSHIP_TYPES,
    HIDDEN_TAGS,
    INTIMACY_SUPPRESSOR_TAGS,
    PUBLIC_MOBILITY_TAGS,
    PUBLIC_PLACE_CLASSES,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.config import load_settings_as_dict


def _catalog() -> dict:
    orrery = load_settings_as_dict()["orrery"]
    return build_catalog(
        BUILTIN_TEMPLATES,
        sunhelm_settings=orrery.get("sunhelm"),
        promote_settings=orrery.get("promote"),
    )


def test_catalog_covers_every_template_exactly_once() -> None:
    catalog = _catalog()

    bands = catalog["drive_bands"]
    assert [band["band"] for band in bands] == [
        band.value
        for band, _ in sorted(DRIVE_BAND_ORDER.items(), key=lambda item: item[1])
    ]
    template_ids = [
        template["template_id"] for band in bands for template in band["templates"]
    ]
    assert sorted(template_ids) == sorted(t.id for t in BUILTIN_TEMPLATES)
    assert len(template_ids) == len(set(template_ids)) == len(BUILTIN_TEMPLATES)


def test_catalog_pseudo_templates_carry_configured_priorities() -> None:
    catalog = _catalog()
    sunhelm = load_settings_as_dict()["orrery"]["sunhelm"]

    pseudo = {item["template_id"]: item for item in catalog["pseudo_templates"]}
    assert set(pseudo) == {f"{need}_need_pressure" for need in sunhelm["priorities"]}
    for need, priority in sunhelm["priorities"].items():
        assert pseudo[f"{need}_need_pressure"]["priority"] == priority
        assert pseudo[f"{need}_need_pressure"]["kind"] == "need_pressure"


def test_catalog_surfaces_priority_ties_in_tuple_order() -> None:
    """Tuple order is the invisible tie-breaker; the catalog must expose it."""

    catalog = _catalog()
    ties = {
        (tie["arity"], tie["priority"]): tie["template_ids"]
        for tie in catalog["priority_ties"]
    }

    assert ties[("two_party", 50)] == ["cultivate_informant", "keep_vigil"]
    assert ties[("actor_only", 25)] == ["mourn_loss", "sleep"]


def test_catalog_flags_exogenous_only_event_types() -> None:
    """The four gate-consumed, never-emitted event types are dead gate arms."""

    catalog = _catalog()
    exogenous = {
        event_type
        for event_type, entry in catalog["event_map"].items()
        if entry["exogenous_only"]
    }

    assert {
        "threat_issued",
        "compliance_alert",
        "faction_realignment",
        "encoded_message",
    } <= exogenous
    for event_type in exogenous:
        assert not catalog["event_map"][event_type]["emitted_by"]


def test_catalog_event_map_includes_genuinely_emitted_types() -> None:
    catalog = _catalog()

    emitted = {
        event_type
        for event_type, entry in catalog["event_map"].items()
        if entry["emitted_by"]
    }
    assert emitted, "builtin templates emit at least some event types"
    for event_type in emitted:
        assert not catalog["event_map"][event_type]["exogenous_only"]


def test_catalog_tag_families_match_substrate() -> None:
    """Family payloads must track the substrate frozensets, not a local copy."""

    catalog = _catalog()

    expected = {
        "intimacy_suppressor_tags": ("tags", INTIMACY_SUPPRESSOR_TAGS),
        "hidden_tags": ("tags", HIDDEN_TAGS),
        "dramatic_contact_tags": ("tags", DRAMATIC_CONTACT_TAGS),
        "constrained_tags": ("tags", CONSTRAINED_TAGS),
        "public_mobility_tags": ("tags", PUBLIC_MOBILITY_TAGS),
        "public_place_classes": ("place_classes", PUBLIC_PLACE_CLASSES),
        "established_partner_relationship_types": (
            "relationship_types",
            ESTABLISHED_PARTNER_RELATIONSHIP_TYPES,
        ),
    }
    assert set(catalog["tag_families"]) == set(expected)
    for name, (kind, members) in expected.items():
        payload = catalog["tag_families"][name]
        assert payload["kind"] == kind
        assert payload["members"] == sorted(members)
    # DRAMATIC_CONTACT_TAGS is composed from HIDDEN_TAGS; keep that visible.
    assert set(catalog["tag_families"]["dramatic_contact_tags"]["members"]) > set(
        catalog["tag_families"]["hidden_tags"]["members"]
    )


def test_catalog_promotion_thresholds_come_from_config() -> None:
    catalog = _catalog()
    promote = load_settings_as_dict()["orrery"]["promote"]

    assert catalog["promotion"] == {
        "priority_threshold": promote["priority_threshold"],
        "magnitude_threshold": promote["magnitude_threshold"],
    }


def test_catalog_is_json_serializable() -> None:
    payload = json.loads(json.dumps(_catalog()))
    assert payload["drive_bands"]


def test_not_applicable_reason_is_stable() -> None:
    """The UI keys ghost-row styling off this marker; treat it as contract."""

    assert NOT_APPLICABLE_REASON == "no_target_bound"
