"""#813 guards on full-data disposable clones, before and after fleet landing.

Needs the frozen items/ai_notebook closure, schema_migrations, surviving public
and assets data, relationship triggers and wizard cache tables. Sources are read
ONLY by read-only pg_dump subprocesses. Every driver targets postgres or a
qa640_813_* allocation from tests.pg_fixtures. All provider pins are TEST.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

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


@pytest.fixture(scope="session")
def archives(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Cache read-only full-data source dumps; no driver opens an owner source."""
    directory = tmp_path_factory.mktemp("813-archives")
    result = {}
    for source in SOURCES:
        archive = directory / (source + ".dump")
        env = subprocess_env()
        env["PGOPTIONS"] = (
            env.get("PGOPTIONS", "") + " -c default_transaction_read_only=on"
        )
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


@pytest.mark.parametrize("source", SOURCES)
def test_migration_143_drops_only_manifest_on_each_fleet_clone(
    archives: dict[str, Path],
    tmp_path: Path,
    source: str,
) -> None:
    """Preserve full source data, all surviving definitions, and repeat-run state."""
    with _clone(archives, tmp_path, source) as dbname:
        # Frozen full-data pre-143 rehearsal is separate from reconstruction.
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM schema_migrations WHERE version='143'")
            was_post = cur.fetchone()[0] == 1
        before = _snapshot(dbname, surviving=True)
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
        assert [s for s in _stamps(dbname) if s[0] != "143"] == stamps
        assert migrate.migrate_database(dbname, skip_locked=False) == (0, 0)
        assert _snapshot(dbname, surviving=True) == before


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
        signature = "input text" if name == "unresolved" else ""
        language = "sql" if name.startswith("sql-") else "plpgsql"
        result_type = {
            "sql-query": "bigint",
            "sql-atomic": "bigint",
            "sql-cast": "text",
        }.get(name, "void")
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
    _sql(dbname, statement)
    before = _snapshot(dbname, surviving=False)
    caplog.clear()
    assert not _apply(dbname), case
    assert offender in caplog.text, caplog.text
    assert "target public." in caplog.text, caplog.text
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


def _column_consumers(dbname: str) -> None:
    _sql(
        dbname,
        "CREATE FUNCTION public.probe813_columns() RETURNS SETOF text "
        "LANGUAGE sql AS $$SELECT cr.emotional_valence::text "
        "FROM public.character_relationships cr$$; "
        "COMMENT ON FUNCTION public.probe813_columns() IS '813 varchar alias'; "
        "CREATE FUNCTION public.probe813_bare() RETURNS SETOF text "
        "LANGUAGE sql AS $$SELECT emotional_valence::text "
        "FROM public.character_relationships$$; "
        "COMMENT ON FUNCTION public.probe813_bare() IS '813 varchar column'; "
        "CREATE FUNCTION public.probe813_percent() RETURNS void LANGUAGE plpgsql "
        "AS $$DECLARE v public.character_relationships.emotional_valence%TYPE; "
        "BEGIN RETURN; END$$; "
        "COMMENT ON FUNCTION public.probe813_percent() "
        "IS '813 unrelated percent type'; "
        "CREATE FUNCTION public.probe813_dynamic() RETURNS void LANGUAGE plpgsql "
        "AS $$BEGIN EXECUTE pg_catalog.format('SELECT %L','item_type'); END$$; "
        "COMMENT ON FUNCTION public.probe813_dynamic() IS '813 constant safe SQL'; "
        "CREATE TYPE assets.item_type AS ENUM ('other'); "
        "COMMENT ON TYPE assets.item_type IS '813 namespace shadow'; "
        "CREATE FUNCTION public.probe813_shadow() RETURNS text LANGUAGE sql "
        "SET search_path=assets,public AS $$SELECT 'other'::item_type::text$$; "
        "COMMENT ON FUNCTION public.probe813_shadow() IS '813 effective search path'",
    )


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


@pytest.mark.parametrize("case", (*REFUSALS, "relationship", "deferred", "transition"))
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
        elif case == "deferred":
            _deferred(dbname)
        else:
            if case == "relationship":
                _column_consumers(dbname)
            assert _apply(dbname)
            if case == "relationship":
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
        assert _apply(dbname)
        assert _snapshot(dbname, surviving=True) == before
        _relationship(dbname)


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
