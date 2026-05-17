"""Tests for the Orrery package catalog renderer."""

from __future__ import annotations

from pathlib import Path

from nexus.agents.orrery.catalog import (
    _collect_vocabulary,
    _render_predicate_name,
    render_catalog,
)
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
    assert "retaliation_executed" in vocab["event_types"]
    assert "family" in vocab["relationship_types"]
    assert "handler" in vocab["relationship_types"]


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
            "has_symmetric_relationship_of_type(family,actor<->target)",
            "actor and target share `family` relationship (either direction)",
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
