"""Incubator column comments follow the code that writes them (issue #1106).

Migration 152 rewrote the incubator comments the code at c7ae2988 proves false
and the comment on ``public.clear_incubator()``. These tests read
``col_description`` and ``obj_description`` on a migrated disposable clone of
NEXUS_template (the template is read only). Each JSON-column comment names its
top-level keys once as ``keys: {a, b, c}`` and a nested object's keys as
``<field>.keys: {a, b}``; the tests require those sets to equal the fields of
the Pydantic model the writers and readers validate against, so a model change
that the comment does not follow fails here.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import closing

import pytest
from pydantic import BaseModel

from nexus.agents.logon.apex_schema import (
    ChronologyUpdate,
    ChunkMetadataUpdate,
    ReferencedEntities,
    StateUpdates,
)
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres

# Column -> (model of the whole value, {nested field: model of that field}).
GUARDED: dict[str, tuple[type[BaseModel], dict[str, type[BaseModel]]]] = {
    "metadata_updates": (ChunkMetadataUpdate, {"chronology": ChronologyUpdate}),
    "entity_updates": (StateUpdates, {}),
    "reference_updates": (ReferencedEntities, {}),
}

FUNCTION = "clear_incubator()"

# The comments these objects carried before migration 152 (read on
# NEXUS_template on 2026-10-26), kept to prove the checks reject them.
PRE_152: dict[str, str] = {
    "metadata_updates": (
        "JSON: {episode_transition, time_delta_seconds, time_delta_description, "
        "world_layer, pacing}"
    ),
    "entity_updates": (
        "JSON array of entity state changes: "
        "[{type, id, field, old_value, new_value}]"
    ),
    "reference_updates": (
        "JSON: {character_present: [], character_referenced: [], "
        "place_referenced: []}"
    ),
    "status": (
        "Status: provisional (pending approval), approved (ready to commit), "
        "committed (written to main tables)"
    ),
    "llm_response_id": "OpenAI or LM Studio response ID for debugging",
    "authorial_directives": (
        "Provisional Storyteller-authored retrieval directives to persist when "
        "accepted."
    ),
    "orrery_proposal": (
        "No-write OrreryTickProposal generated during preview; stamped into "
        "canonical Orrery tables only when the incubator chunk is accepted."
    ),
    "parent_chunk_id": "ID of existing chunk being continued from",
    "choice_object": (
        "Structured choice data: {presented: string[], selected: "
        "{label, text, edited}}"
    ),
    "generation_model": (
        "The registry model id that produced the accepted storyteller text; "
        "NULL for pre-082 history and rows not produced by the storyteller "
        "pipeline."
    ),
    FUNCTION: "Clear the incubator after content is approved and committed",
}

# The old key lists of the three JSON columns, written in the convention, and
# the (extra, missing) differences each must produce against its model.
PRE_152_IN_CONVENTION: dict[str, tuple[str, set[str], set[str]]] = {
    "metadata_updates": (
        "keys: {episode_transition, time_delta_seconds, time_delta_description, "
        "world_layer, pacing}",
        {
            "episode_transition",
            "pacing",
            "time_delta_description",
            "time_delta_seconds",
        },
        {"chronology", "scene_boundary", "scene_weather"},
    ),
    "entity_updates": (
        "keys: {type, id, field, old_value, new_value}",
        {"type", "id", "field", "old_value", "new_value"},
        {"characters", "factions", "locations", "relationships"},
    ),
    "reference_updates": (
        "keys: {character_present, character_referenced, place_referenced}",
        {"character_present", "character_referenced", "place_referenced"},
        {"characters", "departures", "factions", "places"},
    ),
}

RETIRED = frozenset(
    {
        "pacing",
        "time_delta_seconds",
        "character_present",
        "character_referenced",
        "place_referenced",
        "approved",
        "committed",
    }
)

KEY_SET = re.compile(r"(?:\b(\w+)\.)?keys: \{([^{}]*)\}")

COLUMN_SQL = """
SELECT a.attname, col_description(a.attrelid, a.attnum)
FROM pg_attribute a
WHERE a.attrelid = 'public.incubator'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
"""

FUNCTION_SQL = """
SELECT obj_description('public.clear_incubator()'::regprocedure, 'pg_proc')
"""


def _key_sets(comment: str) -> dict[str | None, set[str]]:
    """Map each ``keys: {...}`` prefix (None for top level) to its key names."""
    sets: dict[str | None, set[str]] = {}
    for match in KEY_SET.finditer(comment):
        prefix = match.group(1)
        assert prefix not in sets, f"key set {prefix!r} is repeated in {comment!r}"
        names = [name.strip() for name in match.group(2).split(",")]
        assert all(names), f"key set {prefix!r} has an empty name in {comment!r}"
        sets[prefix] = set(names)
    return sets


def _model_mismatches(
    comment: str,
    model: type[BaseModel],
    nested: dict[str, type[BaseModel]],
) -> list[str]:
    """Describe every way the comment's key sets differ from the models."""
    sets = _key_sets(comment)
    expected_prefixes: set[str | None] = {None, *nested}
    problems: list[str] = []
    if set(sets) != expected_prefixes:
        problems.append(
            f"key-set prefixes {sorted(sets, key=str)} != "
            f"{sorted(expected_prefixes, key=str)}"
        )
    for prefix, owner in [(None, model), *nested.items()]:
        if prefix not in sets:
            continue
        fields = set(owner.model_fields)
        extra = sets[prefix] - fields
        missing = fields - sets[prefix]
        if extra or missing:
            problems.append(
                f"{prefix or 'top level'} ({owner.__name__}): extra "
                f"{sorted(extra)}, missing {sorted(missing)}"
            )
    return problems


def _words(comment: str) -> set[str]:
    """Split a comment into case-folded identifier-like words."""
    return {word.casefold() for word in re.findall(r"[A-Za-z0-9_]+", comment)}


@pytest.fixture(scope="module")
def migrated_clone() -> Iterator[str]:
    """Yield a disposable NEXUS_template clone with every migration applied."""
    with disposable_slot_database("qa640_1106_comments") as dbname:
        yield dbname


@pytest.fixture(scope="module")
def live_comments(migrated_clone: str) -> dict[str, str | None]:
    """Read every incubator column comment and the function comment."""
    with closing(connect(migrated_clone)) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(COLUMN_SQL)
            comments: dict[str, str | None] = dict(cur.fetchall())
            cur.execute(FUNCTION_SQL)
            comments[FUNCTION] = cur.fetchone()[0]
    return comments


@pytest.mark.parametrize("column", sorted(GUARDED))
def test_json_column_comment_lists_its_model_keys(
    live_comments: dict[str, str | None], column: str
) -> None:
    """A JSON-column comment names exactly its model's fields."""
    comment = live_comments[column]
    assert comment is not None and comment.strip(), f"{column} comment is blank"
    model, nested = GUARDED[column]
    problems = _model_mismatches(comment, model, nested)
    assert not problems, f"incubator.{column}: {'; '.join(problems)}"


@pytest.mark.parametrize("column", sorted(GUARDED))
def test_pre_152_comment_is_rejected(column: str) -> None:
    """Free prose without the convention yields no top-level key set."""
    model, nested = GUARDED[column]
    assert None not in _key_sets(PRE_152[column])
    assert _model_mismatches(PRE_152[column], model, nested)


@pytest.mark.parametrize("column", sorted(PRE_152_IN_CONVENTION))
def test_pre_152_keys_in_convention_are_rejected(column: str) -> None:
    """The old key lists, in the convention, differ from the models exactly."""
    text, extra, missing = PRE_152_IN_CONVENTION[column]
    model, _ = GUARDED[column]
    sets = _key_sets(text)
    assert set(sets) == {None}
    fields = set(model.model_fields)
    assert sets[None] - fields == extra
    assert fields - sets[None] == missing
    assert _model_mismatches(text, model, {}) == [
        f"top level ({model.__name__}): extra {sorted(extra)}, "
        f"missing {sorted(missing)}"
    ]


def test_corrected_comments_drop_retired_tokens(
    live_comments: dict[str, str | None],
) -> None:
    """No corrected comment names a retired key or status value."""
    for name in (
        "metadata_updates",
        "entity_updates",
        "reference_updates",
        "status",
        FUNCTION,
    ):
        comment = live_comments[name]
        assert comment is not None
        shared = _words(comment) & RETIRED
        assert not shared, f"{name} comment still names {sorted(shared)}"
    for name in ("metadata_updates", "reference_updates", "status", FUNCTION):
        assert _words(PRE_152[name]) & RETIRED, f"{name}: the check does not bite"


@pytest.mark.parametrize("name", sorted(PRE_152))
def test_every_corrected_comment_replaced_its_pre_152_text(
    live_comments: dict[str, str | None], name: str
) -> None:
    """Migration 152 replaced the comment on every object it names."""
    comment = live_comments[name]
    assert comment is not None and comment.strip(), f"{name} comment is blank"
    assert comment != PRE_152[name], f"{name} still carries its pre-152 comment"
