"""Issue #810: migrations own the schema; legacy scripts create no owned object.

Decision 810-Q4 moved schema ownership to migrations: a legacy script that
needs an object it no longer creates raises and names the owner. Decision
810-Q9 asked for a wide static scan with a reasoned allowlist. ``scan_ddl``
parses the Python under ``nexus/`` and ``scripts/`` with ``ast`` and reports
every string constant (f-string parts included, docstrings excluded) that
spells CREATE, ALTER or DROP of a TABLE, INDEX, TYPE, FUNCTION or EXTENSION,
every ``create_all``/``drop_all`` call, and every ``<expr>.__table__.create``
or ``.drop`` call. ``ALLOWLIST`` names each site that may keep its DDL and
why.

Gaps: a verb or object kind built at run time (concatenated from parts,
formatted in, or read from a file) is not seen, and SQL and shell files
(``scripts/*.sql``, ``scripts/*.sh``, ``migrations/``) are not scanned.

The PostgreSQL tests run each legacy script in a fresh interpreter against a
bare disposable database, so no test imports a legacy script in process
(``scripts/new_story_setup.py`` excepted: the test fixtures already import
it) and the import graph does not change.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import textwrap
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pytest

from nexus.agents.memnon.utils.embedding_tables import ensure_embedding_table
from nexus.database import database_url
from scripts import new_story_setup
from tests.pg_fixtures import connect, disposable_database

REPO_ROOT = Path(__file__).resolve().parents[1]

_DDL = re.compile(
    r"\b(CREATE|ALTER|DROP)\s+(?:OR\s+REPLACE\s+)?(?:UNIQUE\s+)?"
    r"(?:(?:TEMP|TEMPORARY|UNLOGGED)\s+)?(TABLE|INDEX|TYPE|FUNCTION|EXTENSION)\b",
    re.IGNORECASE,
)

_EMBEDDING_TABLES = "nexus/agents/memnon/utils/embedding_tables.py"

ALLOWLIST: Dict[tuple[str, str, str], str] = {
    (_EMBEDDING_TABLES, "_ensure_corpus_table", "CREATE TABLE"): (
        "Lazy owner of the dimension-keyed vector tables (migration 022, "
        "Decision 810-Q3); the body the three ensure_* helpers share."
    ),
    (_EMBEDDING_TABLES, "_ensure_corpus_table", "CREATE INDEX"): (
        "Lazy owner of each vector table's model index (migration 022, "
        "Decision 810-Q3); the body the three ensure_* helpers share."
    ),
    (_EMBEDDING_TABLES, "build_candidate_ann_index", "CREATE INDEX"): (
        "The only ANN path: the explicit 2560d candidate gate run by "
        "scripts/qa_shift/ann_gate.py (Decision 810-Q3)."
    ),
    (_EMBEDDING_TABLES, "drop_candidate_ann_index", "DROP INDEX"): (
        "Removes the candidate gate's own ANN index (Decision 810-Q3)."
    ),
    ("scripts/migrate.py", "ensure_tracking_table", "DROP TABLE"): (
        "The migration runner owns its schema_migrations tracking table."
    ),
    ("scripts/migrate.py", "ensure_tracking_table", "CREATE TABLE"): (
        "The migration runner owns its schema_migrations tracking table."
    ),
    ("scripts/new_story_setup.py", "initialize_slot_database", "CREATE EXTENSION"): (
        "Slot initialization installs vector and postgis before the template "
        "schema restores (Decision 810-Q9)."
    ),
    ("scripts/new_story_setup.py", "clone_slot_with_data", "CREATE EXTENSION"): (
        "Slot cloning installs vector and postgis before the source restores "
        "(Decision 810-Q9)."
    ),
    (
        "scripts/update_raw_text.py",
        "ChunkUpdater.create_backup_table",
        "CREATE TABLE",
    ): (
        "A data backup of narrative_chunks before rows are rewritten, kept by "
        "Decision 810-Q4; not schema ownership."
    ),
    ("scripts/simple_update.py", "resequence_all_chunks", "CREATE TABLE"): (
        "A session temporary table for resequencing; not schema ownership."
    ),
    ("scripts/simple_update.py", "resequence_all_chunks", "DROP TABLE"): (
        "Drops the session temporary tables it created; not schema ownership."
    ),
    ("scripts/benchmark_experience_enqueue_fence.py", "main", "DROP INDEX"): (
        "Runs on a disposable clone, then re-applies the owning migration."
    ),
    (
        "scripts/check_migration_comments.py",
        "_SqlScanner._alter_table",
        "ALTER TABLE",
    ): ("A lint label for migration findings, never executed."),
    (
        "scripts/check_migration_comments.py",
        "_SqlScanner._create_named",
        "CREATE TYPE",
    ): ("A lint label for migration findings, never executed."),
}


@dataclass(frozen=True)
class Finding:
    """One DDL site: its file, line, enclosing scope and statement kind."""

    path: str
    line: int
    scope: str
    statement: str


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Return the ids of every module, class and function docstring constant."""

    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


class _Scanner(ast.NodeVisitor):
    """Collect DDL findings for one parsed file, tracking the enclosing scope."""

    def __init__(self, path: str, docstrings: set[int]) -> None:
        self.path = path
        self.docstrings = docstrings
        self.scope: List[str] = []
        self.findings: List[Finding] = []

    def _add(self, line: int, statement: str) -> None:
        self.findings.append(
            Finding(
                path=self.path,
                line=line,
                scope=".".join(self.scope) or "<module>",
                statement=statement,
            )
        )

    def _visit_scope(self, node: Any) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_ClassDef = _visit_scope
    visit_FunctionDef = _visit_scope
    visit_AsyncFunctionDef = _visit_scope

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and id(node) not in self.docstrings:
            for match in _DDL.finditer(node.value):
                statement = f"{match.group(1).upper()} {match.group(2).upper()}"
                line = node.lineno + node.value.count("\n", 0, match.start())
                self._add(line, statement)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "create_all":
                self._add(node.lineno, "CREATE TABLE")
            elif func.attr == "drop_all":
                self._add(node.lineno, "DROP TABLE")
            elif (
                func.attr in {"create", "drop"}
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "__table__"
            ):
                self._add(
                    node.lineno,
                    "CREATE TABLE" if func.attr == "create" else "DROP TABLE",
                )
        self.generic_visit(node)


def scan_ddl(root: Path, paths: Iterable[str]) -> list[Finding]:
    """Return every DDL site in the Python files ``paths`` under ``root``.

    Args:
        root: The directory the relative ``paths`` resolve against.
        paths: Repository-relative ``.py`` paths to parse.

    Returns:
        Findings in path and line order.
    """

    findings: List[Finding] = []
    for relative in paths:
        source = (root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        scanner = _Scanner(relative, _docstring_nodes(tree))
        scanner.visit(tree)
        findings.extend(scanner.findings)
    return sorted(findings, key=lambda f: (f.path, f.line, f.statement))


def unowned(findings: Iterable[Finding]) -> list[Finding]:
    """Return the findings that no ``ALLOWLIST`` entry covers."""

    return [
        finding
        for finding in findings
        if (finding.path, finding.scope, finding.statement) not in ALLOWLIST
    ]


def _tree_paths() -> list[str]:
    """Return the tracked Python files under ``nexus/`` and ``scripts/``."""

    listed = subprocess.run(
        ["git", "ls-files", "--", "nexus", "scripts"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [path for path in listed if path.endswith(".py")]


def _describe(findings: Iterable[Finding]) -> str:
    return "\n".join(f"{f.path}:{f.line} {f.scope} {f.statement}" for f in findings)


def test_tree_has_no_unowned_ddl() -> None:
    """No Python under nexus/ or scripts/ spells DDL outside the allowlist."""

    stray = unowned(scan_ddl(REPO_ROOT, _tree_paths()))
    assert (
        not stray
    ), "DDL outside migrations and the reasoned allowlist:\n" + _describe(stray)


def test_every_allowlist_entry_matches_a_site() -> None:
    """Each allowlist entry still names a real DDL site."""

    sites = {(f.path, f.scope, f.statement) for f in scan_ddl(REPO_ROOT, _tree_paths())}
    stale = sorted(key for key in ALLOWLIST if key not in sites)
    assert not stale, f"Allowlist entries with no matching site: {stale}"


def _plant(tmp_path: Path, relative: str, source: str) -> list[Finding]:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(source), encoding="utf-8")
    return scan_ddl(tmp_path, [relative])


@pytest.mark.parametrize(
    ("source", "statement"),
    [
        ('cur.execute("CREATE INDEX IF NOT EXISTS x ON t (c)")\n', "CREATE INDEX"),
        ("sql = \"CREATE TYPE s.e AS ENUM ('a')\"\n", "CREATE TYPE"),
        ('sql = "DROP TABLE t"\n', "DROP TABLE"),
        ('sql = f"ALTER TABLE {name} ADD COLUMN c int"\n', "ALTER TABLE"),
        ('sql = "create or replace function f() returns int"\n', "CREATE FUNCTION"),
        ('sql = "CREATE EXTENSION IF NOT EXISTS vector"\n', "CREATE EXTENSION"),
        ("Base.metadata.create_all(engine)\n", "CREATE TABLE"),
        ("Model.__table__.drop(engine)\n", "DROP TABLE"),
    ],
)
def test_scan_flags_planted_ddl(tmp_path: Path, source: str, statement: str) -> None:
    """Every covered verb and kind, and both ORM call shapes, are found."""

    findings = _plant(tmp_path, "scripts/planted.py", source)
    assert [(f.statement, f.scope, f.line) for f in findings] == [
        (statement, "<module>", 1)
    ]


def test_scan_ignores_docstrings_and_comments(tmp_path: Path) -> None:
    """A docstring and a comment holding DDL text are not findings."""

    findings = _plant(
        tmp_path,
        "scripts/planted.py",
        '''
        """CREATE TABLE t"""


        def run():
            """CREATE TABLE t"""
            # CREATE TABLE t
            return None
        ''',
    )
    assert findings == []


def test_allowlist_is_scoped_to_its_function(tmp_path: Path) -> None:
    """An allowlisted statement in another function of the same file fails."""

    findings = _plant(
        tmp_path,
        "scripts/new_story_setup.py",
        """
        def initialize_slot_database():
            run("CREATE EXTENSION IF NOT EXISTS vector;")


        def create_assets_tables():
            run("CREATE TABLE IF NOT EXISTS assets.new_story_creator (id boolean)")
        """,
    )
    assert [(f.scope, f.statement) for f in findings] == [
        ("initialize_slot_database", "CREATE EXTENSION"),
        ("create_assets_tables", "CREATE TABLE"),
    ]
    assert [(f.scope, f.statement) for f in unowned(findings)] == [
        ("create_assets_tables", "CREATE TABLE")
    ]


# --- PostgreSQL: the legacy scripts refuse instead of creating ---------------

_MODEL = "bge-large"
_DIMENSIONS = 1024
_MIGRATE_HINT = "Apply migrations with scripts/migrate.py."
_VECTOR_MESSAGE = (
    "Missing vector extension; migration 022 "
    "(migrations/022_compound_embedding_pk_lazy_tables.sql) owns it. " + _MIGRATE_HINT
)
_SCENE_MESSAGE = (
    "Missing chunk_metadata.scene; migration 138 "
    "(migrations/138_adopt_unowned_fleet_indexes.sql) owns it. " + _MIGRATE_HINT
)
_ASSETS_MESSAGE = (
    "Missing assets.new_story_creator; migration 007 "
    "(migrations/007_normalize_new_story_creator.sql) owns it. " + _MIGRATE_HINT
)


def _baseline_message(table: str) -> str:
    return (
        f"Missing public.{table}; it is baseline schema "
        "(migrations/001_baseline.sql), copied from NEXUS_template by "
        "scripts/new_story_setup.py."
    )


def _ann_message(table: str, dimensions: int) -> str:
    return (
        f"No ANN index exists on {table}, and this script no longer creates one: "
        "the only ANN path is the explicit 2560d candidate gate "
        "(build_candidate_ann_index, run by scripts/qa_shift/ann_gate.py), and "
        f"#812 owns the legacy {dimensions}d tables and their indexes."
    )


_PROBE = r"""
import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import psycopg2

from nexus.database import url_connection_kwargs

script, call, url = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("probe_script", Path(script))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

result = None
model_load_calls = []
try:
    if call == "require_scene_column":
        conn = psycopg2.connect(**url_connection_kwargs(url))
        try:
            result = module.require_scene_column(conn)
        finally:
            conn.close()
    elif call == "migrate_provider_names":
        module.DB_URL = url
        result = module.migrate()
    elif call == "narrative_importer":
        module.NarrativeImporter(url)
    elif call == "create_vector_index":
        result = module.create_vector_indexes("bge-large", url)
    elif call == "regenerator_indexes":
        regenerator = module.EmbeddingRegenerator(
            "bge-large", db_url=url, ensure_table=False, load_model=False
        )
        result = regenerator.create_vector_indexes()
    elif call == "regenerator":
        module.EmbeddingRegenerator("bge-large", db_url=url, load_model=False)
    elif call.startswith("regenerator_precheck"):
        def record_model_load(name):
            model_load_calls.append(name)
            return object()
        module.ModelLoader.load_model = staticmethod(record_model_load)
        if call == "regenerator_precheck_chunk":
            result = module.regenerate_specific_chunk(
                "bge-large", 1, db_url=url, create_indexes=True
            )
        elif call in ("regenerator_precheck_resume", "regenerator_precheck_resume_cli"):
            missing = Path("resume.txt")
            missing.write_text("1\n")
            if call.endswith("_cli"):
                sys.argv = [script, "--model", "bge-large", "--resume-from",
                            str(missing), "--db-url", url, "--create-indexes",
                            "--truncate-table"]
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    try:
                        module.main()
                    except SystemExit as exc:
                        result = {"exit_code": exc.code}
                result["stdout"] = output.getvalue()
            else:
                result = module.regenerate_missing_chunks(
                    "bge-large", str(missing), db_url=url,
                    create_indexes=True, truncate_table=True
                )
        elif call == "regenerator_precheck_all":
            module.SETTINGS["models"] = {
                "bge-large": {"is_active": True},
                "e5-large": {"is_active": True},
            }
            result = module.regenerate_all_models(
                db_url=url, create_indexes=True, truncate_table=True
            )
        else:
            high_dimension = call.startswith("regenerator_precheck_high")
            model = "Octen-Embedding-4B" if high_dimension else "bge-large"
            regenerator = module.EmbeddingRegenerator(
                model, db_url=url, create_indexes=True, truncate_table=True,
                dry_run=call.endswith("_dry")
            )
            regenerator.engine.dispose()
    elif call == "season_episode_extractor":
        module.SeasonEpisodeExtractor(url)
    else:
        raise SystemExit(f"unknown probe call {call!r}")
    outcome = {"type": None, "message": "", "result": result}
except Exception as exc:
    outcome = {
        "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
        "message": str(exc),
        "result": None,
    }
if call.startswith("regenerator_precheck"):
    outcome["model_load_calls"] = model_load_calls
print(json.dumps(outcome))
"""


def _probe(script: str, call: str, dbname: str, tmp_path: Path) -> Dict[str, Any]:
    """Run one legacy-script call in a fresh interpreter against ``dbname``."""

    env = {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONPATH": str(REPO_ROOT),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE,
            str(REPO_ROOT / script),
            call,
            database_url(dbname),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        # Several scripts open log files in the working directory.
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _refused(outcome: Dict[str, Any], message: str) -> None:
    assert outcome == {
        "type": "builtins.RuntimeError",
        "message": message,
        "result": None,
    }


def _scalar(dbname: str, statement: str) -> Any:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(statement)
        row = cur.fetchone()
        return None if row is None else row[0]


def _execute(dbname: str, *statements: str) -> None:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)


def _vector_installed(dbname: str) -> bool:
    return bool(
        _scalar(dbname, "SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
    )


def _regclass(dbname: str, name: str) -> Optional[str]:
    return _scalar(dbname, f"SELECT to_regclass('{name}')::text")


@pytest.mark.requires_postgres
@pytest.mark.parametrize(
    "script", ["scripts/update_scene_numbers.py", "scripts/extract_scene_numbers.py"]
)
def test_scene_scripts_require_the_migration_138_column(
    script: str, tmp_path: Path
) -> None:
    """Both scene scripts refuse a missing column and create nothing."""

    with disposable_database("qa640_810s3_scene") as dbname:
        _execute(dbname, "CREATE TABLE public.chunk_metadata (chunk_id bigint)")

        _refused(
            _probe(script, "require_scene_column", dbname, tmp_path), _SCENE_MESSAGE
        )
        assert (
            _scalar(
                dbname,
                "SELECT count(*) FROM information_schema.columns WHERE "
                "table_schema = 'public' AND table_name = 'chunk_metadata' "
                "AND column_name = 'scene'",
            )
            == 0
        )
        assert _regclass(dbname, "public.idx_chunk_metadata_scene") is None
        assert (
            _regclass(dbname, "public.idx_chunk_metadata_season_episode_scene") is None
        )

        _execute(dbname, "ALTER TABLE public.chunk_metadata ADD COLUMN scene integer")
        assert _probe(script, "require_scene_column", dbname, tmp_path) == {
            "type": None,
            "message": "",
            "result": None,
        }


@pytest.mark.requires_postgres
def test_require_assets_tables_names_migration_007(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--create-assets checks for the migration-007 table and creates nothing."""

    monkeypatch.setattr(new_story_setup, "USE_POOL", False)
    with disposable_database("qa640_810s3_assets") as dbname:
        with pytest.raises(RuntimeError) as refused:
            new_story_setup.require_assets_tables(dbname)
        assert str(refused.value) == _ASSETS_MESSAGE
        assert _scalar(dbname, "SELECT to_regnamespace('assets')::text") is None

        _execute(
            dbname,
            "CREATE SCHEMA assets",
            "CREATE TABLE assets.new_story_creator (id boolean)",
        )
        new_story_setup.require_assets_tables(dbname)


@pytest.mark.requires_postgres
def test_provider_names_script_refuses_a_missing_enum(tmp_path: Path) -> None:
    """The provider rename alters no enum and creates no apex_audition schema."""

    with disposable_database("qa640_810s3_provider") as dbname:
        _refused(
            _probe(
                "scripts/migrate_provider_names.py",
                "migrate_provider_names",
                dbname,
                tmp_path,
            ),
            "Missing apex_audition.provider_enum values "
            "['Anthropic', 'DeepSeek', 'OpenAI']; no migration owns "
            "apex_audition.provider_enum, and this script no longer alters it. "
            "scripts/migrate.py is the only migration runner.",
        )
        assert _scalar(dbname, "SELECT to_regnamespace('apex_audition')::text") is None


@pytest.mark.requires_postgres
def test_importer_requires_its_schema(tmp_path: Path) -> None:
    """The importer installs no extension and creates or drops no table."""

    script = "scripts/import_narratives.py"
    with disposable_database("qa640_810s3_importer") as dbname:
        _refused(
            _probe(script, "narrative_importer", dbname, tmp_path), _VECTOR_MESSAGE
        )
        assert not _vector_installed(dbname)

        _execute(dbname, "CREATE EXTENSION vector")
        _refused(
            _probe(script, "narrative_importer", dbname, tmp_path),
            _baseline_message("narrative_chunks"),
        )
        assert _regclass(dbname, "public.narrative_chunks") is None


def _ann_count(dbname: str, table: str) -> int:
    return int(
        _scalar(
            dbname,
            "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public' "
            f"AND tablename = '{table}' AND indexdef ~ 'USING (hnsw|ivfflat)'",
        )
    )


@pytest.mark.requires_postgres
@pytest.mark.parametrize(
    ("script", "call"),
    [
        ("scripts/create_vector_index.py", "create_vector_index"),
        ("scripts/regenerate_embeddings.py", "regenerator_indexes"),
    ],
)
def test_ann_steps_build_no_index(script: str, call: str, tmp_path: Path) -> None:
    """Both ANN steps check for an index and never build one."""

    with disposable_database("qa640_810s3_ann") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION vector")
            cur.execute("CREATE TABLE public.narrative_chunks (id bigint PRIMARY KEY)")
            cur.execute("INSERT INTO public.narrative_chunks (id) VALUES (1)")
            table = ensure_embedding_table(cur, _DIMENSIONS)
            vector = "[" + ",".join(["0.5"] * _DIMENSIONS) + "]"
            cur.execute(
                f"INSERT INTO public.{table} (chunk_id, model, embedding) "
                "VALUES (1, %s, %s::vector)",
                (_MODEL, vector),
            )
        assert table == "chunk_embeddings_1024d"

        _refused(
            _probe(script, call, dbname, tmp_path), _ann_message(table, _DIMENSIONS)
        )
        assert _ann_count(dbname, table) == 0

        _execute(
            dbname,
            f"CREATE INDEX probe_hnsw_idx ON public.{table} "
            "USING hnsw (embedding vector_cosine_ops)",
        )
        assert _probe(script, call, dbname, tmp_path) == {
            "type": None,
            "message": "",
            "result": True,
        }


@pytest.mark.requires_postgres
@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize(
    "call",
    [
        "regenerator_precheck",
        "regenerator_precheck_dry",
        "regenerator_precheck_chunk",
        "regenerator_precheck_resume",
        "regenerator_precheck_resume_cli",
        "regenerator_precheck_all",
    ],
)
def test_requested_ann_refuses_before_model_load_or_existing_vector_deletion(
    call: str, shared: bool, tmp_path: Path
) -> None:
    """Real missing-ANN refusal precedes TRUNCATE, shared DELETE and chunk DELETE.

    Only model loading is replaced by a recording sentinel: no artifact is read
    and no inference occurs. Catalog reads and stored-row operations are real.
    """
    with disposable_database("qa640_810s3_ann_precheck") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION vector")
            cur.execute(
                "CREATE TABLE public.narrative_chunks "
                "(id bigint PRIMARY KEY, raw_text text NOT NULL)"
            )
            cur.execute("INSERT INTO public.narrative_chunks VALUES (1, 'the bell')")
            table = ensure_embedding_table(cur, _DIMENSIONS)
            vector = "[" + ",".join(["0.5"] * _DIMENSIONS) + "]"
            models = [_MODEL, "e5-large"] if shared else [_MODEL]
            for model in models:
                cur.execute(
                    f"INSERT INTO public.{table} (chunk_id, model, embedding) "
                    "VALUES (1, %s, %s::vector)",
                    (model, vector),
                )
        snapshot_sql = (
            f"SELECT jsonb_agg(to_jsonb(t) ORDER BY model) FROM public.{table} t"
        )
        before = _scalar(dbname, snapshot_sql)
        assert _ann_count(dbname, table) == 0

        outcome = _probe("scripts/regenerate_embeddings.py", call, dbname, tmp_path)
        after = _scalar(dbname, snapshot_sql)
        expected: Dict[str, Any] = {
            "type": "builtins.RuntimeError",
            "message": _ann_message(table, _DIMENSIONS),
            "result": None,
            "model_load_calls": [],
        }
        if call == "regenerator_precheck_all":
            expected = {
                "type": None,
                "message": "",
                "result": {"total": 0, "success": 0, "failed": 2},
                "model_load_calls": [],
            }
        elif call == "regenerator_precheck_resume_cli":
            expected = {
                "type": None,
                "message": "",
                "result": {
                    "exit_code": 1,
                    "stdout": f"Error: {_ann_message(table, _DIMENSIONS)}\n",
                },
                "model_load_calls": [],
            }
        assert outcome == expected and after == before, {
            "outcome": outcome,
            "existing_rows_unchanged": after == before,
        }
        assert _ann_count(dbname, table) == 0


@pytest.mark.requires_postgres
@pytest.mark.parametrize("dry_run", [False, True])
def test_requested_ann_preserves_high_dimension_exemption_and_dry_run(
    dry_run: bool, tmp_path: Path
) -> None:
    """The legacy >2000d exemption retains lazy table ownership and dry-run safety."""
    with disposable_database("qa640_810s3_ann_high") as dbname:
        _execute(dbname, "CREATE EXTENSION vector")
        _execute(dbname, "CREATE TABLE public.narrative_chunks (id bigint PRIMARY KEY)")
        call = "regenerator_precheck_high" + ("_dry" if dry_run else "")
        outcome = _probe("scripts/regenerate_embeddings.py", call, dbname, tmp_path)
        assert outcome == {
            "type": None,
            "message": "",
            "result": None,
            "model_load_calls": ["Octen-Embedding-4B"],
        }
        table = "chunk_embeddings_2560d"
        assert _regclass(dbname, "public." + table) == (None if dry_run else table)
        assert _ann_count(dbname, table) == 0


@pytest.mark.requires_postgres
def test_regenerator_requires_the_vector_extension(tmp_path: Path) -> None:
    """The regenerator installs no extension and creates no table on a bare target."""

    with disposable_database("qa640_810s3_regen") as dbname:
        _refused(
            _probe("scripts/regenerate_embeddings.py", "regenerator", dbname, tmp_path),
            _VECTOR_MESSAGE,
        )
        assert not _vector_installed(dbname)
        assert _regclass(dbname, "public.chunk_embeddings_1024d") is None


@pytest.mark.requires_postgres
def test_season_episode_extractor_requires_chunk_metadata(tmp_path: Path) -> None:
    """The extractor refuses a missing baseline table instead of creating it."""

    with disposable_database("qa640_810s3_season") as dbname:
        _refused(
            _probe(
                "scripts/extract_season_episode.py",
                "season_episode_extractor",
                dbname,
                tmp_path,
            ),
            _baseline_message("chunk_metadata"),
        )
        assert _regclass(dbname, "public.chunk_metadata") is None
