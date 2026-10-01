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
            "function public.touch_row() has no COMMENT ON FUNCTION",
        ),
        (
            "CREATE PROCEDURE public.review_p() LANGUAGE sql AS 'SELECT 1';",
            "procedure public.review_p() has no COMMENT ON PROCEDURE",
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
    ids=["enum", "function", "procedure", "view", "materialized-view", "table"],
)
def test_missing_object_comment_fails(tmp_path: Path, ddl: str, expected: str) -> None:
    """Enums, functions, procedures, views, and tables each need a COMMENT ON."""
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


def test_each_function_overload_needs_its_own_comment(tmp_path: Path) -> None:
    """A comment documents only the overload whose argument types it names."""
    _migration(
        tmp_path,
        f"{NEXT}_overloads.sql",
        """
CREATE FUNCTION review_f(p integer) RETURNS integer LANGUAGE sql AS 'SELECT p';
CREATE FUNCTION review_f(p text) RETURNS integer LANGUAGE sql AS 'SELECT 1';
COMMENT ON FUNCTION review_f(integer) IS 'Only the integer overload.';
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_overloads.sql:2: function public.review_f(text) has no COMMENT ON "
        "FUNCTION",
    ]


def test_function_signatures_ignore_names_modes_defaults_and_case(
    tmp_path: Path,
) -> None:
    """Types name an overload; names, modes, defaults, OUT, and spacing do not."""
    _migration(
        tmp_path,
        f"{NEXT}_overloads.sql",
        """
CREATE FUNCTION review_f(p integer) RETURNS integer LANGUAGE sql AS 'SELECT p';
CREATE OR REPLACE FUNCTION review_f(
    IN p TEXT,
    q double precision DEFAULT 0.5,
    r VARIADIC numeric( 5, 2 )[] = ARRAY[1],
    OUT total integer
) LANGUAGE sql AS 'SELECT 1';
COMMENT ON FUNCTION review_f(INTEGER) IS 'Integer overload.';
COMMENT ON FUNCTION public.review_f(label text, double   PRECISION, numeric(5,2) [])
    IS 'Text overload.';
""",
    )

    assert _findings(tmp_path) == []


def test_function_type_aliases_typmods_and_arrays_match(tmp_path: Path) -> None:
    """A type alias, typmod, or array spelling names the same PostgreSQL type.

    A different type is still a different overload.
    """
    _migration(
        tmp_path,
        f"{NEXT}_int_alias.sql",
        """
CREATE FUNCTION f(a int) RETURNS integer LANGUAGE sql AS 'SELECT a';
COMMENT ON FUNCTION f(integer) IS 'int is integer.';
""",
    )
    _migration(
        tmp_path,
        f"{WATERMARK + 2:03d}_varchar_typmod.sql",
        """
CREATE FUNCTION f(a varchar(20)) RETURNS integer LANGUAGE sql AS 'SELECT 1';
COMMENT ON FUNCTION f(character varying) IS 'Signatures ignore typmods.';
""",
    )
    _migration(
        tmp_path,
        f"{WATERMARK + 3:03d}_arrays_and_aliases.sql",
        """
CREATE FUNCTION f(a integer ARRAY[3], b int4[][], c timestamptz, d float(24))
    RETURNS integer LANGUAGE sql AS 'SELECT 1';
COMMENT ON FUNCTION f(int[], integer[], timestamp with time zone, real)
    IS 'Array spellings and aliases name the same types.';
""",
    )
    _migration(
        tmp_path,
        f"{WATERMARK + 4:03d}_other_type.sql",
        """
CREATE FUNCTION f(a text) RETURNS integer LANGUAGE sql AS 'SELECT 1';
COMMENT ON FUNCTION f(integer) IS 'Wrong type: PostgreSQL finds no f(integer).';
""",
    )

    assert _findings(tmp_path) == [
        f"{WATERMARK + 4:03d}_other_type.sql:1: function public.f(text) has no "
        "COMMENT ON FUNCTION",
    ]


def test_bare_function_name_must_name_one_overload(tmp_path: Path) -> None:
    """Without an argument list, a comment names the file's only overload.

    With two overloads PostgreSQL rejects the comment as not unique, so it
    documents neither.
    """
    _migration(
        tmp_path,
        f"{NEXT}_bare.sql",
        """
CREATE FUNCTION review_f(p integer) RETURNS integer LANGUAGE sql AS 'SELECT p';
CREATE FUNCTION review_f(p text) RETURNS integer LANGUAGE sql AS 'SELECT 1';
COMMENT ON FUNCTION review_f IS 'Names no single overload.';
CREATE FUNCTION tally(a int, b int) RETURNS int LANGUAGE sql AS 'SELECT a + b';
COMMENT ON FUNCTION tally IS 'The only tally, so no argument list is needed.';
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_bare.sql:1: function public.review_f(integer) has no COMMENT ON "
        "FUNCTION",
        f"{NEXT}_bare.sql:2: function public.review_f(text) has no COMMENT ON "
        "FUNCTION",
        f"{NEXT}_bare.sql:3: COMMENT ON FUNCTION public.review_f matches 2 overloads "
        "this migration creates (public.review_f(integer), public.review_f(text)); "
        "PostgreSQL rejects it as not unique, so it documents none",
    ]


def test_procedure_comments_follow_postgresql_lookup(tmp_path: Path) -> None:
    """A procedure needs COMMENT ON PROCEDURE or ROUTINE, matched as PostgreSQL does.

    The comment may list the input types or, marking none OUT, every argument
    type. COMMENT ON FUNCTION does not document a procedure, and a Python DDL
    constant that creates one is scanned even when it starts with another verb.
    """
    _migration(
        tmp_path,
        f"{NEXT}_procedures.sql",
        """
CREATE OR REPLACE PROCEDURE settle(IN a integer, OUT b integer)
    LANGUAGE plpgsql AS $$ BEGIN b := a; END $$;
COMMENT ON PROCEDURE settle(integer) IS 'Input types name the procedure.';
CREATE PROCEDURE audit(a integer, OUT b text)
    LANGUAGE plpgsql AS $$ BEGIN b := ''; END $$;
COMMENT ON PROCEDURE audit(integer, text) IS 'So do all of its argument types.';
CREATE PROCEDURE sweep() LANGUAGE sql AS 'SELECT 1';
COMMENT ON ROUTINE sweep IS 'ROUTINE documents a procedure.';
CREATE PROCEDURE purge() LANGUAGE sql AS 'SELECT 1';
COMMENT ON FUNCTION purge() IS 'PostgreSQL rejects this: purge() is not a function.';
""",
    )
    _migration(
        tmp_path,
        f"{WATERMARK + 2:03d}_tidy.py",
        '''
DDL = """
DROP PROCEDURE IF EXISTS tidy();
CREATE PROCEDURE tidy() LANGUAGE sql AS 'SELECT 1';
"""
''',
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_procedures.sql:9: procedure public.purge() has no COMMENT ON "
        "PROCEDURE",
        f"{WATERMARK + 2:03d}_tidy.py:3: procedure public.tidy() has no COMMENT ON "
        "PROCEDURE",
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


def test_foreign_tables_follow_create_table_rules(tmp_path: Path) -> None:
    """A foreign table needs COMMENT ON FOREIGN TABLE and every column comment.

    PostgreSQL rejects COMMENT ON TABLE for a foreign table ("is not a
    table"), so that form documents nothing. PARTITION OF and LIKE behave as
    they do for a plain table, under the CREATE FOREIGN TABLE label.
    """
    _migration(
        tmp_path,
        f"{NEXT}_remote.sql",
        """
CREATE FOREIGN TABLE remote_moods (
    id int OPTIONS (column_name 'mood_id') NOT NULL,
    mood text
) SERVER mood_server OPTIONS (table_name 'moods');
COMMENT ON FOREIGN TABLE remote_moods IS 'Moods kept on another server.';
COMMENT ON COLUMN remote_moods.id IS 'Remote row key.';
COMMENT ON COLUMN remote_moods.mood IS 'Remote mood.';
CREATE FOREIGN TABLE IF NOT EXISTS remote_notes (id int, note text) SERVER s;
COMMENT ON TABLE remote_notes IS 'PostgreSQL rejects this for a foreign table.';
COMMENT ON COLUMN remote_notes.id IS 'Remote row key.';
CREATE FOREIGN TABLE remote_calm PARTITION OF scene_moods
    FOR VALUES IN ('calm') SERVER mood_server;
COMMENT ON FOREIGN TABLE remote_calm IS 'Remote partition.';
CREATE FOREIGN TABLE remote_like (LIKE scene_moods) SERVER mood_server;
COMMENT ON FOREIGN TABLE remote_like IS 'Copied shape.';
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_remote.sql:8: column public.remote_notes.note has no COMMENT ON "
        "COLUMN",
        f"{NEXT}_remote.sql:8: foreign table public.remote_notes has no COMMENT ON "
        "FOREIGN TABLE",
        f"{NEXT}_remote.sql:11: CREATE FOREIGN TABLE public.remote_calm declares no "
        "column list; its columns cannot be verified",
        f"{NEXT}_remote.sql:14: CREATE FOREIGN TABLE public.remote_like copies "
        "columns with LIKE but without INCLUDING COMMENTS; they cannot be verified",
    ]


def test_run_time_foreign_kind_fails(tmp_path: Path) -> None:
    """FOREIGN is a CREATE modifier, so a kind filled in after it is reported."""
    _migration(
        tmp_path,
        f"{NEXT}_remote_kinds.sql",
        """
DO $$
BEGIN
    EXECUTE 'CREATE FOREIGN ' || v_kind || ' t (id int) SERVER s';
    EXECUTE 'CREATE FOREIGN TABLE ' || v_name || ' (id int) SERVER s';
END
$$;
""",
    )

    assert _findings(tmp_path) == [
        f"{NEXT}_remote_kinds.sql:3: CREATE object kind '{{}}' is filled in at run "
        "time; its schema changes cannot be verified",
        f"{NEXT}_remote_kinds.sql:4: CREATE FOREIGN TABLE names '{{}}', which is not "
        "a literal identifier; name the object literally so its COMMENT can be "
        "verified",
    ]


def test_import_foreign_schema_fails_as_unsupported(tmp_path: Path) -> None:
    """IMPORT FOREIGN SCHEMA creates tables it does not name, wherever it runs."""
    _migration(
        tmp_path,
        f"{NEXT}_import.sql",
        """
IMPORT FOREIGN SCHEMA remote FROM SERVER mood_server INTO public;
DO $$
BEGIN
    IMPORT FOREIGN SCHEMA remote LIMIT TO (moods)
        FROM SERVER mood_server INTO public;
END
$$;
""",
    )
    _migration(
        tmp_path,
        f"{WATERMARK + 2:03d}_import.py",
        """
IMPORT = "IMPORT FOREIGN SCHEMA remote FROM SERVER mood_server INTO public"


def run(cur) -> None:
    cur.execute("IMPORT FOREIGN SCHEMA archive FROM SERVER mood_server INTO public")
    cur.execute(IMPORT)
""",
    )

    unsupported = (
        "IMPORT FOREIGN SCHEMA creates foreign tables it does not name; their "
        "columns cannot be verified"
    )
    assert _findings(tmp_path) == [
        f"{NEXT}_import.sql:1: {unsupported}",
        f"{NEXT}_import.sql:4: {unsupported}",
        f"{WATERMARK + 2:03d}_import.py:1: {unsupported}",
        f"{WATERMARK + 2:03d}_import.py:5: {unsupported}",
    ]


def test_select_into_fails_like_ctas(tmp_path: Path) -> None:
    """SELECT INTO creates a table without a column list, outside PL/pgSQL.

    In a DO body SELECT INTO assigns a variable, as in migrations 077 and 109,
    so it passes there; a temporary target and INSERT INTO pass everywhere.
    An EXECUTE command in a DO body is still scanned as SQL, so its SELECT INTO
    is reported, and a target built at run time is unresolvable.
    """
    _migration(
        tmp_path,
        f"{NEXT}_snapshots.sql",
        """
SELECT id, mood
INTO mood_snapshot
FROM scene_moods;
WITH recent AS (SELECT id, mood FROM scene_moods WHERE id > 10)
SELECT id, mood
INTO recent_moods
FROM recent;
SELECT id
INTO UNLOGGED TABLE mood_ids
FROM scene_moods;
SELECT id INTO TEMP mood_scratch FROM scene_moods;
SELECT id INTO LOCAL TEMP mood_scratch_local FROM scene_moods;
INSERT INTO mood_archive SELECT id, mood FROM scene_moods;
DO $migration$
DECLARE
    invalid_tags text;
    completed_target_constraints text[];
BEGIN
    WITH expected(tag) AS (
        VALUES
            ('intoxicated:stimulant'),
            ('intoxicated:depressant')
    )
    SELECT string_agg(expected.tag, ', ' ORDER BY expected.tag)
    INTO invalid_tags
    FROM expected
    LEFT JOIN tags AS registry USING (tag)
    WHERE registry.id IS NULL;
    SELECT array_agg(conname ORDER BY conname)
    INTO completed_target_constraints
    FROM pg_constraint
    WHERE conrelid = 'character_project_states'::regclass
      AND contype = 'c';
END
$migration$;
COMMENT ON TABLE mood_snapshot IS 'Snapshot.';
COMMENT ON TABLE recent_moods IS 'Recent moods.';
COMMENT ON TABLE mood_ids IS 'Mood ids.';
DO $$
DECLARE
    v_name text := 'mood_copy';
BEGIN
    EXECUTE 'SELECT 1 AS id INTO ' || v_name || ' FROM scene_moods';
END
$$;
WITH a AS (SELECT 1)
(SELECT 1
 INTO with_paren_main);
WITH a AS (SELECT 1)
(SELECT 1
 INTO with_paren_union) UNION ALL SELECT 2;
COMMENT ON TABLE with_paren_main IS 'Parenthesized main statement.';
COMMENT ON TABLE with_paren_union IS 'Parenthesized first branch.';
""",
    )
    _migration(
        tmp_path,
        f"{WATERMARK + 2:03d}_snapshots.py",
        '''
SNAPSHOT = """
SELECT id, mood
INTO py_snapshot
FROM scene_moods
"""
RECENT = """
WITH recent AS (SELECT id FROM scene_moods)
SELECT id
INTO py_recent
FROM recent
"""
DOCS = """
COMMENT ON TABLE py_snapshot IS 'Snapshot.';
COMMENT ON TABLE py_recent IS 'Recent.';
"""


def run(cur) -> None:
    cur.execute(SNAPSHOT)
    cur.execute(RECENT)
    cur.execute(DOCS)
''',
    )

    no_columns = "declares no column list; its columns cannot be verified"
    assert _findings(tmp_path) == [
        f"{NEXT}_snapshots.sql:2: SELECT INTO public.mood_snapshot {no_columns}",
        f"{NEXT}_snapshots.sql:6: SELECT INTO public.recent_moods {no_columns}",
        f"{NEXT}_snapshots.sql:9: SELECT INTO public.mood_ids {no_columns}",
        f"{NEXT}_snapshots.sql:43: SELECT INTO names '{{}}', which is not a "
        "literal identifier; name the object literally so its COMMENT can be "
        "verified",
        f"{NEXT}_snapshots.sql:48: SELECT INTO public.with_paren_main {no_columns}",
        f"{NEXT}_snapshots.sql:51: SELECT INTO public.with_paren_union {no_columns}",
        f"{WATERMARK + 2:03d}_snapshots.py:3: SELECT INTO public.py_snapshot "
        f"{no_columns}",
        f"{WATERMARK + 2:03d}_snapshots.py:9: SELECT INTO public.py_recent "
        f"{no_columns}",
    ]


def test_select_into_is_found_past_comments_parentheses_and_cte_names(
    tmp_path: Path,
) -> None:
    """SELECT INTO still fails where it is not the literal's or statement's head.

    A Python literal may open with a comment or another statement; a statement
    may open with parentheses, and PostgreSQL then still creates the table; a
    CTE may be named ``delete`` or ``update``, which is not the verb. A real
    DELETE after a CTE, a SELECT without INTO, and PL/pgSQL SELECT INTO in a DO
    body (migrations 077 and 109) stay silent.
    """
    _migration(
        tmp_path,
        f"{NEXT}_hidden.sql",
        """
(SELECT 1
 INTO t);
(SELECT 1
 INTO t) UNION ALL SELECT 2;
WITH delete AS (SELECT 1 AS id)
SELECT id
INTO snapshot
FROM delete;
WITH RECURSIVE update (n) AS (SELECT 1)
SELECT n
INTO snapshot2
FROM update;
WITH delete AS (SELECT 1 AS id) DELETE FROM t WHERE id IN (SELECT id FROM delete);
SELECT 1 FROM (SELECT 2) AS sub;
DO $$
DECLARE
    invalid_tags text;
    completed_target_constraints text[];
BEGIN
    WITH expected(tag) AS (
        VALUES
            ('intoxicated:stimulant'),
            ('intoxicated:depressant')
    )
    SELECT string_agg(expected.tag, ', ' ORDER BY expected.tag)
    INTO invalid_tags
    FROM expected;
    SELECT array_agg(conname ORDER BY conname)
    INTO completed_target_constraints
    FROM pg_constraint
    WHERE conrelid = 'character_project_states'::regclass;
END
$$;
COMMENT ON TABLE t IS 'Parenthesized snapshot.';
COMMENT ON TABLE snapshot IS 'Snapshot after a CTE named delete.';
COMMENT ON TABLE snapshot2 IS 'Snapshot after a recursive CTE named update.';
""",
    )
    _migration(
        tmp_path,
        f"{WATERMARK + 2:03d}_hidden.py",
        '''
COMMENTED = """-- snapshot
SELECT 1 INTO t;"""
WRAPPED = "BEGIN; SELECT 1 INTO t2; COMMIT;"
DOCS = """
COMMENT ON TABLE t IS 'Commented snapshot.';
COMMENT ON TABLE t2 IS 'Wrapped snapshot.';
"""


def run(cur) -> None:
    cur.execute(COMMENTED)
    cur.execute(WRAPPED)
    cur.execute(DOCS)
''',
    )

    no_columns = "declares no column list; its columns cannot be verified"
    assert _findings(tmp_path) == [
        f"{NEXT}_hidden.sql:2: SELECT INTO public.t {no_columns}",
        f"{NEXT}_hidden.sql:4: SELECT INTO public.t {no_columns}",
        f"{NEXT}_hidden.sql:7: SELECT INTO public.snapshot {no_columns}",
        f"{NEXT}_hidden.sql:11: SELECT INTO public.snapshot2 {no_columns}",
        f"{WATERMARK + 2:03d}_hidden.py:2: SELECT INTO public.t {no_columns}",
        f"{WATERMARK + 2:03d}_hidden.py:3: SELECT INTO public.t2 {no_columns}",
    ]


def test_select_into_is_found_past_search_cycle_and_explain_analyze(
    tmp_path: Path,
) -> None:
    """SEARCH and CYCLE words are not the verb; EXPLAIN ANALYZE runs SELECT INTO.

    A recursive CTE's SEARCH or CYCLE clause may name a column ``update`` or
    ``delete``, and a CTE named ``delete`` may follow it. EXPLAIN ANALYZE
    executes its statement, so a parenthesized or CTE-led SELECT INTO behind it
    creates its table. Plain EXPLAIN, EXPLAIN VERBOSE, and ANALYZE false only
    plan the statement and pass. PREPARE is reported, because an EXECUTE of
    the prepared statement creates the table. A real DELETE after SEARCH and
    CYCLE stays silent.
    """
    _migration(
        tmp_path,
        f"{NEXT}_clauses.sql",
        """
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 3)
CYCLE n SET update USING path
SELECT n INTO cycled FROM r;
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 3)
SEARCH DEPTH FIRST BY n SET ord, delete AS (SELECT 1 AS id)
SELECT n INTO searched FROM r, delete;
WITH RECURSIVE r(delete) AS (
    SELECT 1 UNION ALL SELECT delete + 1 FROM r WHERE delete < 3
) SEARCH BREADTH FIRST BY delete SET ord
SELECT 1 INTO searched_by_delete FROM r;
EXPLAIN ANALYZE SELECT 1 INTO explained;
EXPLAIN ANALYZE (SELECT 1 INTO explained_paren);
EXPLAIN (ANALYZE) WITH delete AS (SELECT 1 AS id)
SELECT id INTO explained_cte FROM delete;
EXPLAIN ANALYZE VERBOSE WITH a AS (SELECT 1) (SELECT 1 INTO explained_both);
PREPARE p AS SELECT 1 INTO prepared;
EXPLAIN SELECT 1 INTO planned;
EXPLAIN VERBOSE SELECT 1 INTO planned_verbose;
EXPLAIN (ANALYZE false, VERBOSE) SELECT 1 INTO planned_off;
EXPLAIN (SELECT 1 INTO planned_paren);
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 3)
SEARCH DEPTH FIRST BY n SET ord
CYCLE n SET delete TO true DEFAULT false USING update
DELETE FROM t WHERE id IN (SELECT n FROM r);
COMMENT ON TABLE cycled IS 'After a CYCLE clause.';
COMMENT ON TABLE searched IS 'After a SEARCH clause and a CTE named delete.';
COMMENT ON TABLE searched_by_delete IS 'After SEARCH BY a column named delete.';
COMMENT ON TABLE explained IS 'Behind EXPLAIN ANALYZE.';
COMMENT ON TABLE explained_paren IS 'Parenthesized, behind EXPLAIN ANALYZE.';
COMMENT ON TABLE explained_cte IS 'After a CTE, behind EXPLAIN (ANALYZE).';
COMMENT ON TABLE explained_both IS 'After a CTE and a parenthesis.';
COMMENT ON TABLE prepared IS 'Prepared for a later EXECUTE.';
""",
    )

    no_columns = "declares no column list; its columns cannot be verified"
    assert _findings(tmp_path) == [
        f"{NEXT}_clauses.sql:3: SELECT INTO public.cycled {no_columns}",
        f"{NEXT}_clauses.sql:6: SELECT INTO public.searched {no_columns}",
        f"{NEXT}_clauses.sql:10: SELECT INTO public.searched_by_delete {no_columns}",
        f"{NEXT}_clauses.sql:11: SELECT INTO public.explained {no_columns}",
        f"{NEXT}_clauses.sql:12: SELECT INTO public.explained_paren {no_columns}",
        f"{NEXT}_clauses.sql:14: SELECT INTO public.explained_cte {no_columns}",
        f"{NEXT}_clauses.sql:15: SELECT INTO public.explained_both {no_columns}",
        f"{NEXT}_clauses.sql:16: SELECT INTO public.prepared {no_columns}",
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
    # PL/pgSQL SELECT INTO in DO bodies (022, 077, 100, 109, 110, 134, 138)
    # assigns a variable.
    assert not [
        line
        for line in findings
        if "SELECT INTO" in line
        or "IMPORT FOREIGN SCHEMA" in line
        or "foreign table" in line.lower()
    ]


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
