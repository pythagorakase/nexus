"""Enum-typed column comments name only labels their enums have (issue #819).

Migration 136 rewrote six column comments that named labels their enum types
lack, and the faction_member_role type comment whose last sentence #1033 made
false. These tests read ``pg_enum``, ``col_description`` and
``obj_description`` on a migrated disposable clone of NEXUS_template (the
template is read only) and fail when a comment names a label outside its own
enum, so that drift cannot recur silently.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import closing

import pytest

from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres

# The six columns migration 136 corrected.
COLUMNS = (
    ("chunk_character_references", "reference"),
    ("chunk_metadata", "world_layer"),
    ("place_chunk_references", "reference_type"),
    ("places", "type"),
    ("faction_character_relationships", "role"),
    ("faction_relationships", "relationship_type"),
)

# The comments these columns carried before migration 136 (read on
# NEXUS_template on 2026-09-29), kept to prove the check rejects the drift it
# guards against.
PRE_136_COMMENTS = {
    ("chunk_character_references", "reference"): (
        "Type of reference: present (character is in scene), mentioned "
        "(character discussed but not present), implied (indirect reference)"
    ),
    ("chunk_metadata", "world_layer"): "Narrative layer (e.g. primary, secondary)",
    ("place_chunk_references", "reference_type"): (
        "Place presence/reference role written from the chunk roster: "
        "mentioned, transit, setting, or present."
    ),
    ("places", "type"): "Type of location (facility, vehicle, district, etc.)",
    ("faction_character_relationships", "role"): (
        "Character position/function within faction (leader, member, "
        "contractor, etc.)"
    ),
    ("faction_relationships", "relationship_type"): (
        "Nature of relationship (allied, hostile, neutral, trade_partner, etc.)"
    ),
}

# Labels the pre-136 comments named that no enum of the six columns has. The
# catalog cannot list a label that does not exist, so these join the label
# vocabulary explicitly.
RETIRED_LABELS = frozenset(
    {
        "implied",
        "secondary",
        "facility",
        "district",
        "contractor",
        "allied",
        "hostile",
        "neutral",
        "trade_partner",
    }
)

STALE_MEMBERSHIP_SENTENCE = "counts every row as membership whatever its role"

# Exact phrases in the migration 136 comments where "Retrograde" names the
# subsystem, not the world_layer_type label ``retrograde``. Only these phrases
# are exempt; every other occurrence of the word, in any letter case, counts as
# the label.
SUBSYSTEM_PHRASES = (
    "Retrograde prologue",
    "Retrograde persistence",
    "Retrograde maturation",
)

COLUMN_SQL = """
SELECT format_type(a.atttypid, NULL) AS enum_type,
       t.typtype,
       col_description(a.attrelid, a.attnum) AS comment,
       ARRAY(
           SELECT e.enumlabel FROM pg_enum e
           WHERE e.enumtypid = a.atttypid ORDER BY e.enumsortorder
       ) AS labels
FROM pg_attribute a
JOIN pg_type t ON t.oid = a.atttypid
WHERE a.attrelid = to_regclass(%s)
  AND a.attname = %s
  AND NOT a.attisdropped
"""

TYPE_SQL = """
SELECT obj_description(t.oid, 'pg_type') AS comment,
       ARRAY(
           SELECT e.enumlabel FROM pg_enum e
           WHERE e.enumtypid = t.oid ORDER BY e.enumsortorder
       ) AS labels
FROM pg_type t
WHERE t.oid = 'public.faction_member_role'::regtype
"""


def _tokens(comment: str) -> set[str]:
    """Split a comment into case-folded identifier-like words.

    Folding case catches a stale label that comes back capitalized
    ("Secondary"). The subsystem name is dropped only inside the exact phrases
    in ``SUBSYSTEM_PHRASES``, so "Retrograde prologue" does not read as the
    ``world_layer_type`` label ``retrograde`` while a bare "Retrograde" does.
    """
    for phrase in SUBSYSTEM_PHRASES:
        comment = comment.replace(phrase, phrase.split(" ", 1)[1])
    return {word.lower() for word in re.findall(r"[A-Za-z0-9_]+", comment)}


def _read_columns(dbname: str) -> dict[tuple[str, str], dict[str, object]]:
    """Read each column's enum type, labels, and comment from the catalog."""
    rows: dict[tuple[str, str], dict[str, object]] = {}
    with closing(connect(dbname)) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            for table, column in COLUMNS:
                cur.execute(COLUMN_SQL, (f"public.{table}", column))
                found = cur.fetchall()
                assert len(found) == 1, f"public.{table}.{column} is missing"
                enum_type, typtype, comment, labels = found[0]
                assert typtype == "e", f"{table}.{column} is {enum_type}, not an enum"
                rows[(table, column)] = {
                    "enum_type": enum_type,
                    "comment": comment,
                    "labels": frozenset(labels),
                }
    return rows


def _vocabulary(columns: dict[tuple[str, str], dict[str, object]]) -> frozenset[str]:
    """Every label of the six enums, plus the labels only old comments named."""
    labels: set[str] = set(RETIRED_LABELS)
    for row in columns.values():
        labels |= row["labels"]  # type: ignore[arg-type]
    return frozenset(labels)


def _foreign_labels(
    comment: str | None, own: frozenset[str], vocabulary: frozenset[str]
) -> set[str]:
    """Return the vocabulary labels a comment names that its enum lacks."""
    assert comment is not None and comment.strip(), "the comment is missing"
    return _tokens(comment) & (vocabulary - own)


@pytest.fixture(scope="module")
def migrated_clone() -> Iterator[str]:
    """Yield a disposable NEXUS_template clone with every migration applied."""
    with disposable_slot_database("qa640_819_labels") as dbname:
        yield dbname


@pytest.mark.parametrize(
    ("table", "column"), COLUMNS, ids=[f"{t}.{c}" for t, c in COLUMNS]
)
def test_column_comment_names_only_its_enum_labels(
    migrated_clone: str, table: str, column: str
) -> None:
    """A corrected comment names no label its column's enum lacks."""
    columns = _read_columns(migrated_clone)
    row = columns[(table, column)]
    foreign = _foreign_labels(
        row["comment"],  # type: ignore[arg-type]
        row["labels"],  # type: ignore[arg-type]
        _vocabulary(columns),
    )
    assert not foreign, (
        f"{table}.{column} comment names {sorted(foreign)}, which "
        f"{row['enum_type']} does not have: {row['comment']!r}"
    )


@pytest.mark.parametrize(
    ("table", "column"), COLUMNS, ids=[f"{t}.{c}" for t, c in COLUMNS]
)
def test_pre_136_comment_is_rejected(
    migrated_clone: str, table: str, column: str
) -> None:
    """The check flags each comment migration 136 replaced (bite check)."""
    stale = PRE_136_COMMENTS[(table, column)]
    columns = _read_columns(migrated_clone)
    row = columns[(table, column)]
    assert row["comment"] != stale
    assert _foreign_labels(
        stale,
        row["labels"],  # type: ignore[arg-type]
        _vocabulary(columns),
    ), f"the check accepts the pre-136 comment on {table}.{column}"


def test_capitalized_stale_label_is_rejected(migrated_clone: str) -> None:
    """A stale label is flagged even when a comment capitalizes it."""
    columns = _read_columns(migrated_clone)
    row = columns[("chunk_metadata", "world_layer")]
    assert _foreign_labels(
        "Narrative layer (e.g. Primary, Secondary)",
        row["labels"],  # type: ignore[arg-type]
        _vocabulary(columns),
    ) == {"secondary"}


def test_faction_member_role_type_comment_follows_the_membership_rule(
    migrated_clone: str,
) -> None:
    """The type comment drops #1033's false sentence and names only its labels."""
    columns = _read_columns(migrated_clone)
    with closing(connect(migrated_clone)) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(TYPE_SQL)
            comment, labels = cur.fetchone()
    assert comment is not None
    assert STALE_MEMBERSHIP_SENTENCE not in comment
    foreign = _foreign_labels(comment, frozenset(labels), _vocabulary(columns))
    assert not foreign, f"faction_member_role comment names {sorted(foreign)}"


def test_bare_subsystem_word_counts_as_a_label(migrated_clone: str) -> None:
    """Outside its exempt phrases, "Retrograde" is the label ``retrograde``."""
    columns = _read_columns(migrated_clone)
    row = columns[("places", "type")]
    assert _foreign_labels(
        "Type of place: Retrograde.",
        row["labels"],  # type: ignore[arg-type]
        _vocabulary(columns),
    ) == {"retrograde"}

