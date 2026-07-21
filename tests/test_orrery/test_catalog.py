"""Tests for the Orrery package catalog renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.agents.orrery import templates as template_module
from nexus.agents.orrery.catalog import (
    _collect_vocabulary,
    _render_predicate_name,
    _render_state_delta,
    render_catalog,
)
from nexus.agents.orrery.substrate import DriveBand, drive_band_priority_warnings
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES


def test_catalog_includes_all_templates() -> None:
    """Every built-in template appears in the rendered catalog by id."""

    content = render_catalog(BUILTIN_TEMPLATES)
    for template in BUILTIN_TEMPLATES:
        assert (
            template.id.upper() in content
        ), f"Template {template.id} missing from catalog"
        assert (
            f"priority {template.priority}" in content
        ), f"Template {template.id} priority missing from header"
        assert (
            f"**Drive band:** {template.drive_band.value.replace('_', ' ')}" in content
        ), f"Template {template.id} drive band missing from catalog"


def test_builtin_drive_band_priorities_have_rationales() -> None:
    """Priority inversions across drive bands must be deliberate."""

    assert drive_band_priority_warnings(BUILTIN_TEMPLATES) == ()


def test_catalog_includes_every_branch() -> None:
    """Every branch label appears with its own magnitude on the same line.

    Substring-matching label and magnitude separately would trivially pass
    if two branches share the same magnitude — the second's "mag X.XX"
    would just find the first's line. Asserting the exact header form
    rules that out and pins the formatting too.
    """

    content = render_catalog(BUILTIN_TEMPLATES)
    for template in BUILTIN_TEMPLATES:
        for branch in template.branches:
            expected = f"{branch.label}  *(mag {branch.magnitude})*"
            assert expected in content, (
                f"Expected branch header {expected!r} not found in catalog "
                f"for template {template.id!r}"
            )


def test_catalog_renders_build_venture_completion_vocabulary() -> None:
    """The actor-only venture and its durable founder trace stay discoverable."""

    content = render_catalog(BUILTIN_TEMPLATES)

    assert "## START_BUILD_VENTURE — priority 17" in content
    assert "## ADVANCE_BUILD_VENTURE — priority 47" in content
    assert "actor `build_venture` project passes `completion` due-state" in content
    assert (
        "applies project `complete` transition; adds `proprietor` to actor" in content
    )
    assert "- `proprietor`" in content


def test_catalog_renders_pursue_romance_completion_vocabulary() -> None:
    """Courtship gates and its relationship seal stay discoverable."""

    content = render_catalog(BUILTIN_TEMPLATES)
    assert "## START_PURSUE_ROMANCE — priority 17" in content
    assert "## ADVANCE_PURSUE_ROMANCE — priority 47" in content
    assert "actor `pursue_romance` project passes `completion` due-state" in content
    assert "actor→target `romantic` relationship" in content
    assert "- `contact:intimate`" in content


def test_catalog_renders_court_patron_completion_vocabulary() -> None:
    """Patronage gates and its three-write completion stay discoverable."""

    content = render_catalog(BUILTIN_TEMPLATES)
    assert "## START_COURT_PATRON — priority 17" in content
    assert "## ADVANCE_COURT_PATRON — priority 47" in content
    assert "actor `court_patron` project passes `completion` due-state" in content
    assert "inbound `sponsors` pair tag from target to actor" in content
    assert "actor→target `patron` relationship" in content
    assert "- `obligation`" in content
    assert "- `sponsors`" in content


def test_catalog_renders_compound_structure() -> None:
    """AND / OR / NOT compositions appear as labeled nested bullets."""

    content = render_catalog(BUILTIN_TEMPLATES)
    assert "**AND:**" in content
    assert "**OR:**" in content
    assert "**NOT:**" in content


def test_catalog_renders_every_predicate_to_prose() -> None:
    """Every leaf predicate used by BUILTIN_TEMPLATES has a prose renderer.

    Fails loudly if any predicate __name__ falls through the dispatch
    table — forces additions to _PREDICATE_PARSERS whenever a new
    substrate predicate gets used in a template.
    """

    content = render_catalog(BUILTIN_TEMPLATES)
    assert "*(no prose renderer)*" not in content, (
        "Some predicate names rendered without prose mapping. "
        "Extend _PREDICATE_PARSERS in nexus/agents/orrery/catalog.py "
        "to cover the missing predicate(s)."
    )


def test_catalog_vocabulary_appendix_collects_referenced_terms() -> None:
    """Vocabulary collector finds tags / events / relationships in templates."""

    vocab = _collect_vocabulary(BUILTIN_TEMPLATES)
    # Sanity checks against known-present vocabulary from the templates:
    assert "vendetta_holder" in vocab["durable_tags"]
    assert "grudge_active" in vocab["ephemeral_tags"]
    assert "intelligence_asset_active" in vocab["current_tags"]
    assert "retaliation_executed" in vocab["event_types"]
    assert "dwelling" in vocab["place_classes"]
    assert "wilderness" in vocab["place_classes"]
    assert "home" not in vocab["place_classes"]
    assert "place_affordances" not in vocab
    assert "family" in vocab["relationship_types"]
    assert "handler" in vocab["relationship_types"]


def test_catalog_renders_destination_class_alias() -> None:
    """Catalog prose stays in sync with travel payload aliases accepted at commit."""

    rendered = _render_state_delta(
        {"travel.start": {"destination_class": "commerce", "mode": "mixed"}}
    )

    assert "starts travel toward a `commerce` destination" in rendered


def test_catalog_renders_drive_band_exemption_rationale() -> None:
    """Priority-exempt templates still show the rationale in the catalog."""

    content = render_catalog(BUILTIN_TEMPLATES)

    assert (
        "**Drive band:** crisis constraint — priority-order exempt: "
        "Public-cover upkeep is crisis/constraint-flavored, but it is "
        "intentionally a floor package that should not force routine needs "
        "or story obligations to justify outranking it."
    ) in content


def test_place_class_wrappers_reject_empty_inputs() -> None:
    """Private place-class helpers fail visibly if called without classes."""

    with pytest.raises(ValueError, match="requires at least one place class"):
        template_module._place_any()
    with pytest.raises(ValueError, match="requires at least one place class"):
        template_module._place_all()


def test_render_predicate_name_handles_known_predicates() -> None:
    """Spot-check the prose renderer for a few representative predicate forms."""

    cases = [
        ("ALWAYS", "*(always)*"),
        ("has_tag(vendetta_holder@actor)", "actor has `vendetta_holder` tag"),
        (
            "has_ephemeral(grudge_active@target)",
            "target has `grudge_active` ephemeral",
        ),
        (
            "co_located(actor,target)",
            "actor and target are co-located",
        ),
        (
            "can_move_publicly(@actor)",
            "actor can plausibly move through public flow",
        ),
        (
            "relationship_is_asymmetric(3,actor<->target)",
            "directional trust actor↔target differs by 3+ or is loaded",
        ),
        (
            "has_symmetric_relationship_of_type(family,actor<->target)",
            "actor and target share `family` relationship (either direction)",
        ),
        (
            "has_pair_tag(mentors@actor->target)",
            "actor has `mentors` pair tag to target",
        ),
        (
            "lacks_pair_tag(hunting@target->actor)",
            "target lacks `hunting` pair tag to actor",
        ),
        (
            "has_inbound_pair_tag(hunting@actor)",
            "actor has inbound `hunting` pair tag",
        ),
        (
            "has_routine_anchor(work@actor)",
            "actor has `work` routine anchor",
        ),
        (
            "routine_anchor_due(home@actor)",
            "actor's `home` routine is due now "
            "(weekdays 0=Monday; empty schedule always due)",
        ),
        (
            "away_from_routine_anchor(home@actor)",
            "actor is away from `home` anchor",
        ),
        (
            "routine_anchor_has_destination(home@actor)",
            "actor's `home` routine can resolve a destination",
        ),
        (
            "travel_purpose_is(socialize@actor)",
            "actor is traveling for `socialize` purpose",
        ),
        (
            "travel_purpose_is(socialize,errand@actor)",
            "actor is traveling for `socialize`, `errand` purposes",
        ),
        (
            "has_any_pair_tag(claims,protects@actor->target)",
            "actor has any of [`claims`, `protects`] pair tags to target",
        ),
        (
            "since_last_event_at_least(informant_contact,4@actor,target=target)",
            "≥ 4 ticks since last `informant_contact` event for "
            "(actor, target) pair",
        ),
    ]
    for raw, expected in cases:
        assert _render_predicate_name(raw) == expected, (
            f"Predicate {raw!r} rendered as {_render_predicate_name(raw)!r}, "
            f"expected {expected!r}"
        )


def test_render_predicate_name_falls_back_visibly() -> None:
    """Unknown predicates surface a clear marker so tests can flag the gap."""

    rendered = _render_predicate_name("some_unknown_predicate(args)")
    assert "*(no prose renderer)*" in rendered


def test_render_catalog_accepts_a_generator() -> None:
    """Regression: sorted() consumes the iterable; appendix must reuse the list.

    The renderer signature claims Iterable[Template], which includes
    generators. Earlier versions exhausted the iterable via sorted() then
    passed the empty original to _render_vocabulary_appendix, silently
    producing an empty vocabulary section. Passing the materialized
    sorted list to both phases fixes this.
    """

    def template_generator():
        yield from BUILTIN_TEMPLATES

    content = render_catalog(template_generator())
    # Smoke-check: vocabulary appendix must be populated, not empty.
    assert "## Vocabulary Reference" in content
    assert "vendetta_holder" in content
    assert "grudge_active" in content
    assert "retaliation_executed" in content


def test_pair_tag_predicates_populate_vocabulary_appendix() -> None:
    """Pair-tag predicates render as prose and populate the appendix."""

    from nexus.agents.orrery.substrate import Branch, Slot, Template, has_pair_tag

    template = Template(
        id="pair_tag_catalog_fixture",
        priority=1,
        drive_band=DriveBand.PROJECT_IDENTITY,
        blurb="Catalog fixture.",
        required_slots=(Slot.ACTOR, Slot.TARGET),
        package_gate=has_pair_tag("mentors"),
        branches=(
            Branch("fallback", lambda _state, _bindings: True, "{actor} waits."),
        ),
    )

    content = render_catalog((template,))
    vocab = _collect_vocabulary((template,))

    assert "actor has `mentors` pair tag to target" in content
    assert "Pair tags queried by directed predicates" in content
    assert "mentors" in vocab["pair_tags"]


def test_orrery_packages_md_is_up_to_date() -> None:
    """Generated docs/orrery_packages.md must match a fresh render.

    The catalog file is committed; this test fails any time templates.py
    changes without a corresponding `python -m nexus.agents.orrery.catalog
    --write` run. Keeps the doc in lockstep with the source-of-truth.
    """

    # tests/test_orrery/test_catalog.py → repo_root/docs/orrery_packages.md
    doc_path = Path(__file__).resolve().parents[2] / "docs" / "orrery_packages.md"
    assert doc_path.exists(), (
        f"{doc_path} does not exist. "
        f"Run: python -m nexus.agents.orrery.catalog --write"
    )
    expected = render_catalog(BUILTIN_TEMPLATES)
    actual = doc_path.read_text()
    if actual != expected:
        raise AssertionError(
            f"{doc_path} is stale.\n"
            f"Run: python -m nexus.agents.orrery.catalog --write"
        )
