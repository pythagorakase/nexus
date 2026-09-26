"""Offline COMMENT ON coverage lint for new migrations (issue #819)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_migration_comments import (
    REPO_ROOT,
    WATERMARK,
    check_file,
    check_migrations,
)

CHECKER = REPO_ROOT / "scripts/check_migration_comments.py"
NEXT = f"{WATERMARK + 1:03d}"


def _migration(directory: Path, name: str, source: str) -> Path:
    path = directory / name
    path.write_text(source.lstrip("\n"), encoding="utf-8")
    return path


def _findings(directory: Path) -> list[str]:
    return [finding.render(directory) for finding in check_migrations(directory)]


def test_fully_commented_migration_passes(tmp_path: Path) -> None:
    """Every object kind, documented in the same file, satisfies the lint."""
    _migration(
        tmp_path,
        f"{NEXT}_scene_moods.sql",
        r"""
-- CREATE TABLE ghost (id int); inside a line comment is not DDL.
/* Nested /* block */ comments: CREATE TYPE ghost AS ENUM ('x'); */
CREATE TYPE mood AS ENUM ('calm', 'tense');
COMMENT ON TYPE mood IS 'Scene tension; CREATE TABLE decoy (x int) is only text.';

CREATE TABLE IF NOT EXISTS scene_moods (
    id bigserial PRIMARY KEY,
    chunk_id bigint NOT NULL REFERENCES narrative_chunks(id) ON DELETE CASCADE,
    mood mood NOT NULL DEFAULT 'calm',
    weight numeric(5, 2) CHECK (weight >= 0),
    CONSTRAINT scene_moods_chunk_unique UNIQUE (chunk_id, mood),
    UNIQUE (id, weight),
    CHECK (weight < 100),
    FOREIGN KEY (chunk_id) REFERENCES narrative_chunks(id)
);
COMMENT ON TABLE scene_moods IS 'Moods accepted per narrative chunk.';
COMMENT ON COLUMN scene_moods.id IS 'Row key.';
COMMENT ON COLUMN scene_moods.chunk_id IS 'Accepted chunk carrying the mood.';
COMMENT ON COLUMN scene_moods.mood IS E'It\'s the -- literal; mood.';
COMMENT ON COLUMN public.scene_moods.weight IS 'Relative weight, 0 to 100.';

ALTER TABLE assets.new_story_creator
    ADD COLUMN mood_confirmed boolean NOT NULL DEFAULT false,
    ADD CONSTRAINT mood_confirmed_check CHECK (mood_confirmed IS NOT NULL),
    ADD COLUMN IF NOT EXISTS mood_note text;
COMMENT ON COLUMN assets.new_story_creator.mood_confirmed IS 'Player accepted.';
COMMENT ON COLUMN assets.new_story_creator.mood_note IS $$Free-text note.$$;

CREATE OR REPLACE FUNCTION mood_weight(
    p_mood mood, p_scale numeric DEFAULT 1, OUT weight numeric
) LANGUAGE plpgsql AS $body$
BEGIN
    CREATE TEMP TABLE scratch (x int);
    weight := p_scale;
END;
$body$;
COMMENT ON FUNCTION mood_weight(mood, numeric) IS 'Weight of one mood.';

CREATE VIEW mood_view AS SELECT id, mood FROM scene_moods;
COMMENT ON VIEW mood_view IS 'Current moods.';
CREATE MATERIALIZED VIEW IF NOT EXISTS mood_totals AS
    SELECT mood, count(*) AS total FROM scene_moods GROUP BY mood;
COMMENT ON MATERIALIZED VIEW mood_totals IS 'Mood counts.';

CREATE TEMP TABLE migration_scratch (id int);
""",
    )

    assert _findings(tmp_path) == []


def test_missing_column_comment_fails_with_its_location(tmp_path: Path) -> None:
    """Both table-body and ALTER TABLE columns need their own comment."""
    _migration(
        tmp_path,
        f"{NEXT}_notes.sql",
        """
CREATE TABLE notes (
    id bigint PRIMARY KEY,
    body text NOT NULL
);
COMMENT ON TABLE notes IS 'Author notes.';
COMMENT ON COLUMN notes.id IS 'Row key.';
ALTER TABLE notes ADD COLUMN pinned boolean, ADD COLUMN author text;
COMMENT ON COLUMN notes.author IS 'Author name.';
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_notes.sql:3: column public.notes.body has no COMMENT ON COLUMN",
        f"{NEXT}_notes.sql:7: column public.notes.pinned has no COMMENT ON COLUMN",
    ]


def test_real_migration_as_next_number_passes_until_a_comment_is_removed(
    tmp_path: Path,
) -> None:
    """Migration 129's actual SQL passes; dropping one COMMENT names that column."""
    source = (REPO_ROOT / "migrations/129_wizard_confirmation.sql").read_text()
    path = _migration(tmp_path, f"{NEXT}_wizard_confirmation.sql", source)
    assert _findings(tmp_path) == []

    start = source.index(
        "COMMENT ON COLUMN assets.new_story_creator.character_revision_pending"
    )
    end = source.index("';", start) + 2
    path.write_text(source[:start] + source[end:], encoding="utf-8")

    assert _findings(tmp_path) == [
        f"{NEXT}_wizard_confirmation.sql:6: column "
        "assets.new_story_creator.character_revision_pending has no COMMENT ON "
        "COLUMN",
    ]


@pytest.mark.parametrize(
    "ddl, expected",
    [
        (
            "CREATE TYPE mood AS ENUM ('calm', 'tense');",
            "enum public.mood has no COMMENT ON TYPE",
        ),
        (
            "CREATE OR REPLACE FUNCTION touch_row() RETURNS trigger\n"
            "LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;",
            "function public.touch_row (0 arguments) has no COMMENT ON FUNCTION",
        ),
        (
            "CREATE OR REPLACE VIEW assets.mood_view AS SELECT 1 AS one;",
            "view assets.mood_view has no COMMENT ON VIEW",
        ),
        (
            "CREATE MATERIALIZED VIEW mood_totals AS SELECT 1 AS one;",
            "materialized view public.mood_totals has no COMMENT ON MATERIALIZED VIEW",
        ),
        (
            "CREATE TABLE ledger ();",
            "table public.ledger has no COMMENT ON TABLE",
        ),
    ],
    ids=["enum", "function", "view", "materialized-view", "table"],
)
def test_missing_object_comment_fails(tmp_path: Path, ddl: str, expected: str) -> None:
    """Enums, functions, views, and tables each need their own COMMENT ON."""
    _migration(tmp_path, f"{NEXT}_object.sql", f"-- {expected}\n{ddl}\n")

    assert _findings(tmp_path) == [f"{NEXT}_object.sql:2: {expected}"]


def test_migrations_at_or_below_the_watermark_are_ignored(tmp_path: Path) -> None:
    """Legacy debt belongs to the PostgreSQL ratchet, not the commit lint."""
    legacy = _migration(
        tmp_path, f"{WATERMARK:03d}_legacy.sql", "CREATE TABLE legacy (id int);\n"
    )
    _migration(tmp_path, f"{NEXT}_new.sql", "CREATE TABLE fresh (id int);\n")

    assert len(check_file(legacy)) == 2
    assert _findings(tmp_path) == [
        f"{NEXT}_new.sql:1: column public.fresh.id has no COMMENT ON COLUMN",
        f"{NEXT}_new.sql:1: table public.fresh has no COMMENT ON TABLE",
    ]


def test_quoted_and_schema_qualified_names_match(tmp_path: Path) -> None:
    """Qualification defaults to public; only unquoted identifiers fold case."""
    _migration(
        tmp_path,
        f"{NEXT}_names.sql",
        """
CREATE TABLE assets."Scene Notes" ("Author" text, Body text, "check" int);
COMMENT ON TABLE assets."Scene Notes" IS 'Notes.';
COMMENT ON COLUMN assets."Scene Notes"."Author" IS 'Exact quoted spelling.';
COMMENT ON COLUMN assets . "Scene Notes".BODY IS 'Unquoted names fold.';
COMMENT ON COLUMN assets."Scene Notes"."check" IS 'Quoted keyword column.';
CREATE TABLE Public.Ledger (ID int);
COMMENT ON TABLE ledger IS 'Unqualified means public.';
COMMENT ON COLUMN public.LEDGER.id IS 'Case folds.';
CREATE TYPE "Mood" AS ENUM ('a');
COMMENT ON TYPE public."Mood" IS 'Quoted enum.';
""",
    )
    _migration(
        tmp_path,
        f"{WATERMARK + 2:03d}_mismatch.sql",
        """
CREATE TABLE assets.ledger (id int);
COMMENT ON TABLE ledger IS 'Documents public.ledger, not assets.ledger.';
COMMENT ON COLUMN assets.ledger.id IS 'Row key.';
CREATE TABLE "Mixed" (id int);
COMMENT ON TABLE mixed IS 'Unquoted mixed folds to another name.';
COMMENT ON COLUMN "Mixed".id IS 'Row key.';
""",
    )

    assert _findings(tmp_path) == [
        f"{WATERMARK + 2:03d}_mismatch.sql:1: "
        "table assets.ledger has no COMMENT ON TABLE",
        f'{WATERMARK + 2:03d}_mismatch.sql:4: table public."Mixed" has no '
        "COMMENT ON TABLE",
    ]


def test_do_blocks_and_execute_strings_are_scanned(tmp_path: Path) -> None:
    """DDL run by a DO block or a literal EXECUTE creates real objects."""
    _migration(
        tmp_path,
        f"{NEXT}_guarded.sql",
        """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'mood') THEN
        CREATE TYPE mood AS ENUM ('calm');
    END IF;
    EXECUTE 'ALTER TABLE scene ADD COLUMN mood_note text DEFAULT ''none''';
    EXECUTE format('ALTER TABLE %I ADD COLUMN mood text', 'scene');
END
$$;
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_guarded.sql:4: enum public.mood has no COMMENT ON TYPE",
        f"{NEXT}_guarded.sql:6: column public.scene.mood_note has no COMMENT ON "
        "COLUMN",
        f"{NEXT}_guarded.sql:7: ALTER TABLE names '%I', which is not a literal "
        "identifier; name the object literally so its COMMENT can be verified",
    ]


def test_python_migration_literals_are_checked(tmp_path: Path) -> None:
    """SQL strings count; docstrings do not; run-time names fail loudly."""
    _migration(
        tmp_path,
        f"{NEXT}_seat_notes.py",
        '''
"""Docstrings may say CREATE TABLE ghost (id int) without creating it."""

from psycopg2 import sql

DDL = """
CREATE TABLE seat_notes (id bigint, note text);
COMMENT ON TABLE seat_notes IS 'Seat notes.';
COMMENT ON COLUMN seat_notes.id IS 'Row key.';
"""


def run(conn) -> None:
    """Apply the DDL and a dynamically named column."""
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN pinned boolean").format(
                sql.Identifier("seat_notes")
            )
        )
        cur.execute(f"CREATE VIEW seat_view_{conn.info.dbname} AS SELECT 1")
''',
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_seat_notes.py:6: column public.seat_notes.note has no COMMENT ON "
        "COLUMN",
        f"{NEXT}_seat_notes.py:17: ALTER TABLE names '{{}}', which is not a "
        "literal identifier; name the object literally so its COMMENT can be "
        "verified",
        f"{NEXT}_seat_notes.py:21: CREATE VIEW names 'seat_view_{{}}', which is "
        "not a literal identifier; name the object literally so its COMMENT can "
        "be verified",
    ]


def test_concatenated_execute_commands_are_joined_or_fail(tmp_path: Path) -> None:
    """EXECUTE joins ``||`` operands; run-time names, actions, and verbs fail."""
    _migration(
        tmp_path,
        f"{NEXT}_dynamic.sql",
        """
DO $$
DECLARE
    ddl text := 'CREATE TABLE foo (id int)';
BEGIN
    EXECUTE 'ALTER TABLE ' || 'scene' || ' ADD COLUMN joined int';
    EXECUTE 'ALTER TABLE ' || quote_ident(t) || ' ADD COLUMN x int';
    EXECUTE 'ALTER TABLE scene ' || v_action;
    EXECUTE ddl;
    EXECUTE format('%s ADD COLUMN z int', v_prefix);
    EXECUTE 'ALTER TABLE scene'
        ' ADD COLUMN documented int';
    EXECUTE 'UPDATE ' || quote_ident(t) || ' SET x = 1';
    EXECUTE format(
        'DELETE FROM scene '
        'WHERE id = %L', 1);
    FOR r IN EXECUTE 'SELECT 1' LOOP NULL; END LOOP;
END
$$;
COMMENT ON COLUMN scene.documented IS 'Joined from adjacent literals.';
GRANT EXECUTE  ON FUNCTION touch_row() TO PUBLIC;
CREATE TRIGGER scene_touch BEFORE UPDATE ON scene
    FOR EACH ROW EXECUTE
    FUNCTION touch_row();
""",
    )

    run_time = "its schema changes cannot be verified"
    assert _findings(tmp_path) == [
        f"{NEXT}_dynamic.sql:5: column public.scene.joined has no COMMENT ON COLUMN",
        f"{NEXT}_dynamic.sql:6: ALTER TABLE names '{{}}', which is not a literal "
        "identifier; name the object literally so its COMMENT can be verified",
        f"{NEXT}_dynamic.sql:7: ALTER TABLE public.scene action '{{}}' is filled in "
        "at run time; its changes cannot be verified",
        f"{NEXT}_dynamic.sql:8: EXECUTE 'ddl' runs a command built at run time; "
        f"{run_time}",
        f"{NEXT}_dynamic.sql:9: statement begins with '%s', which is filled in at "
        f"run time; {run_time}",
    ]


def test_python_concatenated_ddl_fails_instead_of_passing(tmp_path: Path) -> None:
    """A Python ``+`` or f-string cannot hide an ALTER TABLE target or action."""
    _migration(
        tmp_path,
        f"{NEXT}_seat_pins.py",
        """
PREFIX = "ALTER TABLE seat_notes"
ADD = " ADD COLUMN pinned boolean"


def run(cur, prefix, action) -> None:
    cur.execute("ALTER TABLE seat_notes" + ADD)
    cur.execute(PREFIX + ADD)
    cur.execute(f"{prefix} ADD COLUMN note text")
    cur.execute("ALTER TABLE seat_notes %s" % action)
    cur.execute("ALTER TABLE seat_notes ALTER COLUMN id SET DEFAULT %s", (0,))
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_seat_pins.py:1: ALTER TABLE public.seat_notes names no action, so "
        "it is a fragment of a command assembled at run time; its changes cannot "
        "be verified",
        f"{NEXT}_seat_pins.py:6: ALTER TABLE names 'seat_notes{{}}', which is not "
        "a literal identifier; name the object literally so its COMMENT can be "
        "verified",
        f"{NEXT}_seat_pins.py:8: statement begins with '{{}}', which is filled in "
        "at run time; its schema changes cannot be verified",
        f"{NEXT}_seat_pins.py:9: ALTER TABLE public.seat_notes action '%s' is "
        "filled in at run time; its changes cannot be verified",
    ]


def test_run_time_object_kind_in_execute_fails(tmp_path: Path) -> None:
    """``'CREATE ' || kind`` matches no DDL pattern, so it must fail, not pass."""
    _migration(
        tmp_path,
        f"{NEXT}_kinds.sql",
        """
DO $$
BEGIN
    EXECUTE 'CREATE ' || v_kind || ' hidden (id int)';
    EXECUTE 'CREATE OR REPLACE ' || v_kind || ' hidden_view AS SELECT 1';
    EXECUTE 'ALTER ' || v_kind || ' scene ADD COLUMN hidden int';
    EXECUTE format('CREATE %s hidden_fmt (id int)', v_kind);
    EXECUTE 'CREATE INDEX ' || v_name || ' ON scene (id)';
    EXECUTE 'ALTER TABLE scene ALTER COLUMN id SET DEFAULT ' || v_default;
END
$$;
""",
    )

    run_time = "is filled in at run time; its schema changes cannot be verified"
    assert _findings(tmp_path) == [
        f"{NEXT}_kinds.sql:3: CREATE object kind '{{}}' {run_time}",
        f"{NEXT}_kinds.sql:4: CREATE object kind '{{}}' {run_time}",
        f"{NEXT}_kinds.sql:5: ALTER object kind '{{}}' {run_time}",
        f"{NEXT}_kinds.sql:6: CREATE object kind '%s' {run_time}",
    ]


def test_python_run_time_object_kind_fails(tmp_path: Path) -> None:
    """f-strings, split-keyword ``+``, and ``%`` cannot hide the object kind.

    A placeholder before DDL words counts as SQL only beside a DDL verb, so
    ordinary log text about tables and functions still passes.
    """
    _migration(
        tmp_path,
        f"{NEXT}_kinds.py",
        """
def run(cur, kind, verb, statement, value, log) -> None:
    cur.execute(f"CREATE {kind} hidden (id int)")
    cur.execute("CREATE " + kind + " hidden_plus (id int)")
    ddl = "ALTER " + kind + " scene ADD COLUMN hidden int"
    cur.execute(ddl)
    create = "CREATE " + kind + " hidden_var (id int)"
    cur.execute(create)
    cur.execute("CREATE %s hidden_mod (id int)" % kind)
    cur.execute(" ".join(["CREATE", kind, "hidden_join (id int)"]))
    cur.execute(f"{statement}")
    cur.execute(f"DO $$ BEGIN {verb} TABLE hidden_do (id int); END $$")
    cur.execute(f"SELECT CASE WHEN true THEN {value} ELSE 0 END")
    cur.execute("SELECT 1 FROM pg_type WHERE typname = %s", (kind,))
    indexed = f"{verb} TABLE two (id int); CREATE INDEX two_idx ON two (id)"
    print(f"{value} rows copied into table foo")
    log.info("%s legacy function rows removed", value)
""",
    )

    run_time = "is filled in at run time; its schema changes cannot be verified"
    begins = "which is filled in at run time; its schema changes cannot be verified"
    assert _findings(tmp_path) == [
        f"{NEXT}_kinds.py:2: CREATE object kind '{{}}' {run_time}",
        f"{NEXT}_kinds.py:3: CREATE object kind '{{}}' {run_time}",
        f"{NEXT}_kinds.py:4: ALTER object kind '{{}}' {run_time}",
        f"{NEXT}_kinds.py:6: CREATE object kind '{{}}' {run_time}",
        f"{NEXT}_kinds.py:8: CREATE object kind '%s' {run_time}",
        f"{NEXT}_kinds.py:9: CREATE names no object kind, so it is a fragment of a "
        "command assembled at run time; its schema changes cannot be verified",
        f"{NEXT}_kinds.py:10: statement begins with '{{}}', {begins}",
        f"{NEXT}_kinds.py:11: statement begins with '{{}}', {begins}",
        f"{NEXT}_kinds.py:14: statement begins with '{{}}', {begins}",
    ]


def test_named_placeholder_is_reported_whole(tmp_path: Path) -> None:
    """A %(name)s column placeholder is named whole in the finding."""
    _migration(
        tmp_path,
        f"{NEXT}_named.py",
        """
def run(cur, column) -> None:
    cur.execute("ALTER TABLE seat_notes ADD COLUMN %(col)s int", {"col": column})
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_named.py:2: ALTER TABLE public.seat_notes ADD COLUMN names "
        "'%(col)s', which is not a literal identifier; name the object literally "
        "so its COMMENT can be verified",
    ]


def test_like_options_apply_left_to_right(tmp_path: Path) -> None:
    """Only an effective INCLUDING of COMMENTS (or ALL) copies column comments."""
    _migration(
        tmp_path,
        f"{NEXT}_likes.sql",
        """
CREATE TABLE copy_a (LIKE source INCLUDING ALL EXCLUDING COMMENTS);
CREATE TABLE copy_b (LIKE source EXCLUDING COMMENTS INCLUDING ALL);
CREATE TABLE copy_c (LIKE source INCLUDING COMMENTS EXCLUDING ALL);
CREATE TABLE copy_d (LIKE source EXCLUDING ALL INCLUDING COMMENTS);
CREATE TABLE copy_e (LIKE source INCLUDING COMMENTS EXCLUDING DEFAULTS);
COMMENT ON TABLE copy_a IS 'Copy.';
COMMENT ON TABLE copy_b IS 'Copy.';
COMMENT ON TABLE copy_c IS 'Copy.';
COMMENT ON TABLE copy_d IS 'Copy.';
COMMENT ON TABLE copy_e IS 'Copy.';
""",
    )

    unverified = "copies columns with LIKE but without INCLUDING COMMENTS"
    assert _findings(tmp_path) == [
        f"{NEXT}_likes.sql:1: CREATE TABLE public.copy_a {unverified}; they cannot "
        "be verified",
        f"{NEXT}_likes.sql:3: CREATE TABLE public.copy_c {unverified}; they cannot "
        "be verified",
    ]


def test_array_defaults_do_not_split_lists(tmp_path: Path) -> None:
    """Commas inside ARRAY[...] belong to one column or one argument."""
    _migration(
        tmp_path,
        f"{NEXT}_arrays.sql",
        """
CREATE TABLE tagged (
    id int,
    tags text[] NOT NULL DEFAULT ARRAY['a', 'b'],
    weights int[] DEFAULT ARRAY[1, 2, 3]
);
COMMENT ON TABLE tagged IS 'Tagged rows.';
COMMENT ON COLUMN tagged.id IS 'Row key.';
COMMENT ON COLUMN tagged.tags IS 'Tag names.';
COMMENT ON COLUMN tagged.weights IS 'Tag weights.';
CREATE FUNCTION pick(a int[] DEFAULT ARRAY[1, 2], b int) RETURNS int
    LANGUAGE sql AS 'SELECT b';
COMMENT ON FUNCTION pick(int[], int) IS 'Two arguments, one with an ARRAY default.';
ALTER TABLE tagged ADD COLUMN flags bool[] DEFAULT ARRAY[true, false],
    ADD COLUMN extra int;
COMMENT ON COLUMN tagged.flags IS 'Flags.';
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_arrays.sql:14: column public.tagged.extra has no COMMENT ON COLUMN",
    ]


def test_create_schema_elements_belong_to_that_schema(tmp_path: Path) -> None:
    """CREATE SCHEMA s CREATE TABLE t creates s.t, not public.t."""
    _migration(
        tmp_path,
        f"{NEXT}_lore_schema.sql",
        """
CREATE SCHEMA IF NOT EXISTS lore
    CREATE TABLE lore_notes (id int)
    CREATE VIEW lore_view AS SELECT 1 AS one;
COMMENT ON TABLE lore.lore_notes IS 'Notes in the new schema.';
COMMENT ON COLUMN lore.lore_notes.id IS 'Row key.';
COMMENT ON VIEW lore.lore_view IS 'View in the new schema.';
CREATE TABLE after_schema (id int);
COMMENT ON TABLE public.after_schema IS 'Later statements are public again.';
COMMENT ON COLUMN after_schema.id IS 'Row key.';
""",
    )

    assert _findings(tmp_path) == []


def test_function_comments_match_argument_count(tmp_path: Path) -> None:
    """An overload needs its own comment; a bare name documents any arity."""
    _migration(
        tmp_path,
        f"{NEXT}_weights.sql",
        """
CREATE FUNCTION weigh(p integer) RETURNS integer LANGUAGE sql AS 'SELECT p';
CREATE FUNCTION weigh(p integer, q text) RETURNS integer
    LANGUAGE sql AS $$SELECT p$$;
COMMENT ON FUNCTION weigh(integer) IS 'One-argument weight.';
CREATE FUNCTION tally(a int, b int) RETURNS int LANGUAGE sql AS 'SELECT a + b';
COMMENT ON FUNCTION tally IS 'Unique name, so no argument list is needed.';
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_weights.sql:2: function public.weigh (2 arguments) has no "
        "COMMENT ON FUNCTION",
    ]


def test_blank_or_null_comment_does_not_document(tmp_path: Path) -> None:
    """A blank or NULL comment is removed documentation, not coverage."""
    _migration(
        tmp_path,
        f"{NEXT}_blank.sql",
        """
CREATE TABLE ledger (id int);
COMMENT ON TABLE ledger IS '   ';
COMMENT ON COLUMN ledger.id IS NULL;
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_blank.sql:1: column public.ledger.id has no COMMENT ON COLUMN",
        f"{NEXT}_blank.sql:1: table public.ledger has no COMMENT ON TABLE",
        f"{NEXT}_blank.sql:2: COMMENT ON TABLE public.ledger is NULL or blank, "
        "which removes documentation",
        f"{NEXT}_blank.sql:3: COMMENT ON COLUMN public.ledger.id is NULL or "
        "blank, which removes documentation",
    ]


def test_undeclared_columns_fail_instead_of_passing(tmp_path: Path) -> None:
    """Columns the statement does not list cannot be verified statically."""
    _migration(
        tmp_path,
        f"{NEXT}_copies.sql",
        """
CREATE TABLE mood_copy AS SELECT * FROM scene_moods;
CREATE TABLE mood_like (LIKE scene_moods);
CREATE TABLE mood_child (extra text) INHERITS (scene_moods);
CREATE TABLE mood_full (LIKE scene_moods INCLUDING ALL);
COMMENT ON TABLE mood_copy IS 'Copy.';
COMMENT ON TABLE mood_like IS 'Like.';
COMMENT ON TABLE mood_child IS 'Child.';
COMMENT ON COLUMN mood_child.extra IS 'Extra.';
COMMENT ON TABLE mood_full IS 'Copies source comments.';
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_copies.sql:1: CREATE TABLE public.mood_copy declares no column "
        "list; its columns cannot be verified",
        f"{NEXT}_copies.sql:2: CREATE TABLE public.mood_like copies columns with "
        "LIKE but without INCLUDING COMMENTS; they cannot be verified",
        f"{NEXT}_copies.sql:3: CREATE TABLE public.mood_child INHERITS columns "
        "that cannot be verified",
    ]


def test_watermark_is_pinned() -> None:
    """Raising the watermark exempts new migrations, so it must change in review."""
    assert WATERMARK == 129


def test_repository_migrations_pass() -> None:
    """The real tree passes, and the command-line gate agrees."""
    assert check_migrations(REPO_ROOT / "migrations") == []
    result = subprocess.run(
        [sys.executable, str(CHECKER)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert f"after migration {WATERMARK}" in result.stdout


def test_every_historical_migration_parses() -> None:
    """Below the watermark the parser still reads every file and finds real debt."""
    findings = [
        finding.render()
        for finding in check_migrations(REPO_ROOT / "migrations", watermark=0)
    ]

    assert not [line for line in findings if "cannot parse" in line]
    assert (
        "migrations/104_character_experiences.sql:9: enum "
        "public.character_experience_basis has no COMMENT ON TYPE"
    ) in findings
    assert not [line for line in findings if line.startswith("migrations/114_")]


def test_command_line_reports_findings(tmp_path: Path) -> None:
    """The pre-commit entry point exits nonzero and names file:line."""
    path = _migration(tmp_path, f"{NEXT}_table.sql", "CREATE TABLE t ();\n")

    result = subprocess.run(
        [sys.executable, str(CHECKER), "--migrations-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert f"{path}:1: table public.t has no COMMENT ON TABLE" in result.stderr
