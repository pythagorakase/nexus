"""#813 guards on full-data disposable clones, before and after fleet landing.

Needs the frozen items/ai_notebook closure, schema_migrations, surviving public
and assets data, relationship triggers and wizard cache tables. Sources are read
ONLY by read-only pg_dump subprocesses. Every driver targets postgres or a
qa640_813_* allocation from tests.pg_fixtures. All provider pins are TEST.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

import psycopg2
import pytest

from nexus.api.db_pool import close_all_pools
from nexus.config.story_model import StorySettings, write_story_settings
from scripts import migrate
from tests.pg_fixtures import (
    connect,
    disposable_database,
    require_disposable_target,
    route_slot_to_disposable,
    seed_character,
    seed_protagonist,
    subprocess_env,
)

pytestmark = pytest.mark.requires_postgres
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/813_pre143_schema.sql"
MANIFEST = json.loads((ROOT / "tests/fixtures/813_pre143_manifest.json").read_text())
MIGRATION = ROOT / "migrations/143_drop_dead_schema_strata.sql"
SOURCES = ("NEXUS_template", "save_01", "save_02", "save_03", "save_04", "save_05")
NEW_COMMENT = (
    "BEFORE UPDATE trigger on characters and places "
    "(trg_characters_set_updated, trg_places_set_updated): stamps updated_at "
    "with now(), the transaction start time."
)
TARGET_NAMES = (
    "items",
    "ai_notebook",
    "items_id_seq",
    "ai_notebook_id_seq",
    *(e[1] for e in MANIFEST["enums"]),
)

# Catalog queries frozen before DDL; each definition uses fresh clone OIDs.
QUERIES: dict[str, str] = {
    "columns": (
        "SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmo"
        "d),a.attnotnull,pg_get_expr(d.adbin,d.adrelid),col_descripti"
        "on(c.oid,a.attnum) FROM pg_class c JOIN pg_namespace n ON n."
        "oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid L"
        "EFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnu"
        "m WHERE n.nspname='public' AND c.relname IN ('items','ai_not"
        "ebook') AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.rel"
        "name,a.attnum"
    ),
    "constraints": (
        "SELECT conname,conrelid::regclass::text,pg_get_constraintdef"
        "(oid),obj_description(oid,'pg_constraint') FROM pg_constrain"
        "t WHERE conrelid IN ('public.items'::regclass,'public.ai_not"
        "ebook'::regclass) ORDER BY conname"
    ),
    "indexes": (
        "SELECT c.relname,pg_get_indexdef(c.oid),obj_description(c.oi"
        "d,'pg_class') FROM pg_class c JOIN pg_index i ON i.indexreli"
        "d=c.oid WHERE i.indrelid IN ('public.items'::regclass,'publi"
        "c.ai_notebook'::regclass) ORDER BY c.relname"
    ),
    "sequences": (
        "SELECT c.relname,s.seqtypid::regtype::text,s.seqstart,s.seqi"
        "ncrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle,obj_descrip"
        "tion(c.oid,'pg_class') FROM pg_class c JOIN pg_sequence s ON"
        " s.seqrelid=c.oid WHERE c.oid IN ('public.items_id_seq'::reg"
        "class,'public.ai_notebook_id_seq'::regclass) ORDER BY c.reln"
        "ame"
    ),
    "closure_objects": (
        "WITH RECURSIVE roots(classid,objid,objsubid) AS (\n SELECT "
        "'pg_class'::regclass::oid,c.oid,0 FROM pg_class c JOIN "
        "pg_namespace n ON n.oid=c.relnamespace WHERE "
        "n.nspname='public' AND c.relname IN "
        "('items','ai_notebook')\n UNION SELECT "
        "'pg_class'::regclass::oid,a.attrelid,a.attnum FROM "
        "pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN "
        "pg_namespace n ON n.oid=c.relnamespace WHERE "
        "n.nspname='public' AND c.relname IN ('items','ai_notebook') "
        "AND a.attnum>0 AND NOT a.attisdropped\n UNION SELECT "
        "'pg_type'::regclass::oid,t.oid,0 FROM pg_type t JOIN "
        "pg_namespace n ON n.oid=t.typnamespace WHERE "
        "n.nspname='public' AND t.typname IN "
        "('agent_type','log_level_type','emotional_valence','entity_t"
        "ype','item_type','relationship_type','threat_domain_type','t"
        "hreat_lifecycle_type','trait')\n), closure AS ( SELECT * "
        "FROM roots UNION SELECT d.classid,d.objid,d.objsubid FROM "
        "pg_depend d JOIN closure c ON d.refclassid=c.classid AND "
        "d.refobjid=c.objid AND (c.objsubid=0 OR "
        "d.refobjsubid=c.objsubid))\nSELECT "
        "classid::regclass::text,pg_describe_object(classid,objid,obj"
        "subid) FROM closure ORDER BY 1,2"
    ),
    "internal_triggers": (
        "SELECT t.tgrelid::regclass::text,t.tgfoid::regprocedure::tex"
        "t,t.tgtype,t.tgenabled,t.tgconstrrelid::regclass::text,t.tgd"
        "eferrable,t.tginitdeferred,encode(t.tgargs,'hex'),pg_get_tri"
        "ggerdef(t.oid) FROM pg_trigger t JOIN pg_constraint c ON c.o"
        "id=t.tgconstraint WHERE c.conname='items_owner_id_fkey1' AND"
        " c.conrelid='public.items'::regclass ORDER BY 1,2"
    ),
}


QUERIES["closure_edges"] = (
    "WITH RECURSIVE roots(classid,objid,objsubid) AS (\n SELECT "
    "'pg_class'::regclass::oid,c.oid,0 FROM pg_class c JOIN "
    "pg_namespace n ON n.oid=c.relnamespace WHERE "
    "n.nspname='public' AND c.relname IN "
    "('items','ai_notebook')\n UNION SELECT "
    "'pg_class'::regclass::oid,a.attrelid,a.attnum FROM "
    "pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN "
    "pg_namespace n ON n.oid=c.relnamespace WHERE "
    "n.nspname='public' AND c.relname IN ('items','ai_notebook') "
    "AND a.attnum>0 AND NOT a.attisdropped\n UNION SELECT "
    "'pg_type'::regclass::oid,t.oid,0 FROM pg_type t JOIN "
    "pg_namespace n ON n.oid=t.typnamespace WHERE "
    "n.nspname='public' AND t.typname IN "
    "('agent_type','log_level_type','emotional_valence','entity_t"
    "ype','item_type','relationship_type','threat_domain_type','t"
    "hreat_lifecycle_type','trait')\n), closure AS ( SELECT * "
    "FROM roots UNION SELECT d.classid,d.objid,d.objsubid FROM "
    "pg_depend d JOIN closure c ON d.refclassid=c.classid AND "
    "d.refobjid=c.objid AND (c.objsubid=0 OR "
    "d.refobjsubid=c.objsubid))\nSELECT "
    "c.classid::regclass::text,pg_describe_object(c.classid,c.obj"
    "id,c.objsubid),d.deptype,pg_describe_object(d.refclassid,d.r"
    "efobjid,d.refobjsubid) FROM closure c LEFT JOIN pg_depend d "
    "ON d.classid=c.classid AND d.objid=c.objid AND "
    "d.objsubid=c.objsubid ORDER BY 1,2,3,4"
)


def _normalized(value: Any) -> Any:
    text = json.dumps(value, default=str)
    text = re.sub(r"pg_toast_\d+", "pg_toast_TABLEOID", text)
    text = re.sub(
        r"RI_ConstraintTrigger_([ac])_\d+", r"RI_ConstraintTrigger_\1_OID", text
    )
    return json.loads(text)


def _target_state(cur: Any) -> dict[str, Any]:
    cur.execute("SET LOCAL search_path=pg_catalog")
    result = {}
    for key, query in QUERIES.items():
        cur.execute(query)
        result[key] = _normalized(cur.fetchall())
    cur.execute(
        "SELECT n.nspname,t.typname,t.typtype,"
        "(SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder) FROM pg_enum e "
        "WHERE e.enumtypid=t.oid),obj_description(t.oid,'pg_type') "
        "FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
        "WHERE n.nspname='public' AND t.typname=ANY(%s) ORDER BY t.typname",
        ([e[1] for e in MANIFEST["enums"]],),
    )
    result["enums"] = _normalized(cur.fetchall())
    cur.execute(
        "SELECT c.oid::regclass::text,obj_description(c.oid,'pg_class') "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname IN ('items','ai_notebook') "
        "ORDER BY c.relname"
    )
    result["table_comments"] = _normalized(cur.fetchall())
    cur.execute(
        "SELECT obj_description('public.set_updated_at()'::regprocedure,'pg_proc'),"
        "pg_get_functiondef('public.set_updated_at()'::regprocedure)"
    )
    result["shared_comment"], result["shared_body"] = cur.fetchone()
    cur.execute(
        (
            "SELECT count(*) FROM public.items UNION ALL SELECT count(*) "
            "FROM public.ai_notebook"
        )
    )
    assert cur.fetchall() == [(0,), (0,)], "fixture targets must be empty"
    cur.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname=ANY(%s) "
        "AND pg_get_userbyid(c.relowner) <> current_user",
        (list(TARGET_NAMES[:4]),),
    )
    assert cur.fetchall() == [], "restore must normalize owners"
    for table in ("items", "ai_notebook"):
        cur.execute("SELECT pg_get_serial_sequence(%s,'id')", ("public." + table,))
        assert cur.fetchone() == ("public." + table + "_id_seq",)
    return result


def _assert_manifest(cur: Any) -> None:
    actual = _target_state(cur)
    expected = {key: MANIFEST[key] for key in actual}
    assert actual == expected, "pre-143 catalog drift"


def _post_state(cur: Any) -> None:
    for name in TARGET_NAMES:
        cur.execute(
            "SELECT to_regclass(%s),to_regtype(%s)",
            ("public." + name, "public." + name),
        )
        assert cur.fetchone() == (None, None), name
    cur.execute("SELECT count(*) FROM schema_migrations WHERE version='143'")
    assert cur.fetchone() == (1,)
    cur.execute(
        "SELECT obj_description('public.set_updated_at()'::regprocedure,'pg_proc')"
    )
    assert cur.fetchone() == (NEW_COMMENT,)


def _load_fixture(dbname: str) -> None:
    """Reconstruct only complete post-143 clones; reject partial/drifted states."""
    require_disposable_target(dbname)
    assert dbname.startswith("qa640_813_"), dbname
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        assert cur.fetchone() == (dbname,), "allocated target identity mismatch"
        cur.execute("SELECT count(*) FROM schema_migrations WHERE version='143'")
        stamped = cur.fetchone()[0]
        if not stamped:
            _assert_manifest(cur)
            return
        _post_state(cur)
        cur.execute(FIXTURE.read_text())
        cur.execute("DELETE FROM schema_migrations WHERE version='143'")
        assert cur.rowcount == 1
        _assert_manifest(cur)


def _dump_sources(sources: tuple[str, ...], directory: Path) -> dict[str, Path]:
    """Use the corpus policy's temporary, read-only custom dump/clone transport."""
    result = {}
    for source in sources:
        archive = directory / (source + ".dump")
        env = subprocess_env()
        env["PGOPTIONS"] = (
            env.get("PGOPTIONS", "") + " -c default_transaction_read_only=on"
        )
        print("813 source dump:", source, flush=True)
        subprocess.run(
            ["pg_dump", "--format=custom", "--file", str(archive), "--dbname", source],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=540,
        )
        result[source] = archive
    return result


@pytest.fixture(scope="session")
def archives() -> Iterator[dict[str, Path]]:
    """Ordinary regressions dump only the template and delete the archive at exit."""
    with tempfile.TemporaryDirectory(prefix="813-template-") as directory:
        yield _dump_sources(("NEXUS_template",), Path(directory))


@pytest.fixture(scope="session")
def fleet_archives(
    archives: dict[str, Path], request: pytest.FixtureRequest
) -> Iterator[dict[str, Path]]:
    """Only the corpus-selected fleet test may read save slots, via pg_dump."""
    if not any(
        item.get_closest_marker("requires_corpus") for item in request.session.items
    ):
        raise RuntimeError("fleet_archives requires a requires_corpus test")
    if os.environ.get("NEXUS_RUN_CORPUS") != "1":
        raise RuntimeError("fleet archives require NEXUS_RUN_CORPUS=1")
    with tempfile.TemporaryDirectory(prefix="813-corpus-") as directory:
        yield {**archives, **_dump_sources(SOURCES[1:], Path(directory))}


@contextmanager
def _clone(
    archives: dict[str, Path], tmp_path: Path, source: str = "NEXUS_template"
) -> Iterator[str]:
    """Restore raw data, pin TEST, and migrate the clone through predecessors."""
    tree = tmp_path / "preceding"
    tree.mkdir(exist_ok=True)
    for version, _, path in migrate.discover_migrations():
        if version != "143":
            shutil.copy2(path, tree / path.name)
    with disposable_database("qa640_813_case") as dbname:
        require_disposable_target(dbname)
        subprocess.run(
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "--dbname",
                dbname,
                str(archives[source]),
            ],
            env=subprocess_env(),
            check=True,
            capture_output=True,
            text=True,
            timeout=540,
        )
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                (
                    "INSERT INTO global_variables(id,new_story) VALUES(true,true)"
                    " ON CONFLICT(id) DO NOTHING"
                )
            )
            write_story_settings(
                cur, StorySettings(skald_model="TEST", gaia_model=None)
            )
        applied, failed = migrate.migrate_database(
            dbname, skip_locked=False, migrations_dir=tree
        )
        assert failed == 0, (applied, failed)
        yield dbname


def _snapshot(dbname: str, *, surviving: bool) -> str:
    """Hash pg_dump schema blocks and exact surviving data/sequence state."""
    args = ["pg_dump", "--dbname", dbname]
    if surviving:
        for name in TARGET_NAMES[:4]:
            args.append("--exclude-table=public." + name)
        args.append("--exclude-table-data=public.schema_migrations")
    result = subprocess.run(
        args,
        env=subprocess_env(),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    blocks = re.split(r"(?=--\n-- Name: )", result.stdout)
    kept = []
    for block in blocks:
        if surviving:
            header = block.split("\n", 3)[:3]
            if "Schema: public;" in " ".join(header) and any(
                f"Name: {e[1]}; Type: TYPE;" in " ".join(header)
                or f"Name: TYPE {e[1]}; Type: COMMENT;" in " ".join(header)
                for e in MANIFEST["enums"]
            ):
                continue
            if "Schema: public;" in " ".join(
                header
            ) and "Name: FUNCTION set_updated_at(); Type: COMMENT;" in " ".join(header):
                continue
        block = re.sub(r"^\\(?:un)?restrict .*\n", "", block, flags=re.MULTILINE)
        kept.append(block)
    return hashlib.sha256("".join(kept).encode()).hexdigest()


def _function_catalog(dbname: str) -> list[Any]:
    """Record surviving application functions including owner, ACL and comment."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT p.oid,n.nspname,p.proname,pg_get_functiondef(p.oid),"
            "p.proowner,p.proacl,p.proconfig,"
            "CASE WHEN p.oid='public.set_updated_at()'::regprocedure THEN NULL "
            "ELSE obj_description(p.oid,'pg_proc') END "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE p.oid >= 16384 AND n.nspname !~ '^pg_(temp|toast)' "
            "AND p.prokind IN ('f','p','w') "
            "ORDER BY p.oid"
        )
        return cur.fetchall()


def _apply(dbname: str) -> bool:
    with closing(connect(dbname)) as conn:
        return migrate.apply_migration(
            conn, "143", "drop_dead_schema_strata", MIGRATION
        )


def _sql(dbname: str, statement: str) -> None:
    require_disposable_target(dbname)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(statement)


def _stamps(dbname: str) -> list[Any]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT version,name,applied_at FROM schema_migrations ORDER BY version"
        )
        return cur.fetchall()


@pytest.mark.requires_corpus
@pytest.mark.parametrize("source", SOURCES)
def test_migration_143_drops_only_manifest_on_each_fleet_clone(
    fleet_archives: dict[str, Path],
    tmp_path: Path,
    source: str,
) -> None:
    """Preserve full source data, all surviving definitions, and repeat-run state."""
    with _clone(fleet_archives, tmp_path, source) as dbname:
        # Frozen full-data pre-143 rehearsal is separate from reconstruction.
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM schema_migrations WHERE version='143'")
            was_post = cur.fetchone()[0] == 1
        before = _snapshot(dbname, surviving=True)
        functions = _function_catalog(dbname)
        if not was_post:
            raw_stamps = _stamps(dbname)
            assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
            assert _snapshot(dbname, surviving=True) == before
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                _post_state(cur)
            assert [s for s in _stamps(dbname) if s[0] != "143"] == raw_stamps
            raw_post_stamps = _stamps(dbname)
            assert migrate.migrate_database(dbname, skip_locked=False) == (0, 0)
            assert _stamps(dbname) == raw_post_stamps
            assert _snapshot(dbname, surviving=True) == before
        _load_fixture(dbname)
        assert _snapshot(dbname, surviving=True) == before
        stamps = _stamps(dbname)
        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            _post_state(cur)
        assert _snapshot(dbname, surviving=True) == before
        assert _function_catalog(dbname) == functions
        assert [s for s in _stamps(dbname) if s[0] != "143"] == stamps
        assert migrate.migrate_database(dbname, skip_locked=False) == (0, 0)
        assert _snapshot(dbname, surviving=True) == before


@pytest.mark.parametrize("post", (False, True))
@pytest.mark.parametrize(
    "case",
    (
        "shadow-broken",
        "shadow-healthy",
        "session-path",
        "overload-broken",
        "catalog-first-broken",
        "catalog-first-healthy",
        "implicit-first",
        "quoted-equals",
    ),
)
def test_migration_143_round6_search_path(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
    post: bool,
) -> None:
    """Routine and session paths never govern the guard's own builtin resolution.

    A surviving function whose name and signature can stand in for a builtin
    (``public.set_config`` under a path naming public before pg_catalog, or a
    more specific ``public.jsonb_build_array`` overload that PostgreSQL ranks
    above the catalog's variadic one even under ``pg_catalog, public``) must
    change nothing: the guard runs under a single-schema path, so the scanner
    still sees every token and the validator still runs. A broken body refuses
    on the body; a healthy body applies unless R3 refuses its runtime setting
    change. The paths themselves are not refused.
    """
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        broken = case.endswith("broken")
        path = (
            "public, pg_catalog"
            if case.startswith("shadow") or case == "session-path"
            else (
                "pg_catalog, public"
                if case.startswith("catalog-first") or case == "overload-broken"
                else ('"a=b", public' if case == "quoted-equals" else "public")
            )
        )
        if case == "quoted-equals":
            _sql(dbname, 'CREATE SCHEMA "a=b"')
        if case.startswith("shadow"):
            # R3 now refuses this runtime setting change before validation.
            _sql(
                dbname,
                "CREATE FUNCTION public.set_config(text,text,boolean) RETURNS text "
                "LANGUAGE sql AS $$SELECT "
                "pg_catalog.set_config('check_function_bodies','off',true)$$; "
                "COMMENT ON FUNCTION public.set_config(text,text,boolean) "
                "IS '813 builtin stand-in regression'",
            )
        if case == "overload-broken":
            # Signature ranking, not schema order: this overload beats the
            # catalog's variadic jsonb_build_array for a single jsonb argument.
            _sql(
                dbname,
                "CREATE FUNCTION public.jsonb_build_array(jsonb) RETURNS jsonb "
                "LANGUAGE sql AS $$SELECT '[]'::jsonb$$; "
                "COMMENT ON FUNCTION public.jsonb_build_array(jsonb) "
                "IS '813 builtin overload regression'",
            )
            body = "BEGIN EXECUTE 'SELECT 1 FROM public.items'; END"
            language, result = "plpgsql", "void"
        else:
            body = (
                "SELECT missing_column FROM public.characters" if broken else "SELECT 1"
            )
            language, result = "sql", "integer"
        _sql(
            dbname,
            "SET LOCAL check_function_bodies=off; "
            f"CREATE FUNCTION public.probe813_path() RETURNS {result} "
            f"LANGUAGE {language} SET search_path={path} AS $$ {body} $$; "
            "COMMENT ON FUNCTION public.probe813_path() "
            "IS '813 effective-path regression'",
        )
        if case == "session-path":
            _sql(dbname, f'ALTER DATABASE "{dbname}" SET search_path=public,pg_catalog')
        refuses = broken or case.startswith("shadow")
        before = _snapshot(dbname, surviving=not refuses)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        routine_before = _routine_outcome(dbname, "SELECT public.probe813_path()")
        caplog.clear()
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_catalog.current_setting('search_path')")
            original_path = cur.fetchone()
            cur.execute(
                "SELECT s FROM pg_catalog.unnest(pg_catalog.current_schemas(true)) s "
                "WHERE s OPERATOR(pg_catalog.!~) '^pg_temp'"
            )
            assert (cur.fetchall()[0][0] == "pg_catalog") is (case != "session-path")
            applied = migrate.apply_migration(
                conn, "143", "drop_dead_schema_strata", MIGRATION
            )
            if applied:
                _old_verdict(
                    dbname,
                    case,
                    "SELECT public.probe813_path()",
                    routine_before,
                    target=case == "overload-broken",
                    already_broken=broken and case != "overload-broken",
                )
            assert applied is not refuses, caplog.text
            cur.execute("SELECT pg_catalog.current_setting('search_path')")
            assert cur.fetchone() == original_path
            if not refuses:
                _post_state(cur)
                cur.execute("SELECT public.probe813_path()")
                assert cur.fetchone() == (1,)
        if refuses:
            scanner = case == "overload-broken" or case.startswith("shadow")
            _defense(caplog.text, "scanner" if scanner else "validator")
            if case.startswith("shadow"):
                assert "public.set_config(text, text, boolean)" in caplog.text
                assert (
                    "unresolved runtime environment change: set_config" in caplog.text
                )
            else:
                assert "probe813_path" in caplog.text, caplog.text
                assert ("public.items" if scanner else "missing_column") in caplog.text
            assert "search_path places a schema" not in caplog.text
            assert _stamps(dbname) == stamps
        assert _snapshot(dbname, surviving=not refuses) == before
        assert _function_catalog(dbname) == functions


NONEMPTY = {
    "items": "INSERT INTO items(type,summary,name) VALUES ('tool','probe','813 probe')",
    "ai_notebook": "INSERT INTO ai_notebook(log_entry,agent) VALUES ('probe','LORE')",
}
EXTERNAL = {
    "view": (
        "CREATE VIEW public.probe813 AS SELECT * FROM ai_notebook; CO"
        "MMENT ON VIEW public.probe813 IS '813 dependency probe'"
    ),
    "foreign-key": (
        "CREATE TABLE public.probe813 (id bigint REFERENCES "
        "items(id)); COMMENT ON TABLE public.probe813 IS '813 FK "
        "probe'; COMMENT ON COLUMN public.probe813.id IS 'Target "
        "reference'; COMMENT ON CONSTRAINT probe813_id_fkey ON "
        "public.probe813 IS '813 inbound FK consumer'"
    ),
    "sequence-default": (
        "CREATE TABLE public.probe813 (id bigint DEFAULT nextval('ite"
        "ms_id_seq')); COMMENT ON TABLE public.probe813 IS '813 seque"
        "nce probe'; COMMENT ON COLUMN public.probe813.id IS 'Externa"
        "l consumer'"
    ),
    "domain": (
        "CREATE DOMAIN public.probe813 AS public.trait; COMMENT ON DO"
        "MAIN public.probe813 IS '813 domain probe'"
    ),
    "array-column": (
        "CREATE TABLE public.probe813 (value public.entity_type[]); C"
        "OMMENT ON TABLE public.probe813 IS '813 array probe'; COMMEN"
        "T ON COLUMN public.probe813.value IS 'Enum array consumer'"
    ),
    "argument": (
        "CREATE FUNCTION public.probe813(public.item_type) RETURNS te"
        "xt LANGUAGE sql AS 'SELECT $1::text'; COMMENT ON FUNCTION pu"
        "blic.probe813(public.item_type) IS '813 argument probe'"
    ),
    "result": (
        "CREATE FUNCTION public.probe813() RETURNS public.item_type L"
        "ANGUAGE sql AS $$SELECT 'tool'::public.item_type$$; COMMENT "
        "ON FUNCTION public.probe813() IS '813 result probe'"
    ),
    "trigger": (
        "CREATE TRIGGER probe813 BEFORE UPDATE ON items FOR EACH ROW "
        "EXECUTE FUNCTION set_updated_at(); COMMENT ON TRIGGER probe8"
        "13 ON items IS '813 trigger probe'"
    ),
}
IDENTITY = {
    "missing": ("DROP TABLE public.items", "items"),
    "view": (
        (
            "DROP TABLE public.items; CREATE VIEW public.items AS SELECT "
            "1 AS id; COMMENT ON VIEW public.items IS '813 wrongly typed "
            "target'"
        ),
        "items",
    ),
    "detached": ("ALTER SEQUENCE public.items_id_seq OWNED BY NONE", "items_id_seq"),
    "reassigned": (
        "ALTER SEQUENCE public.items_id_seq OWNED BY public.characters.id",
        "items_id_seq",
    ),
}
HIDDEN = {
    "sql-array-cast": "SELECT NULL::public._item_type::text",
    "sql-quoted-array-cast": 'SELECT NULL::"public"."_item_type"::text',
    "sql-row-array-cast": "SELECT NULL::public._items::text",
    "sql-typed-literal": (
        "SELECT (emotional_valence '+2|friendly')::text "
        "FROM public.character_relationships"
    ),
    "sql-catalog-cast": "SELECT CAST('public.items' AS regclass)::oid",
    "sql-catalog-cast-parentheses": (
        "SELECT CAST((('public.items')) AS pg_catalog.regclass)::oid"
    ),
    "sql-catalog-parentheses": "SELECT (('public.items'))::regclass::oid",
    "sql-catalog-regtype": "SELECT CAST('public._item_type' AS regtype)::oid",
    "sql-catalog-computed-format": "SELECT format('%I', input)::regclass::oid",
    "sql-catalog-computed-concat": ("SELECT CAST('public.' || input AS regclass)::oid"),
    "sql-catalog-computed-column": (
        "SELECT CAST(name AS regclass)::oid FROM public.characters"
    ),
    "sql-catalog-computed-parameter": "SELECT CAST(input AS regclass)::oid",
    "sql-catalog-computed-suffix": "SELECT input::regclass::oid",
    "sql-catalog-computed-parentheses": ("SELECT ('public.' || input)::regclass::oid"),
    "unicode-identifier": r'BEGIN PERFORM NULL::U&"item\005ftype"; RETURN; END',
    "computed-path": (
        "BEGIN PERFORM set_config('SEARCH_'||'PATH','assets,public',true); "
        "RETURN; END"
    ),
    "set-path": "BEGIN SET LOCAL search_path=assets,public; RETURN; END",
    "set-config-path": (
        "BEGIN PERFORM set_config('search_path','assets,public',true); " "RETURN; END"
    ),
    "procedure": "BEGIN PERFORM id FROM public.items; END",
    "sql-atomic": "BEGIN ATOMIC SELECT count(*) FROM public.items; END",
    "sql-query": "SELECT count(*) FROM public.items",
    "sql-cast": "SELECT 'tool'::public.item_type::text",
    "query": "BEGIN PERFORM id FROM public.items; RETURN; END",
    "quoted-cast": """BEGIN PERFORM 'tool'::"public"."item_type"; RETURN; END""",
    "cast-as": "BEGIN PERFORM CAST('tool' AS public.item_type); RETURN; END",
    "declaration": "DECLARE v public.item_type; BEGIN RETURN; END",
    "percent-type": "DECLARE v public.ai_notebook.agent%TYPE; BEGIN RETURN; END",
    "percent-rowtype": "DECLARE v public.items%ROWTYPE; BEGIN RETURN; END",
    "concat": "BEGIN EXECUTE 'SELECT NULL::public.' || 'item_' || 'type'; RETURN; END",
    "format": (
        "BEGIN EXECUTE format('SELECT NULL::%I.%I', 'public', 'item_'"
        " || 'type'); RETURN; END"
    ),
    "unresolved": "BEGIN EXECUTE input; RETURN; END",
    "sequence-body": "BEGIN PERFORM nextval('public.items_id_seq'); RETURN; END",
    "regtype": "BEGIN PERFORM 'public.item_type'::regtype; RETURN; END",
}
# All catalog input forms must classify literals and refuse computed operands.
CATALOG_TYPES = (
    "regclass",
    "regtype",
    "regproc",
    "regprocedure",
    "regoper",
    "regoperator",
    "regconfig",
    "regdictionary",
    "regnamespace",
    "regrole",
    "regcollation",
)
for catalog in CATALOG_TYPES:
    for form, expression in {
        "typed": f"{catalog} 'public.items'",
        "call": f"pg_catalog.{catalog}('public.items')",
        "computed-call": f"pg_catalog.{catalog}(input)",
        "computed-cast": f"CAST(input AS {catalog})",
        "computed-suffix": f"input::{catalog}",
        "computed-lookup": f"pg_catalog.to_{catalog}(input)",
    }.items():
        # Some reg* types have no to_reg* SQL function; check_function_bodies=off
        # deliberately plants their unsupported form to prove fail-closed refusal.
        HIDDEN[f"sql-catalog-{catalog}-{form}"] = f"SELECT ({expression})::oid"

LITERAL_FORMS = {
    "ordinary": "'+2|friendly'",
    "escaped": r"E'+2|frien\x64ly'",
    "unicode": "U&'+2|friendly'",
    "unicode-escape": "U&'+2|frien!0064ly' UESCAPE '!'",
    "national": "N'+2|friendly'",
    "binary": "B'101'",
    "hex": "X'aa'",
    "dollar": "$$+2|friendly$$",
    "tagged": "$lit$+2|friendly$lit$",
    "adjacent": "'+2|'\n'friendly'",
    "unknown": "unknown'+2|friendly'",
}
for form, literal in LITERAL_FORMS.items():
    HIDDEN[f"sql-literal-{form}"] = (
        f"SELECT (public.emotional_valence {literal})::text "
        "FROM public.character_relationships AS public"
    )

REFUSALS = (
    *("nonempty:" + key for key in NONEMPTY),
    *("external:" + key for key in EXTERNAL),
    *("identity:" + key for key in IDENTITY),
    *("hidden:" + key for key in HIDDEN),
)


def _refusal(dbname: str, case: str, caplog: pytest.LogCaptureFixture) -> None:
    group, name = case.split(":")
    if group == "nonempty":
        statement, offender = NONEMPTY[name], name
    elif group == "external":
        statement, offender = EXTERNAL[name], "probe813"
    elif group == "identity":
        statement, offender = IDENTITY[name]
    else:
        signature = "input text" if name == "unresolved" or "computed" in name else ""
        language = "sql" if name.startswith("sql-") else "plpgsql"
        result_type = {
            "sql-query": "bigint",
            "sql-atomic": "bigint",
            "sql-cast": "text",
        }.get(
            name,
            (
                "oid"
                if "catalog" in name
                else "text" if name.startswith("sql-") else "void"
            ),
        )
        statement = (
            f"CREATE FUNCTION public.probe813({signature}) "
            f"RETURNS {result_type} LANGUAGE {language} "
            f"AS $probe${HIDDEN[name]}$probe$; "
            f"COMMENT ON FUNCTION public.probe813({'text' if signature else ''}) "
            "IS '813 hidden consumer'"
        )
        if name == "procedure":
            statement = (
                "CREATE PROCEDURE public.probe813() LANGUAGE plpgsql "
                f"AS $probe${HIDDEN[name]}$probe$; "
                "COMMENT ON PROCEDURE public.probe813() IS '813 procedure probe'"
            )
        elif name == "sql-atomic":
            statement = (
                "CREATE FUNCTION public.probe813() RETURNS bigint LANGUAGE sql "
                f"{HIDDEN[name]}; "
                "COMMENT ON FUNCTION public.probe813() IS '813 parsed SQL probe'"
            )
        offender = "probe813"
    _sql(dbname, "SET LOCAL check_function_bodies=off; " + statement)
    before = _snapshot(dbname, surviving=False)
    caplog.clear()
    assert not _apply(dbname), case
    assert offender in caplog.text, caplog.text
    assert "target public." in caplog.text, caplog.text
    _defense(
        caplog.text,
        (
            "validator"
            if group == "hidden" and name == "sql-literal-unknown"
            else (
                "scanner"
                if group == "hidden" and name != "sql-atomic"
                else (
                    "catalog"
                    if group == "external" or name == "sql-atomic"
                    else "manifest"
                )
            )
        ),
    )
    expected_reference = {
        "sql-array-cast": "public._item_type",
        "sql-quoted-array-cast": "public._item_type",
        "sql-row-array-cast": "public._items",
        "sql-typed-literal": "emotional_valence",
        "sql-catalog-cast": "public.items",
        "sql-catalog-cast-parentheses": "public.items",
        "sql-catalog-parentheses": "public.items",
        "sql-catalog-regtype": "public._item_type",
    }.get(name)
    if expected_reference:
        assert expected_reference in caplog.text, caplog.text
    if "computed" in name and group == "hidden":
        assert "unresolved" in caplog.text, caplog.text
    assert (
        _snapshot(dbname, surviving=False) == before
    ), "partial migration or changed row/comment"
    assert all(s[0] != "143" for s in _stamps(dbname))


@pytest.mark.parametrize("table", NONEMPTY)
def test_migration_143_refuses_nonempty_table_atomically(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    table: str,
) -> None:
    """A valid target row survives the runner's rollback with every object."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _refusal(dbname, "nonempty:" + table, caplog)


@pytest.mark.parametrize("probe", EXTERNAL)
def test_migration_143_refuses_external_dependency_atomically(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    probe: str,
) -> None:
    """Catalog consumers, including automatic/internal edges, block retirement."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _refusal(dbname, "external:" + probe, caplog)


@pytest.mark.parametrize("probe", IDENTITY)
def test_migration_143_refuses_wrong_identity_or_ownership(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    probe: str,
) -> None:
    """Never treat a missing, wrongly typed, or detached target as permission."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _refusal(dbname, "identity:" + probe, caplog)


@pytest.mark.parametrize("probe", HIDDEN)
def test_migration_143_refuses_hidden_body_reference(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    probe: str,
) -> None:
    """Actual SQL/PLpgSQL bodies exercise the lexer, type contexts and EXECUTE."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _refusal(dbname, "hidden:" + probe, caplog)


def _lock_refusal(dbname: str, caplog: pytest.LogCaptureFixture) -> None:
    before, stamps = _snapshot(dbname, surviving=False), _stamps(dbname)
    with closing(connect(dbname)) as blocker, blocker.cursor() as cur:
        cur.execute("LOCK TABLE public.items IN ACCESS SHARE MODE")
        caplog.clear()
        assert not _apply(dbname)
        _defense(caplog.text, "lock")
        assert "lock timeout" in caplog.text, caplog.text
        blocker.rollback()
    assert _snapshot(dbname, surviving=False) == before
    assert _stamps(dbname) == stamps
    assert all(s[0] != "143" for s in stamps)


def test_migration_143_refuses_conflicting_lock_atomically(
    archives: dict[str, Path], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A real competing transaction hits the five-second bound and rolls back."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _lock_refusal(dbname, caplog)


def _column_consumers(dbname: str) -> None:
    _sql(
        dbname,
        "CREATE FUNCTION public.probe813_columns() RETURNS SETOF text "
        "LANGUAGE sql AS $$SELECT cr.emotional_valence::text "
        "FROM public.character_relationships cr$$; "
        "COMMENT ON FUNCTION public.probe813_columns() IS '813 varchar alias'; "
        "CREATE FUNCTION public.probe813_bare() RETURNS SETOF text "
        "LANGUAGE sql AS $$SELECT emotional_valence "
        "FROM public.character_relationships$$; "
        "COMMENT ON FUNCTION public.probe813_bare() IS '813 varchar column'; "
        "CREATE FUNCTION public.probe813_where() RETURNS SETOF integer LANGUAGE sql "
        "AS $$SELECT 1 FROM public.character_relationships "
        "WHERE emotional_valence = '+2|friendly'$$; "
        "COMMENT ON FUNCTION public.probe813_where() IS '813 WHERE column'; "
        "CREATE FUNCTION public.probe813_group() RETURNS SETOF text LANGUAGE sql "
        "AS $$SELECT emotional_valence FROM public.character_relationships "
        "GROUP BY emotional_valence HAVING emotional_valence = '+2|friendly' "
        "ORDER BY emotional_valence$$; "
        "COMMENT ON FUNCTION public.probe813_group() IS '813 HAVING ORDER column'; "
        "CREATE FUNCTION public.probe813_argument() RETURNS SETOF text LANGUAGE sql "
        "AS $$SELECT upper(emotional_valence) FROM public.character_relationships$$; "
        "COMMENT ON FUNCTION public.probe813_argument() IS '813 argument column'; "
        "CREATE FUNCTION public.probe813_percent() RETURNS void LANGUAGE plpgsql "
        "AS $$DECLARE v public.character_relationships.emotional_valence%TYPE; "
        "BEGIN RETURN; END$$; "
        "COMMENT ON FUNCTION public.probe813_percent() "
        "IS '813 unrelated percent type'; "
        "CREATE FUNCTION public.probe813_dynamic() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN EXECUTE "
        "pg_catalog.format('SELECT %L','character_relationships'); END$$; "
        "COMMENT ON FUNCTION public.probe813_dynamic() IS '813 constant safe SQL'; "
        "CREATE TYPE assets.item_type AS ENUM ('other'); "
        "COMMENT ON TYPE assets.item_type IS '813 namespace shadow'; "
        "CREATE FUNCTION public.probe813_shadow() RETURNS text LANGUAGE sql "
        "SET search_path=assets,public AS $$SELECT 'other'::item_type::text$$; "
        "COMMENT ON FUNCTION public.probe813_shadow() IS '813 effective search path'; "
        "REVOKE ALL ON FUNCTION public.probe813_where() FROM PUBLIC; "
        "GRANT EXECUTE ON FUNCTION public.probe813_where() TO CURRENT_USER",
    )


def _catalog_consumers(dbname: str) -> None:
    _sql(
        dbname,
        "CREATE FUNCTION public.probe813_catalog() RETURNS oid LANGUAGE sql "
        "AS $$SELECT CAST('public.characters' AS regclass)::oid$$; "
        "COMMENT ON FUNCTION public.probe813_catalog() IS '813 surviving CAST'; "
        "CREATE FUNCTION public.probe813_parentheses() RETURNS oid LANGUAGE sql "
        "AS $$SELECT (('public.places'))::pg_catalog.regclass::oid$$; "
        "COMMENT ON FUNCTION public.probe813_parentheses() "
        "IS '813 surviving parenthesized catalog cast'; "
        "CREATE FUNCTION public.probe813_cast_parentheses() RETURNS oid "
        "LANGUAGE sql AS $$SELECT CAST((('public.characters')) "
        "AS pg_catalog.regclass)::oid$$; "
        "COMMENT ON FUNCTION public.probe813_cast_parentheses() "
        "IS '813 surviving parenthesized CAST'; "
        "CREATE FUNCTION public.probe813_regproc() RETURNS oid LANGUAGE sql "
        "AS $$SELECT CAST('public.set_updated_at' AS regproc)::oid$$; "
        "COMMENT ON FUNCTION public.probe813_regproc() IS '813 surviving regproc'; "
        "CREATE FUNCTION public.probe813_regprocedure() RETURNS oid LANGUAGE sql "
        "AS $$SELECT ('public.set_updated_at()')::regprocedure::oid$$; "
        "COMMENT ON FUNCTION public.probe813_regprocedure() "
        "IS '813 surviving regprocedure'",
    )
    literals = {
        "regclass": "public.characters",
        "regtype": "text",
        "regproc": "public.set_updated_at",
        "regprocedure": "public.set_updated_at()",
        "regoper": "+",
        "regoperator": "+(integer,integer)",
        "regconfig": "english",
        "regdictionary": "english_stem",
        "regnamespace": "public",
        "regrole": "CURRENT_USER",
        "regcollation": '"C"',
    }
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT current_user")
        literals["regrole"] = cur.fetchone()[0]
        for catalog, literal in literals.items():
            if catalog == "regoper":
                # Unqualified + is overloaded; select one uniquely named operator.
                cur.execute(
                    "SELECT oid::regoper::text FROM pg_operator "
                    "WHERE oprname IN (SELECT oprname FROM pg_operator "
                    "GROUP BY oprname HAVING count(*)=1) LIMIT 1"
                )
                literal = cur.fetchone()[0]
            for form, expression in {
                "typed": f"pg_catalog.{catalog} '{literal}'",
                "call": f"pg_catalog.{catalog}('{literal}')",
                "cast": f"CAST('{literal}' AS pg_catalog.{catalog})",
                "suffix": f"'{literal}'::pg_catalog.{catalog}",
            }.items():
                function = f"probe813_{catalog}_{form}"
                cur.execute(
                    f"CREATE FUNCTION public.{function}() RETURNS oid "
                    f"LANGUAGE sql AS $probe$SELECT ({expression})::oid$probe$; "
                    f"COMMENT ON FUNCTION public.{function}() IS "
                    "'813 surviving catalog literal'"
                )


def _catalog_results(dbname: str) -> None:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT probe813_catalog()='public.characters'::regclass::oid, "
            "probe813_parentheses()='public.places'::regclass::oid, "
            "probe813_cast_parentheses()='public.characters'::regclass::oid, "
            "probe813_regproc()='public.set_updated_at'::regproc::oid, "
            "probe813_regprocedure()='public.set_updated_at()'::regprocedure::oid"
        )
        assert cur.fetchone() == (True, True, True, True, True)


def _relationship(dbname: str) -> None:
    seed_protagonist(dbname)
    one, _ = seed_character(dbname, name="813 One")
    two, _ = seed_character(dbname, name="813 Two")
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SET LOCAL nexus.write_producer='manual'")
        cur.execute(
            (
                "INSERT INTO character_relationships(character1_id,character2"
                "_id,relationship_type,emotional_valence,dynamic,recent_event"
                "s,history) VALUES (%s,%s,'friend','+2|friendly','guard probe"
                "','none','probe') RETURNING valence_current,emotional_valenc"
                "e"
            ),
            (one, two),
        )
        value, literal = cur.fetchone()
        assert float(value) == pytest.approx(2 / 5.5)
        assert literal == "+2|friendly"
        cur.execute(
            "SELECT EXISTS(SELECT FROM public.probe813_where()), "
            "EXISTS(SELECT FROM public.probe813_group() "
            "WHERE probe813_group='+2|friendly')"
        )
        assert cur.fetchone() == (True, True)
        cur.execute("SAVEPOINT invalid_literal")
        with pytest.raises(Exception, match="Unparseable emotional_valence"):
            cur.execute(
                (
                    "UPDATE character_relationships SET emotional_valence='invali"
                    "d' WHERE character1_id=%s AND character2_id=%s"
                ),
                (one, two),
            )
        cur.execute("ROLLBACK TO SAVEPOINT invalid_literal")


def _deferred(dbname: str) -> None:
    _sql(
        dbname,
        (
            "CREATE FUNCTION public.probe813() RETURNS bigint LANGUAGE sq"
            "l AS $$SELECT id FROM public.hybrid_search('probe'::text, NU"
            "LL::bytea, 0::double precision, 1::double precision, 1::inte"
            "ger, 'unused'::text)$$; COMMENT ON FUNCTION public.probe813("
            ") IS '813 deferred function consumer; never executes a searc"
            "h'"
        ),
    )
    before = _snapshot(dbname, surviving=True)
    assert _apply(dbname)
    assert _snapshot(dbname, surviving=True) == before


def _transition(dbname: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
    from nexus.api.new_story_flow import build_transition_data_from_cache
    from tests.test_orrery.test_retrograde_constraints_pg import (
        BASE_TIMESTAMP,
        _hydrate_fixture,
    )

    seed_protagonist(dbname, base_timestamp=BASE_TIMESTAMP)
    route_slot_to_disposable(monkeypatch.setattr, slot=3, dbname=dbname)
    try:
        cache = _hydrate_fixture(dbname)
        transition = build_transition_data_from_cache(cache)
        result = NewStoryDatabaseMapper(dbname=dbname).perform_transition(transition)
        assert result
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                (
                    "SELECT c.name,p.name FROM global_variables g JOIN characters"
                    " c ON c.id=g.user_character JOIN places p ON p.id=c.current_"
                    "location WHERE g.id=true"
                )
            )
            assert cur.fetchone() == (
                transition.character.name,
                transition.location.name,
            )
    finally:
        close_all_pools()


@pytest.mark.parametrize(
    "case", (*REFUSALS, "lock", "relationship", "catalog", "deferred", "transition")
)
def test_migration_143_regressions_work_from_post143_clone(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """Reconstruct on a fresh complete post-143 clone, then repeat every case."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        assert _apply(dbname)
        before, stamps = _snapshot(dbname, surviving=True), _stamps(dbname)
        _load_fixture(dbname)
        assert _snapshot(dbname, surviving=True) == before
        assert _stamps(dbname) == [s for s in stamps if s[0] != "143"]
        if case in REFUSALS:
            _refusal(dbname, case, caplog)
        elif case == "lock":
            _lock_refusal(dbname, caplog)
        elif case == "deferred":
            _deferred(dbname)
        else:
            if case == "relationship":
                _column_consumers(dbname)
            if case == "catalog":
                _catalog_consumers(dbname)
            assert _apply(dbname)
            if case == "catalog":
                _catalog_results(dbname)
            elif case == "relationship":
                _relationship(dbname)
            else:
                _transition(dbname, monkeypatch)


def test_migration_143_accepts_live_relationship_column_names(
    archives: dict[str, Path], tmp_path: Path
) -> None:
    """Keep varchar fields, diagnostic strings, and the real deriving trigger."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _column_consumers(dbname)
        before = _snapshot(dbname, surviving=True)
        functions = _function_catalog(dbname)
        assert _apply(dbname)
        assert _snapshot(dbname, surviving=True) == before
        assert _function_catalog(dbname) == functions
        _relationship(dbname)


def test_migration_143_accepts_surviving_catalog_casts(
    archives: dict[str, Path], tmp_path: Path
) -> None:
    """Surviving catalog literals pass CAST and parenthesized :: forms."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _catalog_consumers(dbname)
        before = _snapshot(dbname, surviving=True)
        functions = _function_catalog(dbname)
        assert _apply(dbname)
        assert _snapshot(dbname, surviving=True) == before
        assert _function_catalog(dbname) == functions
        _catalog_results(dbname)


def test_migration_143_preserves_deferred_function_consumers(
    archives: dict[str, Path], tmp_path: Path
) -> None:
    """A real hybrid_search caller stays intact alongside all six overloads."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _deferred(dbname)


def test_new_story_transition_after_migration_143(
    archives: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real normalized cache-to-transition path persists player and location."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        assert _apply(dbname)
        _transition(dbname, monkeypatch)


@pytest.mark.parametrize("post", (False, True))
@pytest.mark.parametrize(
    "body",
    (
        "SELECT count(*) FROM public.items",
        "DECLARE v public.item_type; BEGIN RETURN; END",
    ),
)
def test_migration_143_validation_refuses_without_scanner(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    body: str,
    post: bool,
) -> None:
    """The language validators refuse SQL references and PLpgSQL declarations."""
    language, result = (
        ("sql", "bigint") if body.startswith("SELECT") else ("plpgsql", "void")
    )
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        if post:
            before = _snapshot(dbname, surviving=True)
            stamps = _stamps(dbname)
            assert _apply(dbname)
            _load_fixture(dbname)
            assert _snapshot(dbname, surviving=True) == before
            assert _stamps(dbname) == stamps
        _sql(
            dbname,
            f"CREATE FUNCTION public.probe813() RETURNS {result} "
            f"LANGUAGE {language} AS $probe${body}$probe$; "
            "COMMENT ON FUNCTION public.probe813() IS '813 independent defense'; "
            "REVOKE ALL ON FUNCTION public.probe813() FROM PUBLIC; "
            "GRANT EXECUTE ON FUNCTION public.probe813() TO CURRENT_USER",
        )
        scratch = tmp_path / MIGRATION.name
        sql = MIGRATION.read_text()
        sql, removed = re.subn(
            r"^                    PERFORM pg_temp.dead143_body\(f.prosrc,.*;\n",
            "",
            sql,
            flags=re.MULTILINE,
        )
        assert removed == 1
        scratch.write_text(sql)
        before, functions = _snapshot(dbname, surviving=False), _function_catalog(
            dbname
        )
        caplog.clear()
        with closing(connect(dbname)) as conn:
            assert not migrate.apply_migration(
                conn, "143", "drop_dead_schema_strata", scratch
            )
        _defense(caplog.text, "validator")
        assert "probe813" in caplog.text and "post-drop" in caplog.text, caplog.text
        assert _snapshot(dbname, surviving=False) == before
        assert _function_catalog(dbname) == functions
        assert all(s[0] != "143" for s in _stamps(dbname))


@pytest.mark.parametrize(
    "state", ("partial-pre", "drifted-pre", "partial-post", "drifted-post")
)
def test_pre143_fixture_refuses_partial_or_drifted_clone(
    archives: dict[str, Path],
    tmp_path: Path,
    state: str,
) -> None:
    """The guarded loader never repairs unexpected state or loses a stamp."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        if state.endswith("post"):
            assert _apply(dbname)
        statements = {
            "partial-pre": "DROP TABLE public.items",
            "drifted-pre": "COMMENT ON COLUMN public.items.id IS '813 drift probe'",
            "partial-post": (
                "CREATE TYPE public.trait AS ENUM ('probe'); "
                "COMMENT ON TYPE public.trait IS '813 partial probe'"
            ),
            "drifted-post": (
                "COMMENT ON FUNCTION public.set_updated_at() IS '813 drift probe'"
            ),
        }
        _sql(dbname, statements[state])
        before, stamps = _snapshot(dbname, surviving=False), _stamps(dbname)
        with pytest.raises(Exception):
            _load_fixture(dbname)
        assert _snapshot(dbname, surviving=False) == before
        assert _stamps(dbname) == stamps


ROUND3_LITERALS = {
    "continued-cr-items": (
        "BEGIN RETURN 'public.it' -- diagnostic\r 'ems'::regclass::oid; END",
        "public.items",
    ),
    "continued-chain-items": (
        "BEGIN RETURN 'public.it' -- first\r\n -- second\r -- "
        "third\n 'ems'::regclass::oid; END",
        "public.items",
    ),
    "continued-vtab-items": (
        "BEGIN RETURN 'public.it'\v -- diagnostic\n 'ems'::regclass::oid; END",
        "public.items",
    ),
    "continued-escape-items": (
        "BEGIN RETURN E'public.\\x69t' -- diagnostic\n 'ems'::regclass::oid; END",
        "public.items",
    ),
    "cr-items": (
        "BEGIN -- diagnostic\r RETURN 'public.items'::regclass::oid; END",
        "public.items",
    ),
    "cr-item-type": (
        "BEGIN -- diagnostic\r RETURN 'public.item_type'::regtype::oid; END",
        "public.item_type",
    ),
    "continued-items": (
        "BEGIN RETURN 'public.it' -- diagnostic\n 'ems'::regclass::oid; END",
        "public.items",
    ),
    "continued-item-type": (
        "BEGIN RETURN 'public.it' -- diagnostic\n 'em_type'::regtype::oid; END",
        "public.item_type",
    ),
    "cr-survivor": (
        "BEGIN -- diagnostic\r RETURN 'public.ems'::regclass::oid; END",
        "public.ems",
    ),
    "continued-survivor": (
        "BEGIN RETURN 'public.e' -- diagnostic\n 'ms'::regclass::oid; END",
        "public.ems",
    ),
    "block-separated": (
        "BEGIN RETURN length('public.it' /* diagnostic\n */ || 'ems')::oid; END",
        None,
    ),
}


def _round3_prepare(dbname: str, post: bool) -> None:
    """Load the frozen closure, optionally reconstructing after real retirement."""
    _load_fixture(dbname)
    if post:
        before, stamps = _snapshot(dbname, surviving=True), _stamps(dbname)
        assert _apply(dbname)
        _load_fixture(dbname)
        assert _snapshot(dbname, surviving=True) == before
        assert _stamps(dbname) == stamps


@pytest.mark.parametrize("post", (False, True))
@pytest.mark.parametrize("case", ROUND3_LITERALS)
def test_migration_143_round3_literal_grammar(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
    post: bool,
) -> None:
    """Real PLpgSQL references agree with PostgreSQL's CR/comment continuation."""
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        body, reference = ROUND3_LITERALS[case]
        _sql(
            dbname,
            "CREATE TABLE public.ems(id integer); "
            "COMMENT ON TABLE public.ems IS '813 surviving suffix relation'; "
            "COMMENT ON COLUMN public.ems.id IS '813 surviving probe identity'; "
            "CREATE TYPE public.em_type AS ENUM ('probe'); "
            "COMMENT ON TYPE public.em_type IS '813 surviving suffix type'; "
            "CREATE FUNCTION public.probe813() RETURNS oid LANGUAGE plpgsql "
            f"AS $probe${body}$probe$; "
            "COMMENT ON FUNCTION public.probe813() IS '813 round-three lexer probe'",
        )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            if reference is None:
                # The scanner sees two strings and ||, with no catalog cast.
                # The resulting text is diagnostic data, not a regclass use.
                cur.execute("SELECT public.probe813()")
                assert cur.fetchone() == (len("public.items"),)
                with pytest.raises(psycopg2.errors.SyntaxError):
                    cur.execute("SELECT 'public.it' /* diagnostic\n */ 'ems'")
            else:
                catalog_type = "regtype" if "type" in reference else "regclass"
                cur.execute(
                    f"SELECT public.probe813(), %s::{catalog_type}::oid", (reference,)
                )
                actual, expected = cur.fetchone()
                assert actual == expected
        refuses = reference in ("public.items", "public.item_type")
        before = _snapshot(dbname, surviving=not refuses)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        routine_before = _routine_outcome(dbname, "SELECT public.probe813()")
        caplog.clear()
        applied = _apply(dbname)
        if applied:
            _old_verdict(
                dbname, case, "SELECT public.probe813()", routine_before, target=refuses
            )
        assert applied is not refuses, caplog.text
        if refuses:
            _defense(caplog.text, "scanner")
            assert reference is not None
            assert "probe813" in caplog.text and reference in caplog.text, caplog.text
            assert _stamps(dbname) == stamps
        else:
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                _post_state(cur)
                cur.execute(
                    "SELECT to_regclass('public.ems'),to_regtype('public.em_type')"
                )
                assert all(cur.fetchone())
        assert _snapshot(dbname, surviving=not refuses) == before
        assert _function_catalog(dbname) == functions


@pytest.mark.parametrize("post", (False, True))
def test_migration_143_round3_validator_settings(
    archives: dict[str, Path],
    tmp_path: Path,
    post: bool,
) -> None:
    """DateStyle and all SET entries apply then restore in the runner session."""
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        require_disposable_target(dbname)
        with closing(connect(dbname)) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f"ALTER DATABASE \"{dbname}\" SET DateStyle = 'ISO, MDY'")
        _sql(
            dbname,
            "CREATE FUNCTION public.probe813_date() RETURNS date LANGUAGE sql "
            "SET DateStyle='ISO, DMY' SET search_path=public,pg_catalog "
            "SET application_name='a=b' AS $$SELECT DATE '31/12/2026'$$; "
            "COMMENT ON FUNCTION public.probe813_date() IS '813 DMY "
            "validation environment'; "
            "REVOKE ALL ON FUNCTION public.probe813_date() FROM PUBLIC; "
            "GRANT EXECUTE ON FUNCTION public.probe813_date() TO CURRENT_USER; "
            "CREATE FUNCTION public.probe813_next() RETURNS date LANGUAGE sql "
            "AS $$SELECT DATE '12/31/2026'$$; "
            "COMMENT ON FUNCTION public.probe813_next() IS '813 MDY "
            "validation after DMY'",
        )
        before, functions = _snapshot(dbname, surviving=True), _function_catalog(dbname)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT current_setting('DateStyle'),current_setting('search_path')"
            )
            settings = cur.fetchone()
            assert settings[0] == "ISO, MDY"
            cur.execute("SELECT set_config('application_name','maintenance',false)")
            conn.commit()
            assert migrate.apply_migration(
                conn, "143", "drop_dead_schema_strata", MIGRATION
            )
            cur.execute(
                "SELECT current_setting('DateStyle'),current_setting('search_path')"
            )
            assert cur.fetchone() == settings
            cur.execute("SELECT current_setting('application_name')")
            assert cur.fetchone() == ("maintenance",)
        assert _snapshot(dbname, surviving=True) == before
        assert _function_catalog(dbname) == functions


@pytest.mark.parametrize("post", (False, True))
def test_migration_143_round3_invalid_setting_refuses(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    post: bool,
) -> None:
    """A vanished text-search SET target refuses with its routine named."""
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        _sql(
            dbname,
            "CREATE TEXT SEARCH CONFIGURATION "
            "public.probe813_config (COPY=pg_catalog.english); "
            "COMMENT ON TEXT SEARCH CONFIGURATION "
            "public.probe813_config IS '813 SET dependency'; "
            "CREATE FUNCTION public.probe813_setting() RETURNS integer LANGUAGE sql "
            "SET default_text_search_config='public.probe813_config' AS $$SELECT 1$$; "
            "COMMENT ON FUNCTION public.probe813_setting() IS '813 "
            "vanished SET target'; "
            "DROP TEXT SEARCH CONFIGURATION public.probe813_config RESTRICT",
        )
        before, functions, stamps = (
            _snapshot(dbname, surviving=False),
            _function_catalog(dbname),
            _stamps(dbname),
        )
        caplog.clear()
        assert not _apply(dbname), caplog.text
        _defense(caplog.text, "scanner")
        assert "probe813_setting" in caplog.text, caplog.text
        assert "probe813_config" in caplog.text, caplog.text
        assert _snapshot(dbname, surviving=False) == before
        assert _function_catalog(dbname) == functions
        assert _stamps(dbname) == stamps


ROUND4_LITERALS = {
    "unicode-gap": (
        "BEGIN RETURN U&'public.items' /* gap */ UESCAPE 'z'::regclass::oid; END"
    ),
    "unicode-argument-gap": (
        "BEGIN RETURN U&'public.items' UESCAPE /* gap */ 'z'::regclass::oid; END"
    ),
    "unicode-comment": "BEGIN /* uescape */ RETURN 'public.z'::regclass::oid; END",
    "unicode-string": "BEGIN PERFORM 'uEsCaPe'; RETURN 'public.z'::regclass::oid; END",
    "unicode-identifier": 'BEGIN RETURN (SELECT U&"id"::oid FROM public.z); END',
    "escaped-unicode": r"BEGIN RETURN E'public.\u007a'::regclass::oid; END",
}


@pytest.mark.parametrize("post", (False, True))
@pytest.mark.parametrize("case", ROUND4_LITERALS)
def test_migration_143_round4_unicode_forms(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
    post: bool,
) -> None:
    """Unicode forms refuse even in comments/data; E-string decoding stays valid."""
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        _sql(
            dbname,
            "CREATE TABLE public.z(id integer); "
            "COMMENT ON TABLE public.z IS '813 surviving Unicode suffix'; "
            "COMMENT ON COLUMN public.z.id IS '813 surviving probe value'; "
            "INSERT INTO public.z VALUES (1); "
            "CREATE FUNCTION public.probe813_unicode() RETURNS oid LANGUAGE plpgsql "
            f"AS $probe${ROUND4_LITERALS[case]}$probe$; "
            "COMMENT ON FUNCTION public.probe813_unicode() IS '813 raw-form refusal'",
        )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT public.probe813_unicode()")
            actual = cur.fetchone()[0]
            reference = "public.items" if case.endswith("gap") else "public.z"
            if case == "unicode-identifier":
                assert actual == 1
            else:
                cur.execute("SELECT %s::regclass::oid", (reference,))
                assert cur.fetchone() == (actual,)
        refuses = case != "escaped-unicode"
        before = _snapshot(dbname, surviving=not refuses)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        routine_before = _routine_outcome(dbname, "SELECT public.probe813_unicode()")
        caplog.clear()
        applied = _apply(dbname)
        if applied:
            _old_verdict(
                dbname,
                case,
                "SELECT public.probe813_unicode()",
                routine_before,
                target=case.endswith("gap"),
            )
        assert applied is not refuses, caplog.text
        if refuses:
            _defense(caplog.text, "scanner")
            assert "probe813_unicode" in caplog.text, caplog.text
            assert (
                "unicode-escape literal or identifier; edit the routine" in caplog.text
            )
            assert _stamps(dbname) == stamps
        else:
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                _post_state(cur)
                cur.execute(
                    "SELECT public.probe813_unicode(), 'public.z'::regclass::oid"
                )
                actual, expected = cur.fetchone()
                assert actual == expected
        assert _snapshot(dbname, surviving=not refuses) == before
        assert _function_catalog(dbname) == functions


@pytest.mark.parametrize("post", (False, True))
@pytest.mark.parametrize("case", ("session-authorization", "search-path"))
def test_migration_143_round4_validator_scope(
    archives: dict[str, Path], tmp_path: Path, case: str, post: bool
) -> None:
    """Native GUC unwind restores privilege and embedded-equals path settings."""
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        role = dbname + "_role"
        created_role = False
        try:
            if case == "session-authorization":
                _sql(dbname, f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER')
                created_role = True
                clauses = (
                    "SET client_min_messages='notice' "
                    f"SET session_authorization='{role}'"
                )
            else:
                _sql(
                    dbname,
                    'CREATE SCHEMA "a=b"; '
                    "COMMENT ON SCHEMA \"a=b\" IS '813 path probe'",
                )
                clauses = 'SET search_path="a=b",public'
            _sql(
                dbname,
                "CREATE FUNCTION public.probe813_scope() RETURNS integer LANGUAGE sql "
                f"{clauses} AS $$SELECT 1$$; "
                "COMMENT ON FUNCTION public.probe813_scope() IS '813 SET scope probe'",
            )
            before = _snapshot(dbname, surviving=True)
            functions = _function_catalog(dbname)
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                settings_sql = (
                    "SELECT current_setting('session_authorization'),"
                    "current_setting('role'),"
                    "current_setting('client_min_messages'),current_setting('se"
                    "arch_path')"
                )
                cur.execute(settings_sql)
                settings = cur.fetchone()
                cur.execute("SELECT public.probe813_scope()")
                assert cur.fetchone() == (1,)
                cur.execute(settings_sql)
                assert cur.fetchone() == settings
                # Load both validator libraries before the snapshot, so their
                # GUC registration does not change the inventory being compared.
                cur.execute("SELECT '[1]'::vector; DO $$BEGIN NULL; END$$")
                # Include every maintenance-session GUC, not just named probes.
                cur.execute("SELECT name,setting FROM pg_settings ORDER BY name")
                all_settings = cur.fetchall()
                conn.commit()
                assert migrate.apply_migration(
                    conn, "143", "drop_dead_schema_strata", MIGRATION
                )
                cur.execute(settings_sql)
                assert cur.fetchone() == settings
                cur.execute("SELECT name,setting FROM pg_settings ORDER BY name")
                assert cur.fetchall() == all_settings
                _post_state(cur)
            assert _snapshot(dbname, surviving=True) == before
            assert _function_catalog(dbname) == functions
        finally:
            if created_role:
                _sql(dbname, f'DROP ROLE "{role}"')


@pytest.mark.parametrize("post", (False, True))
@pytest.mark.parametrize("case", ("broken-body", "healthy-body"))
def test_migration_143_round5_routine_cannot_disable_validation(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
    post: bool,
) -> None:
    """A routine's own SET check_function_bodies=off does not skip the second line."""
    body = (
        "SELECT missing_column FROM public.characters"
        if case == "broken-body"
        else "SELECT 1"
    )
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        # check_function_bodies=off at creation lets the broken body in, exactly
        # as a legacy dump restore would; the routine then carries the setting.
        _sql(
            dbname,
            "SET LOCAL check_function_bodies = off; "
            "CREATE FUNCTION public.probe813_bodies() RETURNS integer LANGUAGE sql "
            f"SET check_function_bodies = off AS $$ {body} $$; "
            "COMMENT ON FUNCTION public.probe813_bodies() IS '813 validator-off probe'",
        )
        refuses = True
        before = _snapshot(dbname, surviving=not refuses)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        caplog.clear()
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT current_setting('check_function_bodies')")
            assert cur.fetchone() == ("on",)
            applied = migrate.apply_migration(
                conn, "143", "drop_dead_schema_strata", MIGRATION
            )
            assert applied is not refuses, caplog.text
            cur.execute("SELECT current_setting('check_function_bodies')")
            assert cur.fetchone() == ("on",)
            if not refuses:
                _post_state(cur)
                cur.execute("SELECT public.probe813_bodies()")
                assert cur.fetchone() == (1,)
        if refuses:
            _defense(caplog.text, "scanner")
            assert "probe813_bodies" in caplog.text, caplog.text
            assert (
                "unresolved environment setting: check_function_bodies" in caplog.text
            )
            assert _stamps(dbname) == stamps
        assert _snapshot(dbname, surviving=not refuses) == before
        assert _function_catalog(dbname) == functions


# (body, declarations, expected defense). None means a healthy application.
ROUND8 = {
    "scs-off": (
        r"BEGIN EXECUTE 'SELECT 1 FROM public.\151tems'; END",
        "SET search_path=pg_catalog SET standard_conforming_strings=off",
        "scanner",
    ),
    "scs-on": (
        r"BEGIN EXECUTE 'SELECT 1 FROM public.\151tems'; END",
        "SET search_path=pg_catalog SET standard_conforming_strings=on",
        None,
    ),
    "scs-off-quote": (
        r"BEGIN PERFORM 'escaped\'quote'; END",
        "SET standard_conforming_strings=off",
        None,
    ),
    "national-off": (
        r"BEGIN PERFORM N'public.\151tems'; END",
        "SET standard_conforming_strings=off",
        "scanner",
    ),
    "typed-date": ("BEGIN PERFORM date'2026-01-01'; END", "", None),
    "typed-target": ("BEGIN PERFORM item_type'weapon'; END", "", "scanner"),
    "ordinary-data": ("BEGIN PERFORM 'public.items'; END", "", "scanner"),
    "escaped-data": (r"BEGIN PERFORM E'public.\151tems'; END", "", "scanner"),
    "dollar-data": ("BEGIN PERFORM $x$public.items$x$; END", "", "scanner"),
    "national-data": ("BEGIN PERFORM N'public.items'; END", "", "scanner"),
    "relation-size": (
        "BEGIN PERFORM pg_relation_size('public.items'); END",
        "",
        "scanner",
    ),
    "regclass-variable": (
        "DECLARE x regclass := 'public.items'; BEGIN NULL; END",
        "",
        "scanner",
    ),
    "regtype-variable": (
        "DECLARE x regtype := 'public.item_type'; BEGIN NULL; END",
        "",
        "scanner",
    ),
    "index-pkey": ("BEGIN PERFORM 'public.items_pkey'; END", "", "scanner"),
    "index-name": (
        "BEGIN PERFORM 'public.items_name_key'::regclass; END",
        "",
        "scanner",
    ),
    "index-notebook": ("BEGIN PERFORM 'public.ai_notebook_pkey'; END", "", "scanner"),
    "set-schema": ("BEGIN SET SCHEMA 'public'; END", "", "scanner"),
    "set-local-schema": ("BEGIN SET LOCAL SCHEMA 'public'; END", "", "scanner"),
    "set-session-schema": ("BEGIN SET SESSION SCHEMA 'public'; END", "", "scanner"),
    "session-auth": ("BEGIN SET SESSION AUTHORIZATION DEFAULT; END", "", "scanner"),
    "update-settings": (
        "BEGIN UPDATE pg_settings SET setting='public' WHERE name='search_path'; END",
        "",
        "scanner",
    ),
    "update-qualified-settings": (
        "BEGIN UPDATE pg_catalog.pg_settings SET setting='public' "
        "WHERE name='search_path'; END",
        "",
        "scanner",
    ),
    "select-into-config": (
        "DECLARE x text; BEGIN SELECT "
        "pg_catalog.set_config('search_path','public',true) INTO x; END",
        "",
        "scanner",
    ),
    "perform-config": (
        "BEGIN PERFORM pg_catalog.set_config('role','none',true); END",
        "",
        "scanner",
    ),
    "json-returning": (
        "BEGIN PERFORM json_value('{}'::jsonb, '$' "
        "RETURNING emotional_valence) FROM public.character_relationships; END",
        "",
        "scanner",
    ),
    "dml-returning": (
        "BEGIN UPDATE public.character_relationships "
        "SET emotional_valence=emotional_valence "
        "RETURNING emotional_valence INTO STRICT v; END",
        "",
        None,
    ),
    "window-target": ("SELECT count(*) FROM public.items", "WINDOW", "scanner"),
    "window-broken": (
        "SELECT missing_column FROM public.characters",
        "WINDOW",
        "validator",
    ),
    "system-schema-broken": (
        "SELECT missing_column FROM public.characters",
        "",
        "validator",
    ),
    "window-healthy": ("SELECT 1::bigint", "WINDOW", None),
    "system-schema": ("SELECT count(*) FROM public.items", "", "scanner"),
    "exit-on-error-healthy": ("SELECT 1::bigint", "SET exit_on_error=on", "scanner"),
    "exit-on-error": (
        "SELECT missing_column FROM public.characters",
        "SET exit_on_error=on",
        "scanner",
    ),
    "runtime-data": (
        "BEGIN PERFORM pg_relation_size(input::regclass); END",
        "",
        "scanner",
    ),
}


def _defense(log: str, expected: str) -> None:
    """Distinguish catalog, scanner, validator and lock refusals explicitly."""
    if expected == "scanner":
        assert "function/procedure" in log and "refuses:" in log, log
        assert "post-drop" not in log, log
    elif expected == "validator":
        assert (
            "post-drop function/procedure" in log and "validation refuses:" in log
        ), log
    elif expected == "catalog":
        assert "unexpected dependent" in log or "unexpected dependency edge" in log, log
        assert "post-drop" not in log, log
    elif expected == "manifest":
        assert "target public." in log and "function/procedure" not in log, log
    elif expected == "lock":
        assert "lock timeout" in log, log
    else:
        raise AssertionError(expected)


@pytest.mark.parametrize("post", (False, True))
@pytest.mark.parametrize("case", ROUND8)
def test_migration_143_round8_contract(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
    post: bool,
) -> None:
    """Panel literal, context, selection and environment recipes run on real clones."""
    body, clauses, defense = ROUND8[case]
    language = (
        "sql"
        if case.startswith("window")
        or case
        in (
            "system-schema",
            "system-schema-broken",
            "exit-on-error",
            "exit-on-error-healthy",
        )
        else "plpgsql"
    )
    result = "bigint" if language == "sql" else "void"
    schema = "pg_catalog" if case.startswith("system-schema") else "public"
    signature = "input text" if case == "runtime-data" else ""
    if case == "dml-returning":
        body = "DECLARE v text; " + body
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        _sql(
            dbname,
            "SET LOCAL check_function_bodies=off; "
            f"CREATE FUNCTION {schema}.probe813_r8({signature}) RETURNS {result} "
            f"LANGUAGE {language} {clauses} AS $probe${body}$probe$; "
            f"COMMENT ON FUNCTION {schema}.probe813_r8("
            f"{'text' if signature else ''}) IS '813 round-eight recipe'",
        )
        before = _snapshot(dbname, surviving=defense is None)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        caplog.clear()
        applied = _apply(dbname)
        assert applied is (defense is None), caplog.text
        if defense:
            assert "probe813_r8" in caplog.text, caplog.text
            _defense(caplog.text, defense)
            assert _stamps(dbname) == stamps
        assert _function_catalog(dbname) == functions
        assert _snapshot(dbname, surviving=defense is None) == before


@pytest.mark.parametrize("post", (False, True))
@pytest.mark.parametrize("candidate", ("format", "concat", "operator"))
@pytest.mark.parametrize("path", ("public,pg_catalog", "pg_catalog,public"))
def test_migration_143_round8_fold_candidates(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    post: bool,
    candidate: str,
    path: str,
) -> None:
    """Even a later exact overload invalidates a builtin-only constant fold."""
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        if candidate == "operator":
            definition = (
                "CREATE FUNCTION public.probe813_concat(text,text) RETURNS text "
                "LANGUAGE sql AS $$SELECT 'SELECT 1'$$; "
                "CREATE OPERATOR public.|| (LEFTARG=text, RIGHTARG=text, "
                "FUNCTION=public.probe813_concat)"
            )
            expression = "'SELECT ' || '1'"
        else:
            definition = (
                f"CREATE FUNCTION public.{candidate}(text,text) RETURNS text "
                "LANGUAGE sql AS $$SELECT 'SELECT 1'$$"
            )
            expression = (
                "format('SELECT %s','1')"
                if candidate == "format"
                else "concat('SELECT ','1')"
            )
        _sql(
            dbname,
            definition
            + "; CREATE FUNCTION public.probe813_fold() RETURNS void LANGUAGE plpgsql "
            f"SET search_path={path} AS $probe$BEGIN EXECUTE {expression}; END$probe$; "
            "COMMENT ON FUNCTION public.probe813_fold() IS '813 fold context recipe'",
        )
        before, stamps = _snapshot(dbname, surviving=False), _stamps(dbname)
        caplog.clear()
        assert not _apply(dbname), caplog.text
        assert "noncatalog fold overloads refuse:" in caplog.text, caplog.text
        assert (
            "operator public.||"
            if candidate == "operator"
            else f"function public.{candidate}"
        ) in caplog.text
        assert _stamps(dbname) == stamps
        assert _snapshot(dbname, surviving=False) == before


@pytest.mark.parametrize("post", (False, True))
@pytest.mark.parametrize("setting", ("role", "session_authorization"))
@pytest.mark.parametrize("usage", (True, False))
def test_migration_143_round8_role_resolution(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    post: bool,
    setting: str,
    usage: bool,
) -> None:
    """USAGE filtering and $user resolve under the routine's declared role."""
    with _clone(archives, tmp_path) as dbname:
        _round3_prepare(dbname, post)
        role = dbname + "_role"
        path = '"$user",public' if usage else f'"{role}",public'
        routine = (
            "RETURNS bigint LANGUAGE sql AS $$SELECT count(*) FROM items$$"
            if usage
            else "RETURNS void LANGUAGE plpgsql "
            "AS $$BEGIN PERFORM 'items'::regclass; END$$"
        )
        # Put SET clauses before AS while preserving the literal body.
        declaration, body = routine.split(" AS ", 1)
        try:
            _sql(
                dbname,
                f'CREATE ROLE "{role}" NOLOGIN; CREATE SCHEMA "{role}"; '
                + (f'GRANT USAGE ON SCHEMA "{role}" TO "{role}"; ' if usage else "")
                + f'CREATE TABLE "{role}".items(id integer); '
                f"CREATE FUNCTION public.probe813_role() {declaration} "
                f'SET search_path={path} SET {setting}="{role}" AS {body}',
            )
            before = _snapshot(dbname, surviving=False)
            routine_before = _routine_outcome(dbname, "SELECT public.probe813_role()")
            caplog.clear()
            applied = _apply(dbname)
            assert not applied, caplog.text
            assert "probe813_role" in caplog.text, caplog.text
            if usage:
                # R6 skips identity SETs for validators. The creator's $user
                # path cannot find the role's shadow table; refuse atomically.
                _defense(caplog.text, "validator")
                assert 'relation "items" does not exist' in caplog.text
            else:
                _defense(caplog.text, "scanner")
            assert (
                _routine_outcome(dbname, "SELECT public.probe813_role()")
                == routine_before
            )
            assert _snapshot(dbname, surviving=False) == before
        finally:
            _sql(dbname, f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')


def test_migration_143_round8_validator_lock_timeout(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A routine SET lock_timeout=0 cannot suppress the migration's bound."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _sql(
            dbname,
            "CREATE TABLE public.probe813_locked(id integer); "
            "CREATE FUNCTION public.probe813_wait() RETURNS integer LANGUAGE sql "
            "SET lock_timeout=0 AS $$SELECT id FROM public.probe813_locked$$",
        )
        stamps = _stamps(dbname)
        with closing(connect(dbname)) as locker, locker.cursor() as lockcur:
            lockcur.execute(
                "LOCK TABLE public.probe813_locked IN ACCESS EXCLUSIVE MODE"
            )
            with closing(connect(dbname)) as conn:
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout='10s'")
                caplog.clear()
                start = time.monotonic()
                assert not migrate.apply_migration(
                    conn, "143", "drop_dead_schema_strata", MIGRATION
                )
                elapsed = time.monotonic() - start
                assert elapsed < 8, (elapsed, caplog.text)
                _defense(caplog.text, "scanner")
                assert (
                    "probe813_wait" in caplog.text
                    and "unresolved environment setting: lock_timeout" in caplog.text
                )
        assert _stamps(dbname) == stamps


def test_migration_143_round8_runner_recompiles(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A second pending migration validates on a fresh backend, without cache reuse."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        tree = tmp_path / "cache-proof"
        tree.mkdir()
        (tree / "901_compile.sql").write_text(
            "CREATE FUNCTION public.probe813_cached() RETURNS void LANGUAGE plpgsql "
            "AS $$DECLARE x public.agent_type; BEGIN NULL; END$$; "
            "COMMENT ON FUNCTION public.probe813_cached() IS '813 cached type recipe'; "
            "SELECT public.probe813_cached();"
        )
        second = re.sub(
            r"^                    PERFORM pg_temp.dead143_body\(f.prosrc,.*;\n",
            "",
            MIGRATION.read_text(),
            flags=re.MULTILINE,
        )
        assert second != MIGRATION.read_text()
        (tree / "902_validate.sql").write_text(second)
        caplog.clear()
        assert migrate.migrate_database(
            dbname, skip_locked=False, migrations_dir=tree
        ) == (1, 1), caplog.text
        assert (
            "probe813_cached" in caplog.text and "agent_type" in caplog.text
        ), caplog.text
        _defense(caplog.text, "validator")
        assert any(s[0] == "901" for s in _stamps(dbname))
        assert not any(s[0] == "902" for s in _stamps(dbname))


def _routine_outcome(dbname: str, call: str) -> tuple[bool, Any]:
    """Call on a fresh disposable backend and preserve success or exact failure."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        try:
            cur.execute(call)
            return True, cur.fetchone()
        except psycopg2.Error as failure:
            return False, (failure.pgcode, str(failure).splitlines()[0])


def _old_verdict(
    dbname: str,
    case: str,
    call: str,
    before: tuple[bool, Any],
    *,
    target: bool = False,
    already_broken: bool = False,
) -> None:
    """Classify already broken, newly broken, or intact from both actual calls."""
    after = _routine_outcome(dbname, call)
    if already_broken:
        assert not before[0] and not after[0], (before, after)
    elif target:
        assert before[0] and not after[0], (before, after)
        assert after[1][0] in ("42P01", "42704"), after
    else:
        assert before[0] and after[0], (before, after)
        assert before[1] == after[1], (before, after)
    verdict = (
        "already broken"
        if not before[0]
        else "newly broken" if not after[0] else "intact"
    )
    label = (
        "OLD DESTRUCTIVE VERDICT: applied (newly broken)"
        if verdict == "newly broken"
        else (
            "OLD VERDICT: applied (routine already broken)"
            if verdict == "already broken"
            else "OLD VERDICT: applied (healthy routine)"
        )
    )
    print(label, case, "before:", before, "after:", after, flush=True)


def test_migration_143_round8_environment_unwinds(
    archives: dict[str, Path], tmp_path: Path
) -> None:
    """Every scan helper restores identity and GUCs before drops in the same txn."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _sql(
            dbname,
            "CREATE FUNCTION public.probe813_unwind() RETURNS void LANGUAGE plpgsql "
            "SET search_path=pg_catalog SET role=pg_monitor "
            "SET session_authorization=pg_monitor "
            "SET standard_conforming_strings=off "
            "AS $$BEGIN EXECUTE 'SELECT 1'; END$$",
        )
        probe = """
DO $probe$
BEGIN
    RAISE NOTICE 'UNWIND %: %|%|%|%', '{phase}', current_user, session_user,
        pg_catalog.current_setting('standard_conforming_strings'),
        pg_catalog.current_setting('lock_timeout');
END
$probe$;
"""
        sql = MIGRATION.read_text()
        assert sql.count("DO $guard$") == sql.count("$guard$;") == 1
        sql = sql.replace("DO $guard$", probe.format(phase="before") + "DO $guard$")
        sql = sql.replace("$guard$;", "$guard$;" + probe.format(phase="after"))
        migration = tmp_path / "143_unwind.sql"
        migration.write_text(sql)
        with closing(connect(dbname)) as conn:
            applied = migrate.apply_migration(conn, "143", "unwind_probe", migration)
            notices = [n.strip() for n in conn.notices if "UNWIND " in n]
            assert len(notices) == 2, notices
            before = notices[0].split("UNWIND before: ")[1]
            after = notices[1].split("UNWIND after: ")[1]
            print("UNWIND before:", before, "after:", after, flush=True)
            assert before == after, notices
            assert applied
            assert before.split("|")[2:] == ["on", "5s"], notices
            with conn.cursor() as cur:
                _post_state(cur)


# Round nine recipes from panel-1098-9ed33d54 and the coordinator's clarifications.
# None requires a paid provider or a connection to an owner database.
ROUND9_DEFINITIONS = {
    "F7-ts-stat": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN PERFORM ts_stat('SELECT count(*) FROM public.items'); END$$",
        "hidden body identifier reference",
    ),
    "F7-query-to-xml-and-xmlschema": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN PERFORM query_to_xml_and_xmlschema('SELECT "
        "count(*) FROM public.items',true,false,''); END$$",
        "hidden body identifier reference",
    ),
    "F7-query-to-xmlschema": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN PERFORM query_to_xmlschema('SELECT count(*) "
        "FROM public.items',true,false,''); END$$",
        "hidden body identifier reference",
    ),
    "R2-custom-setting": (
        "CREATE FUNCTION public.probe813_r9() RETURNS integer LANGUAGE sql "
        "SET probe813.note='a=b' AS $$SELECT 1$$",
        "unresolved environment setting: probe813.note",
    ),
    "R2-log-min-messages": (
        "CREATE FUNCTION public.probe813_r9() RETURNS integer LANGUAGE sql "
        "SET log_min_messages=notice AS $$SELECT 1$$",
        "unresolved environment setting: log_min_messages",
    ),
    "F13-default-target-literal": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN EXECUTE pg_catalog.format('SELECT %L','item_type'); END$$",
        "literal names a drop target: item_type",
    ),
    "R1-default-format-control": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN EXECUTE pg_catalog.format('SELECT "
        "%L','character_relationships'); END$$",
        None,
    ),
    "R1-unreachable-format": (
        "CREATE SCHEMA probe813_shadow; CREATE FUNCTION probe813_shadow.format(text) "
        "RETURNS text LANGUAGE sql AS $$SELECT $1$$",
        "noncatalog fold overloads refuse: function probe813_shadow.format(text)",
    ),
    "R1-unreachable-concat-ws": (
        "CREATE SCHEMA probe813_shadow; CREATE FUNCTION "
        "probe813_shadow.concat_ws(text,text) "
        "RETURNS text LANGUAGE sql AS $$SELECT $2$$",
        "noncatalog fold overloads refuse: function "
        "probe813_shadow.concat_ws(text,text)",
    ),
    "R2-statement-timeout": (
        "CREATE FUNCTION public.probe813_r9() RETURNS integer LANGUAGE sql "
        "SET statement_timeout=0 AS $$SELECT 1$$",
        "unresolved environment setting: statement_timeout",
    ),
    "R2-transaction-timeout": (
        "CREATE FUNCTION public.probe813_r9() RETURNS integer LANGUAGE sql "
        "SET transaction_timeout='1s' AS $$SELECT 1$$",
        "unresolved environment setting: transaction_timeout",
    ),
    "R3-set-local": (
        r"CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE plpgsql "
        "SET search_path=pg_catalog AS $f$ DECLARE n bigint; BEGIN "
        "SET LOCAL standard_conforming_strings=off; "
        r"EXECUTE 'SELECT count(*) FROM public.\151tems' INTO n; RETURN n; END $f$",
        "unresolved runtime environment change: set",
    ),
    "R3-reset": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN RESET application_name; END$$",
        "unresolved runtime environment change: reset",
    ),
    "R3-quoted-set-config": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN PERFORM "
        "pg_catalog.\"set_config\"('application_name','x',true); "
        "END$$",
        "unresolved runtime environment change: set_config",
    ),
    "R3-update-only-settings": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql AS $$BEGIN "
        "UPDATE ONLY pg_catalog.pg_settings SET setting='public' "
        "WHERE name='search_path'; END$$",
        "unresolved runtime pg_settings mutation",
    ),
    "R4-event-trigger": (
        "CREATE TABLE public.probe813_log(tag text); "
        "CREATE FUNCTION public.probe813_ddl() RETURNS event_trigger LANGUAGE plpgsql "
        "AS $$BEGIN INSERT INTO probe813_log VALUES(tg_tag); END$$; "
        "CREATE EVENT TRIGGER probe813_event ON ddl_command_end "
        "EXECUTE FUNCTION public.probe813_ddl()",
        "enabled event triggers refuse: probe813_event",
    ),
    "R6-revoked-role": (
        "CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE sql "
        "SET role=pg_monitor AS $$SELECT 1::bigint$$; "
        "REVOKE EXECUTE ON FUNCTION public.probe813_r9() FROM PUBLIC",
        None,
    ),
    "R6-revoked-session-authorization": (
        "CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE sql "
        "SET session_authorization=pg_monitor AS $$SELECT 1::bigint$$; "
        "REVOKE EXECUTE ON FUNCTION public.probe813_r9() FROM PUBLIC",
        None,
    ),
    "F1-dollar-high-byte": (
        "CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE plpgsql AS $f$ "
        "DECLARE n bigint; BEGIN PERFORM $é$'$é$; n:=(SELECT "
        "count(*) FROM public.items); "
        "PERFORM $é$'$é$; RETURN n; END $f$",
        "hidden body identifier reference",
    ),
    "F1-identifier-dollar": (
        "CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE plpgsql AS $f$ "
        "DECLARE n bigint; BEGIN PERFORM 1 AS é$t$; n:=(SELECT "
        "count(*) FROM public.ai_notebook); "
        "PERFORM 1 AS é$t$; RETURN n; END $f$",
        "hidden body identifier reference",
    ),
    "F1-prefix-boundary": (
        'CREATE DOMAIN public."ée" AS text; '
        r"CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE plpgsql AS $f$ "
        r"DECLARE n bigint; BEGIN PERFORM éE'\';"
        "\n"
        "n:=(SELECT count(*) FROM public.items); -- '\nRETURN n; END $f$",
        "hidden body identifier reference",
    ),
    "F1-nbsp-dollar": (
        "CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE plpgsql AS $f$ "
        "DECLARE n bigint; BEGIN PERFORM 1 AS \xa0$t$; n:=(SELECT "
        "count(*) FROM public.ai_notebook); "
        "PERFORM 1 AS \u00a0$t$; RETURN n; END $f$",
        "hidden body identifier reference",
    ),
    "F1-unrelated-identifier-control": (
        "CREATE FUNCTION public.probe813_r9() RETURNS integer LANGUAGE plpgsql "
        "AS $$DECLARE été integer:=1; BEGIN RETURN été; END$$",
        None,
    ),
    "F2-three-part-data": (
        "CREATE FUNCTION public.probe813_r9() RETURNS text LANGUAGE sql "
        "AS $$SELECT 'a.b.c' || 'x'::text$$",
        None,
    ),
    "F2-target-literal-control": (
        "CREATE FUNCTION public.probe813_r9() RETURNS text "
        "LANGUAGE sql AS $$SELECT 'public.items'$$",
        "literal names a drop target: public.items",
    ),
    "F3-string-close-paren": (
        "CREATE FUNCTION public.probe813_r9() RETURNS text LANGUAGE plpgsql AS $f$ "
        "DECLARE v text; BEGIN SELECT json_value('{\"v\":\"0|neutral\"}'::jsonb, '$.v' "
        "PASSING ')' AS p RETURNING emotional_valence)::text INTO v "
        "FROM public.character_relationships; RETURN v; END $f$",
        "hidden body identifier reference",
    ),
    "F3-string-semicolon": (
        "CREATE FUNCTION public.probe813_r9() RETURNS text LANGUAGE plpgsql AS $f$ "
        "DECLARE v text; BEGIN SELECT json_value('{\"v\":\"0|neutral\"}'::jsonb, '$.v' "
        "PASSING ';' AS p RETURNING emotional_valence)::text INTO v "
        "FROM public.character_relationships; RETURN v; END $f$",
        "hidden body identifier reference",
    ),
    "F3-quoted-close-paren": (
        "CREATE FUNCTION public.probe813_r9() RETURNS text LANGUAGE plpgsql AS $f$ "
        "DECLARE v text; BEGIN SELECT json_value('{\"v\":\"0|neutral\"}'::jsonb, '$.v' "
        'PASSING 1 AS ")" RETURNING emotional_valence)::text INTO v '
        "FROM public.character_relationships; RETURN v; END $f$",
        "hidden body identifier reference",
    ),
    "F4-quoted-keyword-column": (
        'CREATE TABLE public.probe813_columns(trait text,"set" text,"order" text); '
        "CREATE FUNCTION public.probe813_r9() RETURNS text LANGUAGE plpgsql AS $$BEGIN "
        "RETURN (SELECT trait FROM public.probe813_columns WHERE "
        '"set"="order" LIMIT 1); END$$',
        None,
    ),
    "F5-record-column-definition": (
        "CREATE FUNCTION public.probe813_r9() RETURNS text LANGUAGE plpgsql AS $f$ "
        "DECLARE v text; BEGIN SELECT r.v::text INTO v FROM public.characters c "
        "JOIN public.character_relationships cr ON cr.character1_id=c.id, "
        'jsonb_to_record(\'{"v":"0|neutral"}\') AS r(v '
        "emotional_valence); RETURN v; END $f$",
        "unclassifiable column-definition list: emotional_valence",
    ),
    "F5-json-table-column-definition": (
        "CREATE FUNCTION public.probe813_r9() RETURNS text LANGUAGE plpgsql AS $f$ "
        "DECLARE v text; BEGIN SELECT jt.v::text INTO v FROM public.characters c "
        "JOIN public.character_relationships cr ON cr.character1_id=c.id, "
        "JSON_TABLE(jsonb '{\"v\":\"friend\"}', '$' COLUMNS (v "
        "relationship_type)) jt; RETURN v; END $f$",
        "unclassifiable column-definition list: relationship_type",
    ),
    "F4-F5-quoted-json-column": (
        "CREATE TABLE public.probe813_columns(item_type text); "
        "CREATE FUNCTION public.probe813_r9() RETURNS text LANGUAGE plpgsql AS $f$ "
        'BEGIN RETURN (SELECT jt."set"::text FROM public.probe813_columns, '
        'JSON_TABLE(jsonb \'{"set":"tool"}\', \'$\' COLUMNS ("set" '
        "item_type)) jt LIMIT 1); END $f$",
        "unclassifiable column-definition list: item_type",
    ),
    "F6-parameter-default": (
        "CREATE FUNCTION public.probe813_r9(k text, known boolean DEFAULT "
        "pg_input_is_valid('weapon','public.item_type')) RETURNS "
        "boolean LANGUAGE plpgsql "
        "AS $$BEGIN RETURN known; END$$",
        "literal names a drop target: public.item_type",
    ),
    "F6-aggregate-initcond": (
        "CREATE FUNCTION public.probe813_keep(acc regclass,x integer) RETURNS regclass "
        "LANGUAGE sql IMMUTABLE AS $$SELECT acc$$; CREATE "
        "AGGREGATE public.probe813_agg(integer) "
        "(sfunc=public.probe813_keep,stype=regclass,initcond='public.items')",
        "literal names a drop target: public.items",
    ),
    "F6-atomic-scs-target": (
        r"CREATE FUNCTION public.probe813_r9(x text) RETURNS text LANGUAGE sql "
        r"SET standard_conforming_strings=off BEGIN ATOMIC SELECT concat(E'\\','--',"
        "pg_input_is_valid(x,'public.item_type')); END",
        "literal names a drop target: public.item_type",
    ),
    "F6-atomic-scs-data": (
        r"CREATE FUNCTION public.probe813_r9() RETURNS text LANGUAGE sql "
        r"SET standard_conforming_strings=off BEGIN ATOMIC SELECT E'C:\\temp\\'; END",
        None,
    ),
    "F7-quoted-query-to-xml": (
        "CREATE FUNCTION public.probe813_r9() RETURNS xml LANGUAGE plpgsql "
        'AS $$BEGIN RETURN pg_catalog."query_to_xml"('
        "'SELECT count(*) FROM public.items',true,false,''); END$$",
        "hidden body identifier reference",
    ),
    "F7-query-to-xml": (
        "CREATE FUNCTION public.probe813_r9() RETURNS xml LANGUAGE plpgsql AS $$BEGIN "
        "RETURN query_to_xml('SELECT count(*) AS n FROM "
        "public.items',true,false,''); END$$",
        "hidden body identifier reference",
    ),
    "F7-sql-do": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE sql AS $f$ "
        "DO $d$ BEGIN PERFORM count(*) FROM public.ai_notebook; END $d$; $f$",
        "hidden body identifier reference",
    ),
    "F7-plpgsql-do": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql AS $f$ "
        "BEGIN DO $d$ BEGIN PERFORM count(*) FROM public.items; END $d$; END $f$",
        "hidden body identifier reference",
    ),
    "F7-nonconstant-query": (
        "CREATE FUNCTION public.probe813_r9(q text) RETURNS xml "
        "LANGUAGE plpgsql AS $$BEGIN "
        "RETURN query_to_xml(q,true,false,''); END$$",
        "unresolved dynamic EXECUTE expression",
    ),
    "F9-for-execute-loop": (
        "CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE plpgsql "
        "SET search_path=pg_catalog AS $$DECLARE r record; n bigint:=0; BEGIN "
        "FOR r IN EXECUTE 'SELECT id FROM public.characters' LOOP "
        "n:=n+1; END LOOP; RETURN n; END$$",
        None,
    ),
    "F10-case-column": (
        "CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE sql AS $$"
        "SELECT count(CASE relationship_type WHEN 'friend' THEN 1 "
        "END) FROM public.character_relationships$$",
        None,
    ),
    "F10-like-column": (
        "CREATE FUNCTION public.probe813_r9() RETURNS bigint "
        "LANGUAGE plpgsql AS $$BEGIN "
        "RETURN (SELECT count(*) FROM "
        "public.character_relationships cr WHERE "
        "cr.emotional_valence LIKE '+%'); END$$",
        None,
    ),
    "F11-cte-returning": (
        "CREATE FUNCTION public.probe813_r9() RETURNS bigint "
        "LANGUAGE plpgsql AS $$DECLARE n bigint; BEGIN "
        "WITH u AS (UPDATE public.character_relationships SET "
        "emotional_valence=emotional_valence "
        "WHERE false RETURNING emotional_valence) SELECT count(*) "
        "INTO n FROM u; RETURN n; END$$",
        None,
    ),
    "F12-view": (
        "CREATE VIEW public.probe813_view AS SELECT "
        "pg_input_is_valid('weapon','public.item_type') AS ok",
        "literal names a drop target: public.item_type",
    ),
    "F12-materialized-view": (
        "CREATE MATERIALIZED VIEW public.probe813_view AS SELECT "
        "pg_input_is_valid('weapon','public.item_type') AS ok",
        "literal names a drop target: public.item_type",
    ),
    "F12-check": (
        "CREATE TABLE public.probe813_columns(kind text "
        "CHECK(pg_input_is_valid(kind,'public.item_type')))",
        "literal names a drop target: public.item_type",
    ),
    "F12-default": (
        "CREATE TABLE public.probe813_columns(id bigint DEFAULT "
        "nextval('public.items_id_seq'::text))",
        "literal names a drop target: public.items_id_seq",
    ),
    "F12-domain": (
        "CREATE DOMAIN public.probe813_domain AS text "
        "CHECK(pg_input_is_valid(VALUE,'public.log_level_type'))",
        "literal names a drop target: public.log_level_type",
    ),
    "F12-trigger-when": (
        "CREATE TABLE public.probe813_columns(kind text,updated_at timestamptz); "
        "CREATE TRIGGER probe813_when BEFORE INSERT ON "
        "public.probe813_columns FOR EACH ROW "
        "WHEN (pg_input_is_valid(NEW.kind,'public.item_type')) "
        "EXECUTE FUNCTION public.set_updated_at()",
        "literal names a drop target: public.item_type",
    ),
    "F12-index-expression": (
        "CREATE TABLE public.probe813_columns(kind text); "
        "CREATE INDEX probe813_index ON public.probe813_columns "
        "((kind || 'public.item_type'))",
        "literal names a drop target: public.item_type",
    ),
    "F12-index-predicate": (
        "CREATE TABLE public.probe813_columns(kind text); "
        "CREATE INDEX probe813_index ON "
        "public.probe813_columns(kind) WHERE "
        "kind<>'public.item_type'",
        "literal names a drop target: public.item_type",
    ),
    "F12-policy": (
        "CREATE TABLE public.probe813_columns(kind text); "
        "CREATE POLICY probe813_policy ON public.probe813_columns "
        "USING(pg_input_is_valid(kind,'public.item_type'))",
        "literal names a drop target: public.item_type",
    ),
    "F12-generated": (
        "CREATE TABLE public.probe813_columns(kind text, note text "
        "GENERATED ALWAYS AS (kind || 'public.item_type') STORED)",
        "literal names a drop target: public.item_type",
    ),
    "F13-format-operand": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "SET search_path=pg_catalog AS $$BEGIN EXECUTE "
        "format('SELECT 1 /* %s */','public.items'); END$$",
        "literal names a drop target: public.items",
    ),
    "T1-concat-healthy": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "SET search_path=pg_catalog AS $$BEGIN EXECUTE concat('SELECT ','1'); END$$",
        None,
    ),
    "T1-concat-target-split": (
        "CREATE FUNCTION public.probe813_r9() RETURNS void LANGUAGE plpgsql "
        "SET search_path=pg_catalog AS $$BEGIN EXECUTE "
        "concat('SELECT count(*) FROM public.it','ems'); END$$",
        "hidden body identifier reference",
    ),
}


@pytest.mark.parametrize("case", ROUND9_DEFINITIONS)
def test_migration_143_round9_definitions(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    """Panel recipes exercise real catalogs; refusals leave schema,

    data and stamp intact."""
    definition, reason = ROUND9_DEFINITIONS[case]
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _sql(dbname, definition)
        before = _snapshot(dbname, surviving=reason is None)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        caplog.clear()
        applied = _apply(dbname)
        print(
            "ROUND9",
            case,
            "applied:",
            applied,
            "expected:",
            reason or "apply",
            flush=True,
        )
        assert applied is (reason is None), caplog.text
        if reason is not None:
            assert reason in caplog.text, caplog.text
            assert _stamps(dbname) == stamps
        assert _snapshot(dbname, surviving=reason is None) == before
        assert _function_catalog(dbname) == functions


@pytest.mark.parametrize("startup_scs", ("on", "off"))
def test_migration_143_round9_startup_pin(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    startup_scs: str,
) -> None:
    """Migration parsing is pinned under either startup string setting."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _sql(
            dbname,
            f'ALTER DATABASE "{dbname}" SET standard_conforming_strings={startup_scs}',
        )
        before = _snapshot(dbname, surviving=True)
        caplog.clear()
        assert _apply(dbname), caplog.text
        assert _snapshot(dbname, surviving=True) == before


def test_migration_143_round9_toast_literal(
    archives: dict[str, Path], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The actual TOAST relation name from the frozen closure is a literal target."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT reltoastrelid::regclass::text FROM pg_class WHERE "
                "oid='public.items'::regclass"
            )
            toast_name = cur.fetchone()[0]
        _sql(
            dbname,
            "CREATE FUNCTION public.probe813_r9() RETURNS bigint LANGUAGE plpgsql "
            f"AS $$BEGIN RETURN pg_catalog.pg_relation_size('{toast_name}'); END$$",
        )
        before, stamps = _snapshot(dbname, surviving=False), _stamps(dbname)
        caplog.clear()
        assert not _apply(dbname), caplog.text
        assert f"literal names a drop target: {toast_name}" in caplog.text
        assert (
            _snapshot(dbname, surviving=False) == before and _stamps(dbname) == stamps
        )


# Third-panel reproductions. Calls use fresh backends, including after an old
# acceptance, so an already compiled body cannot hide a destructive verdict.
ROUND10_DEFINITIONS: dict[str, tuple[str, str | None, str]] = {
    "array-default": (
        "CREATE FUNCTION public.probe813_r10(v regclass[] DEFAULT "
        "'{public.items,public.characters}') RETURNS bigint LANGUAGE plpgsql "
        "AS $$BEGIN RETURN pg_relation_size(v[1]); END$$",
        "literal names a drop target: public.items",
        "SELECT public.probe813_r10()",
    ),
    "array-parameter": (
        "CREATE FUNCTION public.probe813_r10() RETURNS bigint LANGUAGE plpgsql "
        "AS $$DECLARE v regclass[] := '{public.items,public.characters}'; "
        "BEGIN RETURN pg_relation_size(v[1]); END$$",
        "literal names a drop target: public.items",
        "SELECT public.probe813_r10()",
    ),
    "array-data": (
        "CREATE FUNCTION public.probe813_r10() RETURNS text LANGUAGE sql "
        "AS $$SELECT '{a,b}'::text$$",
        None,
        "SELECT public.probe813_r10()",
    ),
    "cursor-variable": (
        "CREATE FUNCTION public.probe813_r10() RETURNS xml LANGUAGE plpgsql "
        "AS $$DECLARE c refcursor; x xml; BEGIN OPEN c FOR SELECT 1 AS n; "
        "x := cursor_to_xml(c,1,true,false,''); CLOSE c; RETURN x; END$$",
        None,
        "SELECT public.probe813_r10()::text",
    ),
    "ts-rewrite-two": (
        "CREATE FUNCTION public.probe813_r10(q tsquery) RETURNS tsquery LANGUAGE sql "
        "AS $$SELECT ts_rewrite(q,'SELECT to_tsquery(''simple'', name),"
        "to_tsquery(''simple'', type) FROM public.items')$$",
        "hidden body identifier reference",
        "SELECT public.probe813_r10('sword')::text",
    ),
    "ts-rewrite-three": (
        "CREATE FUNCTION public.probe813_r10(q tsquery) RETURNS tsquery LANGUAGE sql "
        "AS $$SELECT ts_rewrite(q,'sword'::tsquery,'blade'::tsquery)$$",
        None,
        "SELECT public.probe813_r10('sword')::text",
    ),
    "update-only-parentheses": (
        "CREATE FUNCTION public.probe813_r10() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN UPDATE ONLY (pg_catalog.pg_settings) SET setting='public' "
        "WHERE name='search_path'; END$$",
        "unresolved runtime pg_settings mutation",
        "",
    ),
    "parameter-name": (
        "CREATE FUNCTION public.probe813_r10(entity_type text DEFAULT 'x') "
        "RETURNS text LANGUAGE sql AS $$SELECT $1$$",
        None,
        "SELECT public.probe813_r10()",
    ),
    "caller-default": (
        "CREATE FUNCTION public.probe813_r10(v boolean DEFAULT "
        "pg_input_is_valid('weapon','item_type')) RETURNS boolean "
        "LANGUAGE sql SET search_path=pg_catalog AS $$SELECT $1$$",
        "literal names a drop target: item_type",
        "SELECT public.probe813_r10()",
    ),
    "domain-default": (
        "CREATE DOMAIN public.probe813_domain AS boolean DEFAULT "
        "pg_input_is_valid('weapon','public.item_type'); "
        "CREATE TABLE public.probe813_table(v public.probe813_domain)",
        "object type public.probe813_domain refuses: literal names a drop target",
        "INSERT INTO public.probe813_table DEFAULT VALUES RETURNING v",
    ),
    "table-rule": (
        "CREATE TABLE public.probe813_table(v text); CREATE RULE probe813_rule "
        "AS ON INSERT TO public.probe813_table DO ALSO SELECT "
        "pg_input_is_valid(NEW.v,'public.item_type')",
        "object rule probe813_rule",
        "INSERT INTO public.probe813_table VALUES ('weapon') RETURNING v",
    ),
    "view-column": (
        "CREATE TABLE public.probe813_table(item_type text); "
        "CREATE VIEW public.probe813_view AS SELECT item_type "
        "FROM public.probe813_table",
        None,
        "SELECT count(*) FROM public.probe813_view",
    ),
    "quoted-keyword-columns": (
        'CREATE TABLE public.probe813_table("set" text,"order" text); '
        "CREATE FUNCTION public.probe813_r10() RETURNS text LANGUAGE plpgsql "
        'AS $$DECLARE "set" text; "order" text; BEGIN SELECT t."set",t."order" '
        'INTO "set","order" FROM public.probe813_table t LIMIT 1; '
        '"set" := "order"; RETURN "set"; END$$',
        None,
        "SELECT public.probe813_r10()",
    ),
}
ROUND10_DEFINITIONS["array-cast"] = (
    "CREATE FUNCTION public.probe813_r10() RETURNS bigint LANGUAGE plpgsql "
    "AS $$BEGIN RETURN pg_relation_size(('{public.items,public.characters}'"
    "::regclass[])[1]); END$$",
    "literal names a drop target: public.items",
    "SELECT public.probe813_r10()",
)
_definition, _reason, _call = ROUND10_DEFINITIONS["array-parameter"]
ROUND10_DEFINITIONS["array-dimensions"] = (
    _definition.replace("'{public.items", "'[2:3]={public.items"),
    _reason,
    _call,
)
for _body_kind in ("plpgsql", "atomic"):
    _definition, _reason, _call = ROUND10_DEFINITIONS["ts-rewrite-two"]
    if _body_kind == "plpgsql":
        _definition = _definition.replace(
            "LANGUAGE sql AS $$SELECT ", "LANGUAGE plpgsql AS $$BEGIN RETURN "
        )
        _definition = _definition.replace("')$$", "'); END$$")
    else:
        _definition = _definition.replace("AS $$", "BEGIN ATOMIC ")
        _definition = _definition.replace("$$", "; END")
    ROUND10_DEFINITIONS[f"ts-rewrite-{_body_kind}"] = (_definition, _reason, _call)

for _spelling, _source in {
    "as-alias": 'jsonb_to_record(\'{"v":"0|neutral"}\') AS r(v emotional_valence)',
    "bare-alias": 'jsonb_to_record(\'{"v":"0|neutral"}\') r(v emotional_valence)',
    "as-only": 'jsonb_to_record(\'{"v":"0|neutral"}\') AS (v emotional_valence)',
    "xml": "XMLTABLE('/r' PASSING xml '<r><v>friend</v></r>' "
    "COLUMNS v relationship_type) r",
    "xml-path": "XMLTABLE('/r' PASSING xml '<r><v>friend</v></r>' "
    "COLUMNS v relationship_type PATH 'v') r",
}.items():
    _query = (
        "SELECT r.v::text FROM public.characters c "
        "JOIN public.character_relationships cr ON cr.character1_id=c.id, " + _source
    )
    if _spelling == "as-only":
        _query = _query.replace("r.v", "jsonb_to_record.v")
    for _language in ("plpgsql", "polymorphic"):
        _definition = (
            "CREATE FUNCTION public.probe813_r10("
            + ("dummy anyelement" if _language == "polymorphic" else "")
            + ") RETURNS text LANGUAGE "
            + (
                "sql AS $$" + _query
                if _language == "polymorphic"
                else "plpgsql AS $$DECLARE v text; BEGIN "
                + _query.replace(
                    "FROM public.characters", "INTO v FROM public.characters"
                )
                + "; RETURN v; END"
            )
            + "$$"
        )
        ROUND10_DEFINITIONS[f"coldef-{_spelling}-{_language}"] = (
            _definition,
            "unclassifiable column-definition list",
            "SELECT public.probe813_r10("
            + ("1" if _language == "polymorphic" else "")
            + ")",
        )
for _form, _body in {
    "string": "LANGUAGE sql AS 'SELECT count(*) FROM public.items'",
    "atomic": "LANGUAGE sql BEGIN ATOMIC SELECT count(*) FROM public.items; END",
    "survivor": "LANGUAGE sql AS 'SELECT count(*) FROM public.characters'",
    "nonconstant": "LANGUAGE sql AS 'SELECT count(*) FROM public.' || suffix",
}.items():
    ROUND10_DEFINITIONS[f"nested-{_form}"] = (
        "CREATE FUNCTION public.probe813_r10() RETURNS bigint LANGUAGE plpgsql "
        "AS $outer$DECLARE n bigint; suffix text := 'characters'; BEGIN "
        "CREATE OR REPLACE FUNCTION pg_temp.generated() RETURNS bigint "
        + _body
        + "; SELECT pg_temp.generated() INTO n; "
        "DROP FUNCTION pg_temp.generated(); RETURN n; END$outer$",
        (
            None
            if _form == "survivor"
            else (
                "unresolved"
                if _form == "nonconstant"
                else "hidden body identifier reference"
            )
        ),
        "" if _form == "nonconstant" else "SELECT public.probe813_r10()",
    )
for _store, _definition in {
    "view": "CREATE VIEW public.probe813_view AS SELECT "
    "query_to_xml('SELECT 1 FROM public.items',true,false,'') AS x",
    "materialized-view": "CREATE MATERIALIZED VIEW public.probe813_view AS SELECT "
    "query_to_xml('SELECT 1 FROM public.items',true,false,'') AS x WITH NO DATA",
    "default": "CREATE TABLE public.probe813_table(x xml DEFAULT "
    "query_to_xml('SELECT 1 FROM public.items',true,false,''))",
    "check": "CREATE TABLE public.probe813_table(x integer CHECK "
    "(query_to_xml('SELECT 1 FROM public.items',true,false,'') IS NOT NULL))",
    "policy": "CREATE TABLE public.probe813_table(x integer); "
    "CREATE POLICY probe813_policy ON public.probe813_table USING "
    "(query_to_xml('SELECT 1 FROM public.items',true,false,'') IS NOT NULL)",
    "trigger-when": "CREATE TABLE public.probe813_table(x integer); "
    "CREATE TRIGGER probe813_trigger BEFORE UPDATE ON public.probe813_table "
    "FOR EACH ROW WHEN (query_to_xml('SELECT 1 FROM public.items',true,false,'') "
    "IS NOT NULL) EXECUTE FUNCTION public.set_updated_at()",
}.items():
    ROUND10_DEFINITIONS[f"stored-fold-{_store}"] = (
        _definition,
        "object",
        "",
    )


@pytest.mark.parametrize("case", ROUND10_DEFINITIONS)
def test_migration_143_round10_definitions(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    """Real third-panel recipes preserve catalogs or prove an old destructive apply."""
    definition, reason, call = ROUND10_DEFINITIONS[case]
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        if case == "nested-nonconstant":
            definition = "SET check_function_bodies=off; " + definition
        _sql(dbname, definition)
        outcome = _routine_outcome(dbname, call) if call else None
        if outcome:
            assert outcome[0], outcome
        before = _snapshot(dbname, surviving=reason is None)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        caplog.clear()
        applied = _apply(dbname)
        print(
            "ROUND10",
            case,
            "applied:",
            applied,
            "expected:",
            reason or "apply",
            flush=True,
        )
        if applied and reason and outcome:
            after = _routine_outcome(dbname, call)
            print("OLD OUTCOME", case, "before:", outcome, "after:", after, flush=True)
        assert applied is (reason is None), caplog.text
        if reason:
            assert reason in caplog.text, caplog.text
            assert _stamps(dbname) == stamps
        else:
            if outcome:
                assert _routine_outcome(dbname, call) == outcome
        assert _snapshot(dbname, surviving=reason is None) == before
        assert _function_catalog(dbname) == functions


@pytest.mark.parametrize("setting", ("exit_on_error", "quote_all_identifiers"))
def test_migration_143_round10_startup_pins(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    setting: str,
) -> None:
    """Guard error handling and manifest deparsing ignore these startup defaults."""
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _sql(dbname, f'ALTER DATABASE "{dbname}" SET {setting}=on')
        _sql(
            dbname,
            "CREATE FUNCTION public.probe813_r10() RETURNS text LANGUAGE sql "
            "AS $$SELECT 'not.a.valid.name'::text$$",
        )
        before = _snapshot(dbname, surviving=True)
        assert _apply(dbname), caplog.text
        assert _snapshot(dbname, surviving=True) == before
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT current_setting(%s)", (setting,))
            assert cur.fetchone() == ("on",)


@pytest.mark.parametrize("dry_run", (False, True))
def test_migration_143_round10_locked_runner(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    dry_run: bool,
) -> None:
    """Every real migration backend keeps the locked override; dry-run needs one."""
    with _clone(archives, tmp_path) as dbname:
        tree = tmp_path / "locked-proof"
        tree.mkdir()
        for version in ("901", "902"):
            (tree / f"{version}_backend.sql").write_text(
                "CREATE TABLE public.probe813_" + version + "(pid integer); "
                "COMMENT ON TABLE public.probe813_" + version + " IS '813 backend'; "
                "INSERT INTO public.probe813_" + version + " SELECT pg_backend_pid();"
            )
        stamps = _stamps(dbname)
        _sql(dbname, f'ALTER DATABASE "{dbname}" SET default_transaction_read_only=on')
        assert migrate.is_db_locked(dbname)
        caplog.clear()
        assert migrate.migrate_database(
            dbname, dry_run=dry_run, write_locked_slot=True, migrations_dir=tree
        ) == (2, 0), caplog.text
        count = caplog.text.count("session write override")
        print(
            "LOCKED RUNNER dry_run:", dry_run, "override backends:", count, flush=True
        )
        assert count == (1 if dry_run else 3), caplog.text
        if dry_run:
            assert _stamps(dbname) == stamps
        else:
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT a.pid<>b.pid FROM public.probe813_901 a, "
                    "public.probe813_902 b"
                )
                assert cur.fetchone() == (True,)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SHOW default_transaction_read_only")
            assert cur.fetchone() == ("on",)


@pytest.mark.parametrize("language", ("sql", "plpgsql"))
@pytest.mark.parametrize("form", ("filter", "predicate", "target-filter"))
def test_migration_143_round11_column_contexts(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    language: str,
    form: str,
) -> None:
    """Filters/predicates preserve column proof, including target-typed refusals."""
    target = form == "target-filter"
    query = (
        "SELECT count(*) FROM public.character_relationships cr "
        "WHERE (cr.character1_id > 0) AND (cr.emotional_valence LIKE '+%')"
        if form == "predicate"
        else "SELECT count(*) FILTER (WHERE cr.emotional_valence"
        + ("::text" if target else "")
        + " LIKE '+%') FROM "
        + ("public.probe813_columns" if target else "public.character_relationships")
        + " cr"
    )
    body = query if language == "sql" else f"BEGIN RETURN ({query}); END"
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        if target:
            _sql(
                dbname,
                "CREATE TABLE public.probe813_columns"
                "(emotional_valence public.emotional_valence)",
            )
        _sql(
            dbname,
            "CREATE FUNCTION public.probe813_r11() RETURNS bigint "
            f"LANGUAGE {language} AS $body${body}$body$",
        )
        call = "SELECT public.probe813_r11()"
        outcome = _routine_outcome(dbname, call)
        assert outcome[0], outcome
        before = _snapshot(dbname, surviving=not target)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        caplog.clear()
        if target:
            # The full dependency guard would refuse this table first. Invoke
            # the same scanner before it to isolate target-typed column proof.
            sql = MIGRATION.read_text()
            assert sql.count("DO $guard$") == 1
            probe = """
DO $column_probe$
BEGIN
    PERFORM pg_temp.dead143_body(
        (SELECT prosrc FROM pg_proc
         WHERE oid='public.probe813_r11()'::regprocedure),
        'public.probe813_r11()'::regprocedure::oid,
        ARRAY['public.emotional_valence'::regtype::oid], ARRAY[]::oid[],
        ARRAY['emotional_valence'], ARRAY['search_path'], ARRAY['public,pg_catalog']);
END
$column_probe$;
"""
            migration = tmp_path / "143_target_column.sql"
            migration.write_text(sql.replace("DO $guard$", probe + "DO $guard$"))
            with closing(connect(dbname)) as conn:
                applied = migrate.apply_migration(
                    conn, "143", "target_column_probe", migration
                )
        else:
            applied = _apply(dbname)
        print("ROUND11", form, language, "applied:", applied, flush=True)
        assert applied is (not target), caplog.text
        if target:
            assert "target-typed query column" in caplog.text, caplog.text
            assert _stamps(dbname) == stamps
        else:
            assert _routine_outcome(dbname, call) == outcome
        assert _snapshot(dbname, surviving=not target) == before
        assert _function_catalog(dbname) == functions


@pytest.mark.parametrize("language", ("sql", "plpgsql"))
@pytest.mark.parametrize("form", ("rows-alias", "interval-type", "column-alias"))
def test_migration_143_round12_column_definitions(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    language: str,
    form: str,
) -> None:
    """FROM position distinguishes keyword aliases/types from healthy aliases."""
    target = form != "column-alias"
    source = {
        "rows-alias": 'jsonb_to_record(\'{"v":"0|neutral"}\') '
        "rows(v emotional_valence)",
        "interval-type": 'jsonb_to_record(\'{"elapsed":"1 second","v":"0|neutral"}\') '
        "r(elapsed interval, v emotional_valence)",
        "column-alias": "generate_series(1,3) g(n)",
    }[form]
    value = {"rows-alias": "rows.v", "interval-type": "r.v", "column-alias": "g.n"}[
        form
    ]
    query = (
        f"SELECT {value}::text FROM public.characters c "
        "JOIN public.character_relationships cr ON cr.character1_id=c.id, " + source
    )
    body = query if language == "sql" else f"BEGIN RETURN ({query}); END"
    argument = "dummy anyelement" if language == "sql" else ""
    call = "SELECT public.probe813_r12(" + ("1" if language == "sql" else "") + ")"
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        _sql(
            dbname,
            f"CREATE FUNCTION public.probe813_r12({argument}) RETURNS text "
            f"LANGUAGE {language} AS $body${body}$body$",
        )
        outcome = _routine_outcome(dbname, call)
        assert outcome[0], outcome
        before = _snapshot(dbname, surviving=not target)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        caplog.clear()
        applied = _apply(dbname)
        print("ROUND12", form, language, "applied:", applied, flush=True)
        if applied and target:
            print(
                "OLD OUTCOME",
                form,
                language,
                "before:",
                outcome,
                "after:",
                _routine_outcome(dbname, call),
                flush=True,
            )
        assert applied is (not target), caplog.text
        if target:
            assert "unclassifiable column-definition list" in caplog.text, caplog.text
            assert _stamps(dbname) == stamps
        else:
            assert _routine_outcome(dbname, call) == outcome
        assert _snapshot(dbname, surviving=not target) == before
        assert _function_catalog(dbname) == functions


@pytest.mark.parametrize(
    "case",
    (
        "r13-set-after-body",
        "r13-set-before-body",
        "r13-language-after-body",
        "r13-persisting-inner",
        "r13-persisting-survivor",
    ),
)
def test_migration_143_round13_nested_environments(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    """Nested options refuse at either position; persisting bodies meet startup SETs."""
    persisting = case.startswith("r13-persisting-")
    survivor = case == "r13-persisting-survivor"
    routine = "probe813_r13_persist" if persisting else "probe813_r13"
    reason = (
        None
        if survivor
        else (
            "literal names a drop target: item_type"
            if persisting
            else (
                "unresolved nested routine language"
                if case == "r13-language-after-body"
                else "unresolved nested routine SET environment"
            )
        )
    )
    if persisting:
        type_name = "boolean" if survivor else "item_type"
        value = "x" if survivor else "weapon"
        body = (
            "BEGIN CREATE OR REPLACE FUNCTION public.probe813_generated() "
            f"RETURNS boolean AS $$SELECT pg_input_is_valid('{value}',"
            f"'{type_name}')$$ LANGUAGE sql; RETURN true; END"
        )
    else:
        options = {
            "r13-set-after-body": "AS $$SELECT pg_input_is_valid('weapon',"
            "'item_type')$$ LANGUAGE sql SET search_path=public",
            "r13-set-before-body": "LANGUAGE sql SET search_path=public "
            "AS $$SELECT pg_input_is_valid('weapon','item_type')$$",
            "r13-language-after-body": "AS $$return True$$ LANGUAGE plpython3u",
        }[case]
        body = (
            "DECLARE ok boolean; BEGIN CREATE FUNCTION pg_temp.generated() "
            f"RETURNS boolean {options}; SELECT pg_temp.generated() INTO ok; "
            "DROP FUNCTION pg_temp.generated(); RETURN ok; END"
        )
    call = f"SELECT public.{routine}()"
    with _clone(archives, tmp_path) as dbname:
        _load_fixture(dbname)
        if survivor:
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute("SELECT to_regtype('boolean')::oid")
                assert cur.fetchone()[0] is not None
            assert "boolean" not in TARGET_NAMES
        _sql(
            dbname,
            f"CREATE FUNCTION public.{routine}() RETURNS boolean "
            f"LANGUAGE plpgsql SET search_path=pg_catalog AS $outer${body}$outer$",
        )
        # Never materialize a persisting inner routine before the scanner decides
        # its wrapper; otherwise the top-level routine scan would mask the gap.
        outcome = None
        if not persisting and case != "r13-language-after-body":
            outcome = _routine_outcome(dbname, call)
            assert outcome == (True, (True,)), outcome
        before = _snapshot(dbname, surviving=survivor)
        functions, stamps = _function_catalog(dbname), _stamps(dbname)
        caplog.clear()
        applied = _apply(dbname)
        print("ROUND13", case, "applied:", applied, flush=True)
        if not applied:
            print("ROUND13 REFUSAL", case, caplog.text, flush=True)
        if applied and reason:
            if persisting:
                _sql(dbname, call)
                after = _routine_outcome(dbname, "SELECT public.probe813_generated()")
            elif outcome:
                after = _routine_outcome(dbname, call)
            else:
                after = None
            print("OLD OUTCOME", case, "before:", outcome, "after:", after, flush=True)
            if case in ("r13-set-after-body", "r13-persisting-inner"):
                assert after is not None and not after[0], after
                assert after[1][0] == "42704", after
        assert applied is survivor, caplog.text
        if reason:
            assert routine in caplog.text, caplog.text
            assert reason in caplog.text, caplog.text
            assert _stamps(dbname) == stamps
        else:
            assert [s for s in _stamps(dbname) if s[0] != "143"] == stamps
        assert _snapshot(dbname, surviving=survivor) == before
        assert _function_catalog(dbname) == functions
        if survivor:
            _sql(dbname, call)
            assert _routine_outcome(dbname, call) == (True, (True,))
            assert _routine_outcome(dbname, "SELECT public.probe813_generated()") == (
                True,
                (False,),
            )
