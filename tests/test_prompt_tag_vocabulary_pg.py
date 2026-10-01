"""The new-story prompt and wizard schema offer only the live tag library (#811).

Bestowal uses the live library only (#811-Q7): a tag the prompt names as an
example, a category the wildcard field description names, and the golden-path
fixture's protagonist tags must all be bestowable on a current template clone.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
import json
from pathlib import Path
import re
from typing import Any

import pytest

from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.agents.orrery.tag_writer import validate_tag_bestowal
from nexus.api.new_story_schemas import WildcardTrait
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres

REPO_ROOT = Path(__file__).resolve().parents[1]
STORYTELLER_NEW_PROMPT = REPO_ROOT / "prompts" / "storyteller_new.md"
GOLDEN_PATH_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "golden_path_wizard_cache.json"
_BACKTICKED = re.compile(r"`([^`\n]+)`")
_DESCRIPTION_CATEGORIES = re.compile(r"Semantic tags for this protagonist \(([^)]*)\)")


@pytest.fixture(scope="module")
def template_clone() -> Iterator[str]:
    """One current-template clone for every vocabulary check in this module."""

    with disposable_slot_database("qa811_prompt_vocab") as dbname:
        yield dbname


def _fetchall(dbname: str, query: str, params: tuple[Any, ...]) -> list[tuple]:
    with closing(connect(dbname)) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        conn.rollback()
    return rows


def _wildcard_description_categories() -> list[str]:
    description = WildcardTrait.model_fields["orrery_tags"].description
    assert description is not None
    match = _DESCRIPTION_CATEGORIES.search(description)
    assert match is not None, description
    names = [name.strip() for name in match.group(1).split(",")]
    return [name for name in names if name and name != "etc."]


def test_prompt_backticked_tags_are_live_tags_in_live_categories(
    template_clone: str,
) -> None:
    """Every backticked token that names a ``tags`` row is bestowable somewhere."""

    tokens = sorted(set(_BACKTICKED.findall(STORYTELLER_NEW_PROMPT.read_text())))
    rows = _fetchall(
        template_clone,
        """
        SELECT
            t.tag,
            t.category,
            t.deprecated,
            t.synonym_for IS NOT NULL AS is_synonym,
            COALESCE(
                array_agg(r.entity_kind::text ORDER BY r.entity_kind::text)
                    FILTER (WHERE NOT r.deprecated),
                ARRAY[]::text[]
            ) AS live_kinds
        FROM tags t
        LEFT JOIN tag_category_registry r ON r.category = t.category
        WHERE t.tag = ANY(%s)
        GROUP BY t.tag, t.category, t.deprecated, t.synonym_for
        ORDER BY t.tag
        """,
        (tokens,),
    )
    not_live = [
        f"{tag} ({category})"
        for tag, category, deprecated, is_synonym, live_kinds in rows
        if deprecated or is_synonym or not live_kinds
    ]
    assert not_live == []
    named_tags = {row[0] for row in rows}
    assert {"first_aid_trained", "haven", "covert"} <= named_tags


def test_wildcard_description_names_only_live_character_categories(
    template_clone: str,
) -> None:
    """Each category the wildcard field names has a live character registry row."""

    categories = _wildcard_description_categories()
    rows = _fetchall(
        template_clone,
        """
        SELECT category
        FROM tag_category_registry
        WHERE entity_kind = 'character'::entity_kind
          AND NOT deprecated
          AND category = ANY(%s)
        """,
        (categories,),
    )
    live = {row[0] for row in rows}
    assert [category for category in categories if category not in live] == []
    assert "role.function" in categories


def test_golden_path_protagonist_tags_validate_on_the_template(
    template_clone: str,
) -> None:
    """The golden-path fixture's protagonist bestowal earns no writer issue."""

    cache = json.loads(GOLDEN_PATH_FIXTURE.read_text())
    bestowal = OrreryTagBestowal.model_validate(
        cache["character_draft"]["wildcard"]["orrery_tags"]
    )
    assert bestowal.applied_tags
    with closing(connect(template_clone)) as conn:
        with conn.cursor() as cur:
            issues = validate_tag_bestowal(
                cur, entity_kind="character", bestowal=bestowal
            )
        conn.rollback()
    assert issues == []
