"""Offline guard: tests reach PostgreSQL only through the connection contract.

Test code resolves its server through ``nexus.database`` or ``tests.pg_fixtures``,
which delegates to it, so both honor ``[api.database]`` ahead of the PG*
environment. A literal loopback endpoint bypasses the contract, so an isolated
lane dials the owner's default server instead of its private cluster (issue
#804). So does a target assembled from PG* by hand: it honors the environment
but not a configured ``[api.database]`` server. Placeholder URLs that must
never connect name an RFC 2606 ``.invalid`` host instead of a real one.
"""

from __future__ import annotations

import ast
import functools
import getpass
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg2
import pytest
import tomlkit

from nexus.database import (
    asyncpg_kwargs,
    connection_kwargs,
    connection_target,
    url_connection_kwargs,
)
from tests import pg_fixtures

TESTS_ROOT = Path(__file__).resolve().parent
SCANNED_SUFFIXES = frozenset({".py", ".json"})


def _tree_sources(suffixes: frozenset[str]) -> list[Path]:
    """Return every test file with one of ``suffixes``, in a stable order."""
    return sorted(
        path
        for path in TESTS_ROOT.rglob("*")
        if path.suffix in suffixes and path.is_file()
    )


def _line_number(text: str, offset: int) -> int:
    """Return the 1-based line of ``offset`` in ``text``."""
    return text.count("\n", 0, offset) + 1


_LOOPBACK = r"(?:localhost|127\.0\.0\.1|\[::1\])"
OWNER_TARGET_PATTERNS = {
    "loopback host on port 5432": re.compile(_LOOPBACK + r":5432\b"),
    "port pinned to 5432": re.compile(
        r"""(?:["']port["']\s*[:,]|\bport\s*=)\s*["']?5432\b"""
    ),
    "PostgreSQL URL naming a loopback host": re.compile(
        r"postgres(?:ql)?(?:\+\w+)?://(?:[^@/\s\"']*@)?" + _LOOPBACK + r"(?![\w.-])"
    ),
}


def _owner_targets(text: str) -> list[str]:
    """Name each owner-endpoint pattern that ``text`` contains."""
    return [
        name for name, pattern in OWNER_TARGET_PATTERNS.items() if pattern.search(text)
    ]


# Known-bad spellings are split so this file stays inside its own scan.
@pytest.mark.parametrize(
    "line",
    [
        'DSN = "postgresql://pythagor@' + "localhost" + ':5432/save_01"',
        '    "port"' + ": 5432",
        "port=db_config.get('port', " + "5432)",
        "psycopg2.connect(host='127.0.0.1', port=" + "5432)",
        'db_url="postgresql://test@' + 'localhost/disposable"',
        '"postgresql+psycopg2://' + '[::1]/save_02"',
    ],
)
def test_guard_recognizes_owner_endpoint_spellings(line: str) -> None:
    """Each historical hardcoded-target form trips at least one pattern."""
    assert _owner_targets(line)


@pytest.mark.parametrize(
    "line",
    [
        'port=os.environ.get("' + 'PGPORT", "5432"),',
        "return database_url(dbname)",
        'db_url="postgresql://test@fixture.invalid/disposable"',
        'API = f"http://localhost:{port}"',
        "PGHOST=127.0.0.1 PGPORT=55432",
        '"pid": 54321',
    ],
)
def test_guard_allows_contract_and_non_postgres_spellings(line: str) -> None:
    """Only literal owner endpoints trip these patterns; PG* reads are below."""
    assert _owner_targets(line) == []


def test_tests_never_hardcode_the_owner_postgres_endpoint() -> None:
    """No test source or JSON fixture names the owner's loopback endpoint."""
    violations = [
        f"{path.relative_to(TESTS_ROOT.parent)}:{number}: {name}: {line.strip()}"
        for path in _tree_sources(SCANNED_SUFFIXES)
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        for name in _owner_targets(line)
    ]
    assert violations == [], (
        "Resolve PostgreSQL through nexus.database.database_url(), "
        "nexus.database.connection_kwargs(), or tests.pg_fixtures.connect(); "
        "use a .invalid host for URLs that never connect:\n" + "\n".join(violations)
    )


# A test that reads PG* itself builds a second resolver: it follows the
# environment but skips a configured [api.database] server. Writing the
# contract's inputs through monkeypatch.setenv stays legal. Scanned over whole
# files, so a call split across lines is still caught.
DIRECT_PG_ENVIRONMENT = re.compile(
    r"""(?:\benviron(?:\.\w+)?|\bgetenv)\s*[\[(]\s*["']PG[A-Z]*["']"""
)


# Samples are split before the name so this file stays inside its own scan.
@pytest.mark.parametrize(
    "line",
    [
        '"port": os.environ.get("' + 'PGPORT", "55432"),',
        'user = os.environ["' + 'PGUSER"]',
        'host = os.getenv("' + 'PGHOST")',
        'password=os.environ.get(\n    "' + 'PGPASSWORD"\n)',
        "f\"{os.environ.get('" + "PGHOST', 'db')}:\"",
    ],
)
def test_environment_guard_recognizes_direct_pg_reads(line: str) -> None:
    """Each way of reading a PG* variable directly trips the guard."""
    assert DIRECT_PG_ENVIRONMENT.search(line)


@pytest.mark.parametrize(
    "line",
    [
        'if story_pin is None and os.environ.get("NEXUS_RUN_LIVE_LLM") != "1":',
        "explicit ``[api.database]`` values, then the PG* environment,",
        "env=subprocess_env(),",
        'monkeypatch.setenv("PGPORT", "1")',
        'assert subprocess_env()["PGHOST"] == "configured.example"',
    ],
)
def test_environment_guard_allows_contract_spellings(line: str) -> None:
    """Other variables, prose, contract output, and setenv inputs stay legal."""
    assert DIRECT_PG_ENVIRONMENT.search(line) is None


def test_tests_never_read_the_pg_environment_directly() -> None:
    """No test module, fixture included, resolves host, port, or user from PG*."""
    reads = [
        f"{path.relative_to(TESTS_ROOT.parent)}:{_line_number(text, match.start())}:"
        f" {match.group(0)}"
        for path in _tree_sources(frozenset({".py"}))
        for text in [path.read_text()]
        for match in DIRECT_PG_ENVIRONMENT.finditer(text)
    ]
    assert reads == [], (
        "Resolve PostgreSQL through tests.pg_fixtures.connect(), "
        "nexus.database.connection_kwargs(), database_url(), or "
        "tests.pg_fixtures.asyncpg_kwargs(); give subprocesses subprocess_env():\n"
        + "\n".join(reads)
    )


# A URL that names a server (or a database on libpq's default server) is a
# hand-built target. Only a bare scheme, for a SQLAlchemy engine whose creator
# connects through the contract, and a portless RFC 2606 .invalid placeholder
# are legal.
POSTGRES_URL = re.compile(
    r"""postgres(?:ql)?(?:\+\w+)?://(?:[^@/\s"']*@)?(?P<host>[^/:?#\s"'@]*)"""
    r"""(?::(?P<port>[^/?#\s"']*))?(?P<path>/[^?#\s"']+)?"""
)


def _hand_built_urls(text: str) -> list[tuple[int, str]]:
    """Return ``(offset, url)`` for each PostgreSQL URL that names a target."""
    found = []
    for match in POSTGRES_URL.finditer(text):
        host = match["host"]
        if host:
            legal = host.endswith(".invalid") and match["port"] is None
        else:
            legal = match["port"] is None and match["path"] is None
        if not legal:
            found.append((match.start(), match.group(0)))
    return found


@pytest.mark.parametrize(
    "line",
    [
        'f"postgresql://' + '{user}@{host}:{port}/{dbname}"',
        "db_url='postgresql://" + "unused'",
        '"postgresql+psycopg2://' + 'db.example/save_02"',
        '"postgresql://' + 'pythagor@/save_01"',
        '"postgres://' + 'save_01"',
        '"postgresql://' + 'fixture.invalid:5432/save_01"',
    ],
)
def test_url_guard_recognizes_hand_built_urls(line: str) -> None:
    """A URL naming any server, or a database without one, trips the guard."""
    assert _hand_built_urls(line)


@pytest.mark.parametrize(
    "line",
    [
        'create_engine("postgresql+psycopg2://", creator=lambda: connect(db))',
        '"postgresql://fixture.invalid/"',
        'db_url="postgresql://test@fixture.invalid/disposable"',
        "engine = create_engine(database_url(dbname))",
    ],
)
def test_url_guard_allows_contract_and_placeholder_urls(line: str) -> None:
    """Bare schemes, .invalid placeholders, and contract URLs stay legal."""
    assert _hand_built_urls(line) == []


def test_tests_never_spell_a_postgres_url_with_a_target() -> None:
    """No test source or JSON fixture writes a PostgreSQL URL naming a server."""
    violations = [
        f"{path.relative_to(TESTS_ROOT.parent)}:{_line_number(text, offset)}: {url}"
        for path in _tree_sources(SCANNED_SUFFIXES)
        for text in [path.read_text()]
        for offset, url in _hand_built_urls(text)
    ]
    assert violations == [], (
        "Build PostgreSQL URLs with nexus.database.database_url(); "
        "use a .invalid host for URLs that never connect:\n" + "\n".join(violations)
    )


# Rule 3: every PostgreSQL driver call takes its target from the contract.
# Drivers are recognized by the name they resolve to through the module's
# imports and aliases (``import psycopg2 as pg``, ``from asyncpg import
# connect``, ``open_db = psycopg2.connect``, star imports) and through
# re-exports from repository modules. Each argument that can carry a server or
# database (a positional DSN or URL, ``*args``, ``**mapping``, ``dsn=``,
# ``url=``, ``connect_args=``, ``query=``) must be a direct call to a contract
# helper, or a name bound once in the same function to such a call and never
# given a target key afterwards. Target keywords (``host=``, ``dbname=``) are
# hand-built by definition. A connecting call with no target dials libpq's
# defaults, which honor PG* but not ``[api.database]``, and a driver handed on
# uncalled (``creator=psycopg2.connect``) cannot be checked; both are
# violations. Whatever the scan cannot resolve is a violation, never a pass.
@dataclass(frozen=True)
class _Driver:
    """Where one driver entry point takes its server or database."""

    first_target: int  # first positional parameter that can name a target
    connects: bool  # opens a connection, so no target means libpq's defaults


_CONNECTS = _Driver(first_target=0, connects=True)
_POOL = _Driver(first_target=2, connects=True)  # minconn and maxconn come first
_DSN_BUILDER = _Driver(first_target=0, connects=False)
_URL_BUILDER = _Driver(first_target=1, connects=False)  # drivername comes first
DRIVERS = {
    "psycopg2.connect": _CONNECTS,
    "psycopg2.extensions.make_dsn": _DSN_BUILDER,
    "psycopg2.pool.AbstractConnectionPool": _POOL,
    "psycopg2.pool.SimpleConnectionPool": _POOL,
    "psycopg2.pool.ThreadedConnectionPool": _POOL,
    "psycopg2.pool.PersistentConnectionPool": _POOL,
    "asyncpg.connect": _CONNECTS,
    "asyncpg.connection.connect": _CONNECTS,
    "asyncpg.create_pool": _CONNECTS,
    "asyncpg.pool.create_pool": _CONNECTS,
    "sqlalchemy.create_engine": _CONNECTS,
    "sqlalchemy.engine.create_engine": _CONNECTS,
    "sqlalchemy.engine.create.create_engine": _CONNECTS,
    "sqlalchemy.ext.asyncio.create_async_engine": _CONNECTS,
    "sqlalchemy.ext.asyncio.engine.create_async_engine": _CONNECTS,
    "sqlalchemy.URL": _URL_BUILDER,
    "sqlalchemy.URL.create": _URL_BUILDER,
    "sqlalchemy.engine.URL": _URL_BUILDER,
    "sqlalchemy.engine.URL.create": _URL_BUILDER,
    "sqlalchemy.engine.url.URL": _URL_BUILDER,
    "sqlalchemy.engine.url.URL.create": _URL_BUILDER,
}
TARGET_KEYWORDS = frozenset(
    {
        "host",
        "hostaddr",
        "port",
        "user",
        "username",
        "password",
        "dbname",
        "database",
        "service",
    }
)
TARGET_ARGUMENTS = frozenset({"dsn", "url"})
TARGET_MAPPINGS = frozenset({"connect_args", "query"})
_TARGET_KEYS = TARGET_KEYWORDS | TARGET_ARGUMENTS | TARGET_MAPPINGS
# The contract helpers, each with the positional arguments it takes before its
# overrides: the database (and, for get_slot_db_url, the slot) is the caller's,
# the server and role never are. tests.pg_fixtures re-exports subprocess_env
# and database_url, which resolve to their nexus.database definitions.
CONTRACT_HELPERS = {
    "tests.pg_fixtures.connect": 1,
    "tests.pg_fixtures.connection_parameters": 1,
    "tests.pg_fixtures.asyncpg_kwargs": 1,
    "tests.pg_fixtures.sqlalchemy_url": 1,
    "nexus.database.subprocess_env": 0,
    "nexus.database.connection_kwargs": 1,
    "nexus.database.asyncpg_kwargs": 1,
    "nexus.database.database_url": 1,
    "nexus.api.slot_utils.get_slot_db_url": 2,
}
TARGET_OVERRIDES = frozenset({"host", "hostaddr", "port", "user", "password"})
# Both files start two disposable clusters and dial each one by its explicit
# host and port: the conflicting environment is the point of the proof that
# the contract picks the configured cluster. Nothing else may spell a target.
DRIVER_TARGET_ALLOWLIST = frozenset(
    {"tests/test_database_contract.py", "tests/test_connection_lifecycle.py"}
)
REPO_ROOT = TESTS_ROOT.parent
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_KEYED_MUTATORS = frozenset({"setdefault", "pop"})
_MUTATORS = _KEYED_MUTATORS | {
    "update",
    "popitem",
    "clear",
    "__setitem__",
    "__delitem__",
    "__ior__",
}
_MAX_ALIAS_DEPTH = 8


def _excerpt(node: ast.AST) -> str:
    """Spell ``node`` as source, shortened for a violation line."""
    text = ast.unparse(node)
    return text if len(text) <= 60 else text[:57] + "..."


def _string(node: ast.AST | None) -> str | None:
    """Return a string literal's value; None for any other expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _plain_key(node: ast.AST | None) -> bool:
    """Whether ``node`` is a literal key that cannot name a target."""
    key = _string(node)
    return key is not None and key not in _TARGET_KEYS


def _alias_target(node: ast.Assign | ast.AnnAssign) -> ast.Name | None:
    """Return the one plain name an assignment binds, if it binds only that."""
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    if len(targets) == 1 and isinstance(targets[0], ast.Name):
        return targets[0]
    return None


class _Scope:
    """What one module, class, or function body binds each name to.

    A binding is an imported dotted name, the assignment or definition that
    binds the name, or the node of any other binding form (a parameter, loop
    target, or augmented assignment), which the scan treats as opaque.
    """

    def __init__(self, node: ast.AST, parent: _Scope | None) -> None:
        self.node = node
        self.parent = parent
        self.bindings: dict[str, list[ast.AST | str]] = {}
        self.stars: list[str] = []
        self.retargeted: set[str] = set()

    def bind(self, name: str, binding: ast.AST | str) -> None:
        """Record one more binding of ``name`` in this scope."""
        self.bindings.setdefault(name, []).append(binding)


class _ModuleIndex:
    """One module's scopes, the scope and parent of each node, and forwarders.

    A ``shallow`` index skips function and class bodies: it serves only to
    follow a production module's module-level re-exports.
    """

    def __init__(
        self, source: str, module: str, *, package: bool = False, shallow: bool = False
    ) -> None:
        self.module = module
        self.package = module if package else module.rpartition(".")[0]
        self.tree = ast.parse(source)
        self.scope_of: dict[ast.AST, _Scope] = {}
        self.parent: dict[ast.AST, ast.AST] = {}
        self.root = _Scope(self.tree, None)
        self.forwarders: dict[str, _Driver] = {}
        self._forwarders_found = shallow
        pending: list[tuple[ast.AST, ast.AST, _Scope]] = [
            (statement, self.tree, self.root) for statement in self.tree.body
        ]
        while pending:
            node, parent, scope = pending.pop()
            self.parent[node] = parent
            self.scope_of[node] = scope
            pending.extend(
                (child, node, inner)
                for child, inner in self._bind(node, scope)
                if not shallow or inner is self.root
            )

    def _bind(self, node: ast.AST, scope: _Scope) -> list[tuple[ast.AST, _Scope]]:
        """Bind the names ``node`` defines; return its children with their scopes."""
        children = list(ast.iter_child_nodes(node))
        if isinstance(node, (*_FUNCTIONS, ast.ClassDef)):
            inner = _Scope(node, scope)
            if isinstance(node, ast.ClassDef):
                body: list[ast.AST] = [*node.body]
            else:
                arguments = node.args
                for argument in (
                    *arguments.posonlyargs,
                    *arguments.args,
                    *arguments.kwonlyargs,
                    arguments.vararg,
                    arguments.kwarg,
                ):
                    if argument is not None:
                        inner.bind(argument.arg, argument)
                body = [node.body] if isinstance(node, ast.Lambda) else [*node.body]
            if not isinstance(node, ast.Lambda):
                scope.bind(node.name, node)
            inside = {id(child) for child in body}
            return [
                (child, inner if id(child) in inside else scope) for child in children
            ]
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    scope.bind(alias.asname, alias.name)
                else:
                    top = alias.name.partition(".")[0]
                    scope.bind(top, top)
            return []
        if isinstance(node, ast.ImportFrom):
            base = self._import_base(node)
            for alias in node.names:
                if alias.name == "*":
                    scope.stars.append(base)
                else:
                    scope.bind(alias.asname or alias.name, f"{base}.{alias.name}")
            return []
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            target = _alias_target(node)
            if target is not None:
                scope.bind(target.id, node)
                return [(child, scope) for child in children if child is not target]
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            scope.bind(node.id, node)
        elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
            if node.name:
                scope.bind(node.name, node)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            scope.bind(node.rest, node)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                scope.bind(name, node)
        elif (
            isinstance(node, ast.Subscript)
            and not isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and not _plain_key(node.slice)
        ):
            scope.retargeted.add(node.value.id)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.attr in _MUTATORS
            and not (
                node.func.attr in _KEYED_MUTATORS
                and node.args
                and _plain_key(node.args[0])
            )
        ):
            scope.retargeted.add(node.func.value.id)
        return [(child, scope) for child in children]

    def _import_base(self, node: ast.ImportFrom) -> str:
        """Return the absolute module an ``ImportFrom`` reads from."""
        if not node.level:
            return node.module or ""
        parts = self.package.split(".") if self.package else []
        parts = parts[: len(parts) - node.level + 1]
        return ".".join([*parts, *([node.module] if node.module else [])])

    def lookup(
        self, name: str, scope: _Scope
    ) -> tuple[_Scope, list[ast.AST | str]] | None:
        """Find the scope that binds ``name`` as seen from ``scope``."""
        current: _Scope | None = scope
        while current is not None:
            visible = current is scope or not isinstance(current.node, ast.ClassDef)
            if visible and name in current.bindings:
                return current, current.bindings[name]
            current = current.parent
        return None

    def _definition(self, name: str, scope: _Scope, node: ast.AST) -> str:
        """Name a function or class defined in this module."""
        if scope is self.root:
            return f"{self.module}.{name}"
        return f"{self.module}.<locals>.{name}@{getattr(node, 'lineno', 0)}"

    def resolve(self, expr: ast.AST, scope: _Scope, depth: int = 0) -> set[str]:
        """Return the dotted names ``expr`` may denote; empty for runtime values."""
        if depth > _MAX_ALIAS_DEPTH:
            return set()
        if isinstance(expr, ast.Attribute):
            return {
                _canonical(f"{base}.{expr.attr}")
                for base in self.resolve(expr.value, scope, depth + 1)
            }
        if not isinstance(expr, ast.Name):
            return set()
        found = self.lookup(expr.id, scope)
        if found is None:
            stars = (f"{star}.{expr.id}" for star in self.root.stars)
            return {_canonical(name) for name in (expr.id, *stars)}
        where, bindings = found
        names: set[str] = set()
        for binding in bindings:
            if isinstance(binding, str):
                names.add(_canonical(binding))
            elif isinstance(binding, _DEFINITIONS):
                names.add(self._definition(expr.id, where, binding))
            elif isinstance(binding, (ast.Assign, ast.AnnAssign)):
                if isinstance(binding.value, ast.Lambda):
                    names.add(self._definition(expr.id, where, binding))
                elif binding.value is not None:
                    names |= self.resolve(binding.value, where, depth + 1)
        return names

    def driver(self, names: set[str]) -> tuple[str, _Driver] | None:
        """Return the label and shape of the driver any of ``names`` denotes."""
        for name in sorted(names):
            module = name.rpartition(".")[0]
            owner = self if module == self.module else None
            if owner is None and module.partition(".")[0] == TESTS_ROOT.name:
                owner = _repository_module(module)  # shallow indexes forward nothing
            if owner is not None:
                owner.find_forwarders()
                if name in owner.forwarders:
                    label = name.rpartition(".")[2].partition("@")[0]
                    return label, owner.forwarders[name]
            for key, driver in DRIVERS.items():
                if name == key or name.endswith("." + key):
                    return key, driver
        return None

    def _forwarded(self, value: ast.AST, scope: _Scope) -> bool:
        """Whether ``value`` is the enclosing function's own ``*args``/``**kwargs``."""
        function = scope.node
        if not isinstance(value, ast.Name) or not isinstance(function, _FUNCTIONS):
            return False
        variadic = {id(function.args.vararg), id(function.args.kwarg)}
        bindings = scope.bindings.get(value.id, [])
        return len(bindings) == 1 and id(bindings[0]) in variadic

    def _function_name(self, function: ast.AST) -> str | None:
        """Return the name a forwarding function is called by, if it has one."""
        if isinstance(function, ast.Lambda):
            parent = self.parent.get(function)
            if not isinstance(parent, (ast.Assign, ast.AnnAssign)):
                return None
            target = _alias_target(parent)
            if target is None or parent.value is not function:
                return None
            return self._definition(target.id, self.scope_of[parent], parent)
        if isinstance(function, _DEFINITIONS):
            return self._definition(function.name, self.scope_of[function], function)
        return None

    def find_forwarders(self) -> None:
        """Treat functions that pass their variadics to a driver as that driver."""
        if self._forwarders_found:
            return
        self._forwarders_found = True
        calls = [node for node in ast.walk(self.tree) if isinstance(node, ast.Call)]
        changed = True
        while changed:
            changed = False
            for call in calls:
                scope = self.scope_of[call]
                driver = self.driver(self.resolve(call.func, scope))
                variadics = [
                    *(arg.value for arg in call.args if isinstance(arg, ast.Starred)),
                    *(kw.value for kw in call.keywords if kw.arg is None),
                ]
                if driver is None or not any(
                    self._forwarded(value, scope) for value in variadics
                ):
                    continue
                name = self._function_name(scope.node)
                if name is not None and name not in self.forwarders:
                    self.forwarders[name] = driver[1]
                    changed = True

    def _helper_problems(self, call: ast.Call, names: set[str]) -> list[str]:
        """Spell each argument that overrides a contract helper's target."""
        limit = min(CONTRACT_HELPERS[name] for name in names)
        positional = [arg for arg in call.args if not isinstance(arg, ast.Starred)]
        problems = [
            f"*{_excerpt(arg.value)}"
            for arg in call.args
            if isinstance(arg, ast.Starred)
        ]
        problems += [_excerpt(arg) for arg in positional[limit:]]
        for keyword in call.keywords:
            if keyword.arg is None:
                problems.append(f"**{_excerpt(keyword.value)}")
            elif keyword.arg in TARGET_OVERRIDES:
                problems.append(f"{keyword.arg}=")
        return problems

    def _from_contract(self, expr: ast.AST, scope: _Scope) -> bool:
        """Whether ``expr`` is a helper call, or a name bound once here to one."""
        if isinstance(expr, ast.Call):
            names = self.resolve(expr.func, scope)
            return (
                bool(names)
                and all(name in CONTRACT_HELPERS for name in names)
                and not self._helper_problems(expr, names)
            )
        if not isinstance(expr, ast.Name) or expr.id in scope.retargeted:
            return False
        bindings = scope.bindings.get(expr.id, [])
        if len(bindings) != 1 or not isinstance(
            bindings[0], (ast.Assign, ast.AnnAssign)
        ):
            return False
        value = bindings[0].value
        return isinstance(value, ast.Call) and self._from_contract(value, scope)

    def _target_kind(self, expr: ast.AST, scope: _Scope) -> str | None:
        """Classify a DSN or URL argument; None when it is hand-built or opaque."""
        if self._from_contract(expr, scope):
            return "contract"
        value = _string(expr)
        if value is None:
            return None
        match = POSTGRES_URL.match(value)
        if match is None or value[match.end() :].strip("/") or _hand_built_urls(value):
            return None
        return "placeholder" if match["host"] else "bare"

    def _mapping_kind(self, expr: ast.AST, scope: _Scope) -> str | None:
        """Classify a ``**``, ``connect_args=``, or ``query=`` mapping."""
        if self._from_contract(expr, scope):
            return "contract"
        if not isinstance(expr, ast.Dict):
            return None
        kind = "empty"
        for key, value in zip(expr.keys, expr.values):
            if key is None:
                inner = self._mapping_kind(value, scope)
                if inner is None:
                    return None
                kind = "contract" if inner == "contract" else kind
            elif not _plain_key(key):
                return None
        return kind

    def _target_problems(
        self, call: ast.Call, driver: _Driver, scope: _Scope
    ) -> list[str]:
        """Spell each driver argument whose target is not the contract's."""
        problems: list[str] = []
        supplied = False
        for index, arg in enumerate(call.args):
            if isinstance(arg, ast.Starred):
                if self._forwarded(arg.value, scope):
                    supplied = True
                else:
                    problems.append(f"*{_excerpt(arg.value)}")
            elif index >= driver.first_target:
                kind = self._target_kind(arg, scope)
                if kind is None:
                    problems.append(_excerpt(arg))
                supplied = supplied or kind in ("contract", "placeholder")
        for keyword in call.keywords:
            name, value = keyword.arg, keyword.value
            if name is None and self._forwarded(value, scope):
                supplied = True
            elif name is None or name in TARGET_MAPPINGS:
                kind = self._mapping_kind(value, scope)
                if kind is None:
                    spelled = f"{name}=" if name else "**"
                    problems.append(spelled + _excerpt(value))
                supplied = supplied or kind == "contract"
            elif name in TARGET_KEYWORDS:
                problems.append(f"{name}=")
            elif name in TARGET_ARGUMENTS:
                kind = self._target_kind(value, scope)
                if kind is None:
                    problems.append(f"{name}={_excerpt(value)}")
                supplied = supplied or kind in ("contract", "placeholder")
            elif name == "creator":
                supplied = True
        if driver.connects and not problems and not supplied:
            problems.append("<no target: libpq defaults>")
        return problems

    def _replaces_driver(
        self, call: ast.AST | None, node: ast.AST, scope: _Scope
    ) -> bool:
        """Whether ``call`` is ``setattr(module, "attr", node)`` patching a driver."""
        if not isinstance(call, ast.Call) or not call.args or call.args[-1] is not node:
            return False
        func = call.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "setattr":
            return False
        attribute = _string(call.args[1]) if len(call.args) == 3 else None
        dotted = _string(call.args[0]) if len(call.args) == 2 else None
        if attribute is not None:
            patched = {
                f"{base}.{attribute}" for base in self.resolve(call.args[0], scope)
            }
        elif dotted is not None:
            patched = {_canonical(dotted)}
        else:
            return False
        return self.driver(patched) is not None

    def _handed_on(self, node: ast.AST, scope: _Scope) -> bool:
        """Whether ``node`` passes a connecting driver on without calling it."""
        parent = self.parent.get(node)
        if isinstance(parent, ast.Attribute) or (
            isinstance(parent, ast.Call) and parent.func is node
        ):
            return False
        driver = self.driver(self.resolve(node, scope))
        if driver is None or not driver[1].connects:
            return False
        if isinstance(parent, (ast.Assign, ast.AnnAssign)) and parent.value is node:
            if _alias_target(parent) is not None:
                return False  # an alias, whose own calls are checked
        return not self._replaces_driver(parent, node, scope)

    def findings(self) -> list[tuple[int, str]]:
        """Return ``(line, finding)`` for each target not taken from the contract."""
        self.find_forwarders()
        found: list[tuple[int, str]] = []
        for node in ast.walk(self.tree):
            scope = self.scope_of.get(node)
            if scope is None:
                continue
            if isinstance(node, ast.Call):
                names = self.resolve(node.func, scope)
                if names and all(name in CONTRACT_HELPERS for name in names):
                    label, problems = min(names), self._helper_problems(node, names)
                elif (driver := self.driver(names)) is not None:
                    label = driver[0]
                    problems = self._target_problems(node, driver[1], scope)
                else:
                    continue
                if problems:
                    found.append((node.lineno, f"{label}({', '.join(problems)})"))
            elif (
                isinstance(node, (ast.Name, ast.Attribute))
                and isinstance(node.ctx, ast.Load)
                and self._handed_on(node, scope)
            ):
                found.append((node.lineno, f"{_excerpt(node)} handed on uncalled"))
        return sorted(found)


_CANONICALIZING: set[str] = set()
# A production module is followed only for names that could be a driver, a
# driver package, or a contract helper; test modules are followed for all.
_FOLLOWED_NAMES = frozenset(
    part
    for dotted in (*DRIVERS, *CONTRACT_HELPERS)
    for part in dotted.split(".")
    if part not in {"nexus", "tests", "pg_fixtures", "database", "api", "slot_utils"}
)


@functools.lru_cache(maxsize=None)
def _repository_module(module: str) -> _ModuleIndex | None:
    """Index a repository module by dotted name; None outside the repository.

    Test modules are indexed in full, so a forwarding wrapper they define is
    recognized where another test imports it; production modules only for
    their module-level re-exports.
    """
    base = REPO_ROOT.joinpath(*module.split("."))
    for path, package in (
        (base.with_suffix(".py"), False),
        (base / "__init__.py", True),
    ):
        if path.is_file():
            shallow = module.partition(".")[0] != TESTS_ROOT.name
            source = path.read_text()
            return _ModuleIndex(source, module, package=package, shallow=shallow)
    return None


def _canonical(name: str) -> str:
    """Follow re-exports through repository modules to where ``name`` is defined."""
    parts = name.split(".")
    if parts[0] != TESTS_ROOT.name and parts[-1] not in _FOLLOWED_NAMES:
        return name
    for cut in range(len(parts) - 1, 0, -1):
        index = _repository_module(".".join(parts[:cut]))
        if index is None:
            continue
        head = parts[cut]
        if name in _CANONICALIZING or index.lookup(head, index.root) is None:
            return name
        _CANONICALIZING.add(name)
        try:
            targets = index.resolve(ast.Name(id=head, ctx=ast.Load()), index.root)
            if len(targets) != 1:
                return name
            resolved = ".".join([*targets, *parts[cut + 1 :]])
            return name if resolved == name else _canonical(resolved)
        finally:
            _CANONICALIZING.discard(name)
    return name


def _module_name(path: Path) -> tuple[str, bool]:
    """Return a repository file's dotted module name and whether it is a package."""
    parts = path.relative_to(REPO_ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False


def _driver_targets(
    source: str, module: str = "tests.snippet", package: bool = False
) -> list[tuple[int, str]]:
    """Return ``(line, finding)`` for each driver target not from the contract."""
    return _ModuleIndex(source, module, package=package).findings()


# Sources are parsed, never run. Known-bad URLs are split so this file stays
# inside the URL rule's scan.
_HAND_BUILT_DRIVER_TARGETS = [
    pytest.param("psycopg2.connect(dbname=TEST_DBNAME)", id="dbname-keyword"),
    pytest.param('psycopg2.connect(dbname=dbname, user="pythagor")', id="user-keyword"),
    pytest.param(
        "await asyncpg.connect(database=name, host=host, port=port)",
        id="asyncpg-keywords",
    ),
    pytest.param(
        "psycopg2.extensions.make_dsn(dbname=name, **params)", id="make-dsn-keywords"
    ),
    pytest.param(
        "from sqlalchemy.engine import URL\n"
        'URL.create("postgresql+psycopg2", username=user, database=name)',
        id="url-create-keywords",
    ),
    pytest.param(
        'import psycopg2\nparams = {"host": host, "dbname": "save_01"}\n'
        "psycopg2.connect(**params)",
        id="expanded-hand-built-dict",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.database import connection_kwargs\n"
        'params = {**connection_kwargs("save_01"), "host": host}\n'
        "psycopg2.connect(**params)",
        id="expanded-dict-over-contract",
    ),
    pytest.param(
        "import psycopg2\ndef open_db(options):\n"
        "    return psycopg2.connect(**options)",
        id="expanded-parameter",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.database import connection_kwargs\n"
        "def open_db(name):\n    params = connection_kwargs(name)\n"
        "    options = params\n    return psycopg2.connect(**options)",
        id="expanded-two-hops",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.database import connection_kwargs\n"
        "def open_db(name, other):\n    params = connection_kwargs(name)\n"
        "    if other:\n        params = other\n    return psycopg2.connect(**params)",
        id="expanded-rebound",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.database import connection_kwargs\n"
        'def open_db(name):\n    params = connection_kwargs(name)\n    params["host"]'
        ' = "db.example"\n    return psycopg2.connect(**params)',
        id="expanded-retargeted",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.database import connection_kwargs\n"
        "def open_db(name, extra):\n    params = connection_kwargs(name)\n"
        "    params.update(extra)\n    return psycopg2.connect(**params)",
        id="expanded-updated",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.database import connection_kwargs\n"
        'PARAMS = connection_kwargs("save_01")\n'
        "def open_db():\n    return psycopg2.connect(**PARAMS)",
        id="expanded-from-another-scope",
    ),
    pytest.param(
        "import asyncpg\nasync def open_db(args, params):\n"
        "    return await asyncpg.connect(*args, **params)",
        id="asyncpg-star-args-and-kwargs",
    ),
    pytest.param(
        "import psycopg2.pool\npsycopg2.pool.SimpleConnectionPool(1, 4, **params)",
        id="pool-expanded",
    ),
    pytest.param(
        'import psycopg2\npsycopg2.connect("dbname=save_01 host=db.example")',
        id="positional-libpq-string",
    ),
    pytest.param(
        "import psycopg2\ndef open_db(url):\n    return psycopg2.connect(url)",
        id="positional-url-variable",
    ),
    pytest.param(
        "import psycopg2\npsycopg2.connect('postgresql://' + host + '/save_01')",
        id="positional-url-expression",
    ),
    pytest.param('import psycopg2\npsycopg2.connect(f"dbname={name}")', id="f-string"),
    pytest.param('import psycopg2\npsycopg2.connect("")', id="empty-dsn"),
    pytest.param(
        'from psycopg2.extensions import make_dsn\nmake_dsn("dbname=save_01")',
        id="make-dsn-positional",
    ),
    pytest.param("import psycopg2\npsycopg2.connect(dsn=dsn)", id="dsn-keyword"),
    pytest.param(
        "import asyncpg\nasync def open_pool(dsn):\n"
        "    return await asyncpg.create_pool(dsn=dsn)",
        id="create-pool-dsn",
    ),
    pytest.param(
        "from psycopg2 import connect as pg_connect\npg_connect(dbname=name)",
        id="from-import-connect-alias",
    ),
    pytest.param(
        "from asyncpg import connect\nasync def open_db():\n"
        "    return await connect(host=host, port=port)",
        id="from-asyncpg-import-connect",
    ),
    pytest.param("import psycopg2 as pg\npg.connect(dsn_string)", id="import-as-alias"),
    pytest.param(
        "import asyncpg as apg\nasync def open_pool():\n"
        "    return await apg.create_pool(**params)",
        id="asyncpg-import-as-alias",
    ),
    pytest.param(
        "import psycopg2\nopen_db = psycopg2.connect\nopen_db(dbname=name)",
        id="assigned-alias",
    ),
    pytest.param("from psycopg2 import *\nconnect(dbname=name)", id="star-import"),
    pytest.param(
        "from tests.pg_fixtures import psycopg2 as driver\ndriver.connect(url)",
        id="repository-re-export",
    ),
    pytest.param(
        "from tests import pg_fixtures\n"
        'pg_fixtures.URL.create("postgresql", host=host)',
        id="repository-re-export-url",
    ),
    pytest.param(
        "from .pg_fixtures import psycopg2\npsycopg2.connect(url)",
        id="relative-re-export",
    ),
    pytest.param(
        "from sqlalchemy import create_engine\ndef engine(url):\n"
        "    return create_engine(url)",
        id="create-engine-url-variable",
    ),
    pytest.param(
        "import sqlalchemy as sa\n"
        'sa.create_engine(sa.URL.create("postgresql", host=host))',
        id="create-engine-url-create",
    ),
    pytest.param(
        "from sqlalchemy import create_engine\nfrom sqlalchemy.engine import URL\n"
        'create_engine(URL("postgresql", "role", None, "db", None, "save_01", {}))',
        id="create-engine-url-constructor",
    ),
    pytest.param(
        "from sqlalchemy import create_engine\n"
        'create_engine("postgresql+psycopg2://")',
        id="create-engine-bare-scheme",
    ),
    pytest.param(
        "from sqlalchemy import create_engine\n"
        'create_engine("postgresql+psycopg2://", connect_args={"host": host})',
        id="create-engine-connect-args",
    ),
    pytest.param(
        "from sqlalchemy.ext.asyncio import create_async_engine\n"
        "create_async_engine(url)",
        id="create-async-engine",
    ),
    pytest.param(
        "import psycopg2\npsycopg2.connect(cursor_factory=RealDictCursor)",
        id="no-target",
    ),
    pytest.param(
        "import asyncpg\nasync def open_db():\n    return await asyncpg.connect()",
        id="asyncpg-no-target",
    ),
    pytest.param(
        "import psycopg2\nfrom sqlalchemy import create_engine\n"
        'create_engine("postgresql+psycopg2://", creator=psycopg2.connect)',
        id="creator-handed-on",
    ),
    pytest.param(
        "import functools\nimport psycopg2\n"
        "open_db = functools.partial(psycopg2.connect, dbname=name)",
        id="partial-handed-on",
    ),
    pytest.param(
        "import psycopg2\ndef open_db(*args, **kwargs):\n"
        "    return psycopg2.connect(*args, **kwargs)\n"
        'open_db("dbname=save_01")',
        id="forwarder-called-with-target",
    ),
    pytest.param(
        "from nexus.database import database_url\n"
        'database_url("save_01", host=host)',
        id="helper-host-override",
    ),
    pytest.param(
        "from nexus.database import connection_kwargs\n"
        "connection_kwargs(dbname, port=port)",
        id="helper-port-override",
    ),
    pytest.param(
        "from nexus.api.slot_utils import get_slot_db_url\n"
        'get_slot_db_url(None, 2, "pythagor")',
        id="helper-positional-override",
    ),
    pytest.param(
        "from nexus.database import connection_kwargs\n"
        "connection_kwargs(dbname, **overrides)",
        id="helper-expanded-override",
    ),
]


@pytest.mark.parametrize("source", _HAND_BUILT_DRIVER_TARGETS)
def test_driver_guard_recognizes_hand_built_targets(source: str) -> None:
    """Every driver target not taken straight from the contract trips the guard."""
    assert _driver_targets(source)


_CONTRACT_DRIVER_TARGETS = [
    pytest.param(
        "import psycopg2\nfrom nexus.database import connection_kwargs\n"
        "psycopg2.connect(**connection_kwargs(dbname))",
        id="expanded-helper",
    ),
    pytest.param(
        "import psycopg2 as pg\n"
        "from nexus.database import connection_kwargs as contract\n"
        "pg.connect(**contract(dbname))",
        id="aliased-driver-and-helper",
    ),
    pytest.param(
        "import psycopg2\nfrom psycopg2.extras import RealDictCursor\n"
        "from nexus.database import connection_kwargs\n"
        "def open_db(name):\n    params = connection_kwargs(name)\n"
        '    params["cursor_factory"] = RealDictCursor\n'
        '    params.pop("application_name")\n'
        "    return psycopg2.connect(**params)",
        id="one-hop-binding",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.database import database_url\n"
        "psycopg2.connect(database_url(dbname), cursor_factory=RealDictCursor)",
        id="positional-helper-url",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.api.slot_utils import get_slot_db_url\n"
        "psycopg2.connect(get_slot_db_url(slot=2), cursor_factory=RealDictCursor)",
        id="positional-slot-url",
    ),
    pytest.param(
        "import asyncpg\nfrom tests import pg_fixtures\nasync def open_db():\n"
        "    return await asyncpg.connect(**pg_fixtures.asyncpg_kwargs(dbname))",
        id="asyncpg-fixture-helper",
    ),
    pytest.param(
        "import asyncpg\nfrom nexus.database import asyncpg_kwargs\n"
        "async def open_pool():\n    return await asyncpg.create_pool("
        "**asyncpg_kwargs(dbname), min_size=1, max_size=2)",
        id="create-pool-helper",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.database import database_url\n"
        "psycopg2.connect(dsn=database_url(dbname))",
        id="dsn-helper",
    ),
    pytest.param(
        "from sqlalchemy import create_engine\n"
        "from tests.pg_fixtures import sqlalchemy_url\n"
        "create_engine(sqlalchemy_url(dbname), future=True)",
        id="create-engine-helper",
    ),
    pytest.param(
        "from sqlalchemy import create_engine\n"
        "from nexus.database import database_url\n"
        "def engine(name):\n    url = database_url(name)\n"
        "    return create_engine(url)",
        id="create-engine-one-hop",
    ),
    pytest.param(
        "from sqlalchemy import create_engine\nfrom tests.pg_fixtures import connect\n"
        'create_engine("postgresql+psycopg2://", creator=lambda: connect(dbname))',
        id="bare-scheme-with-creator",
    ),
    pytest.param(
        "from sqlalchemy import create_engine\n"
        "from nexus.database import connection_kwargs\n"
        'create_engine("postgresql+psycopg2://", '
        "connect_args=connection_kwargs(dbname))",
        id="bare-scheme-with-connect-args",
    ),
    pytest.param(
        'from sqlalchemy import create_engine\ncreate_engine("postgresql://'
        'fixture.invalid/")',
        id="invalid-placeholder",
    ),
    pytest.param(
        "import psycopg2\nfrom tests.pg_fixtures import database_url\n"
        "psycopg2.connect(database_url(dbname))",
        id="repository-re-export-helper",
    ),
    pytest.param(
        "import psycopg2\nfrom nexus.database import connection_kwargs\n"
        "psycopg2.connect(**{**connection_kwargs(dbname), "
        '"cursor_factory": RealDictCursor})',
        id="dict-over-helper",
    ),
    pytest.param(
        "from psycopg2.extensions import make_dsn\n"
        "from nexus.database import connection_kwargs\n"
        "make_dsn(**connection_kwargs('NEXUS_template'))",
        id="make-dsn-helper",
    ),
    pytest.param(
        "from sqlalchemy.engine import URL\n"
        "def bare() -> URL:\n"
        '    return URL.create("postgresql+psycopg2")',
        id="url-builder-without-target",
    ),
    pytest.param(
        "import psycopg2\ndef test_spy(monkeypatch):\n"
        "    original = psycopg2.connect\n"
        "    def spy(*args, **kwargs):\n"
        "        return original(*args, **kwargs, cursor_factory=None)\n"
        '    monkeypatch.setattr(psycopg2, "connect", spy)',
        id="forwarding-spy-installed-as-driver",
    ),
    pytest.param(
        "import sqlite3\nfrom tests import pg_fixtures\n"
        "sqlite3.connect(path)\nengine.connect()\n"
        "pg_fixtures.connect(dbname, cursor_factory=RealDictCursor)\n"
        "def connect(host):\n    return host\n"
        'connect(host="example")',
        id="unrelated-connects",
    ),
    pytest.param(
        'monkeypatch.setattr("psycopg2.connect", fail)\n'
        'mock.patch("asyncpg.connect", new=fail)',
        id="string-patches",
    ),
]


@pytest.mark.parametrize("source", _CONTRACT_DRIVER_TARGETS)
def test_driver_guard_allows_contract_targets(source: str) -> None:
    """Contract helpers, direct or one hop away, and placeholders stay legal."""
    assert _driver_targets(source) == []


def test_tests_never_hand_a_driver_its_own_target() -> None:
    """Driver calls in tests take their target from the contract."""
    violations = [
        f"{relative}:{line}: {finding}"
        for path in _tree_sources(frozenset({".py"}))
        for relative in [path.relative_to(REPO_ROOT).as_posix()]
        if relative not in DRIVER_TARGET_ALLOWLIST
        for line, finding in _driver_targets(path.read_text(), *_module_name(path))
    ]
    assert violations == [], (
        "Pass a contract helper call straight to the driver (or bind it once in "
        "the same function): **nexus.database.connection_kwargs(dbname), "
        "**tests.pg_fixtures.asyncpg_kwargs(dbname), database_url(dbname), or "
        "call tests.pg_fixtures.connect(dbname):\n" + "\n".join(violations)
    )


def test_driver_allowlist_names_only_current_exceptions() -> None:
    """Each allowlisted file exists and still needs its exception."""
    for relative in sorted(DRIVER_TARGET_ALLOWLIST):
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} is gone; drop it from the allowlist"
        needed = _driver_targets(path.read_text(), *_module_name(path))
        assert needed, f"{relative} no longer spells a target; drop the exception"


FIXTURE_DATABASE = "qa804_fixture_target"
_LIBPQ_ENVIRONMENT = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGCONNECT_TIMEOUT",
    "PGOPTIONS",
)


@pytest.fixture
def runtime_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the runtime at an isolated nexus.toml copy with no PG* overrides."""
    for key in _LIBPQ_ENVIRONMENT:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "nexus.toml"
    path.write_text((TESTS_ROOT.parent / "nexus.toml").read_text())
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(path))
    return path


def _configure_database(path: Path, *, host: str, port: int, user: str) -> None:
    """Name a server in ``[api.database]``, which outranks the PG* environment."""
    document: Any = tomlkit.parse(path.read_text())
    database = document["api"]["database"]
    database["host"] = host
    database["port"] = port
    database["user"] = user
    path.write_text(tomlkit.dumps(document))


@pytest.mark.parametrize(
    ("configured", "environment", "expected"),
    [
        pytest.param(
            None,
            {
                "PGHOST": "environment.invalid",
                "PGPORT": "55442",
                "PGUSER": "environment_role",
                "PGPASSWORD": "environment-secret",
                "PGOPTIONS": "-c statement_timeout=1000",
            },
            {"host": "environment.invalid", "port": 55442, "user": "environment_role"},
            id="pg-environment-only",
        ),
        pytest.param(
            {"host": "configured.invalid", "port": 55443, "user": "configured_role"},
            {
                "PGHOST": "environment.invalid",
                "PGPORT": "55444",
                "PGUSER": "environment_role",
            },
            {"host": "configured.invalid", "port": 55443, "user": "configured_role"},
            id="toml-outranks-pg-environment",
        ),
        pytest.param(
            None,
            {},
            {"host": "", "user": getpass.getuser()},
            id="libpq-socket-and-os-user-defaults",
        ),
    ],
)
def test_fixture_clients_resolve_the_runtime_contract(
    runtime_config: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured: dict[str, Any] | None,
    environment: dict[str, str],
    expected: dict[str, Any],
) -> None:
    """Every pg_fixtures client carries exactly the runtime's parameters."""
    if configured is not None:
        _configure_database(runtime_config, **configured)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    contract = connection_kwargs(FIXTURE_DATABASE)
    target = connection_target(contract)
    assert {key: target[key] for key in expected} == expected
    assert target["dbname"] == FIXTURE_DATABASE
    assert url_connection_kwargs(pg_fixtures.sqlalchemy_url(FIXTURE_DATABASE)) == (
        contract
    )
    assert pg_fixtures.asyncpg_kwargs(FIXTURE_DATABASE) == asyncpg_kwargs(
        FIXTURE_DATABASE
    )
    assert pg_fixtures.connection_parameters(FIXTURE_DATABASE) == contract


@pytest.mark.requires_postgres
def test_fixture_connect_dials_the_configured_server(
    runtime_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """connect() dials the ``[api.database]`` port even when PG* names another.

    Both loopback ports are closed, so libpq refuses at once and names the
    port it dialed. No server is needed, but the default tier forbids any
    connection attempt, so this runs in the PostgreSQL tier.
    """
    _configure_database(runtime_config, host="127.0.0.1", port=1, user="configured")
    monkeypatch.setenv("PGHOST", "127.0.0.1")
    monkeypatch.setenv("PGPORT", "2")
    monkeypatch.setenv("PGUSER", "environment_role")
    with pytest.raises(psycopg2.OperationalError) as refused:
        pg_fixtures.connect(FIXTURE_DATABASE)
    message = str(refused.value)
    assert re.search(r"\bport 1\b", message), message
    assert not re.search(r"\bport 2\b", message), message
