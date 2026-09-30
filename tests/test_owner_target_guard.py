"""Offline guard: no test spells an owner database as a connection target.

Issue #885 moved every test off the owner's save slots and ``NEXUS_template``
onto disposable clones. This guard keeps it there without PostgreSQL: it
parses every module under ``tests/`` with ``ast`` and fails on the spellings
that reach an owner database.

- ``get_slot_db_url(slot=<int literal>)`` (or a positional int literal).
- ``slot_dbname(<int literal>)``, positionally or by keyword.
- A connection call (``connect``, ``psycopg2.connect``, ``get_connection``,
  ``asyncpg_kwargs``, ``connection_kwargs``, ``database_url``,
  ``sqlalchemy_url``) whose argument, or a value of a ``**{...}`` dict
  literal or ``**dict(...)`` call (a ``dict(...)`` call's positional dict
  literals included), is a string literal naming ``save_NN`` or
  ``NEXUS_template`` (a whole name, a DSN or URL naming one, or an f-string
  that starts ``save_`` or whose text anywhere ends a DSN value with ``save_``
  before a formatted slot number, as in
  ``f"host={host} dbname='save_{slot:02d}'"``). A name counts in any spelling
  libpq reads as that name: single-quoted with backslash escapes
  (``dbname='save_04'``), spaced around ``=``, and percent-encoded in a URL
  (``postgresql://u@audit.invalid/save%5F04``); a double-quoted
  ``dbname="save_04"`` is refused as well.
- An assignment of such a literal to a ``*DBNAME*`` name
  (``TEST_DBNAME = "save_04"``).
- A child-process call (``subprocess.run``, ``Popen``, ``check_call``,
  ``check_output``, ``call``) whose argument list holds such a literal
  (``pg_dump --dbname save_04``, ``pg_dump --dbname "dbname='save_04'"``),
  or whose ``shell=True`` command string does, word by word as the shell
  splits it at whitespace and at its control operators (``;``, ``&&``,
  ``||``, ``|``, ``&``, ``<``, ``>``), so ``pg_dump -d save_04>dump.sql`` is
  refused: a child connects outside the in-process connection audit.
- ``include_data=True`` (a data clone), passed as a keyword or through a
  ``**{...}`` or ``**dict(...)`` expansion, in a module that never applies
  the ``requires_corpus`` marker.
- A clone or dump helper (a callee whose name ends ``_clone`` or ``_dump``)
  given an int-literal slot, positionally or as ``slot=`` (``slot_clone(1)``
  dumps ``save_01`` with its data), in a module that never applies the
  ``requires_corpus`` marker.

``ALLOWLISTED_FILES`` exempts, by exact path, the contract and private-cluster
tests whose subject is the owner names themselves. ``EXEMPTIONS`` names every
other permitted use by file, rule, and the finding's exact source text, with
its reason. Each exemption admits one finding: a new use in an exempted file,
even of the same rule, fails until it is listed, and an exemption that no
longer matches a finding fails as stale.
"""

from __future__ import annotations

import ast
import re
import shlex
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote

import pytest

TESTS_ROOT = Path(__file__).resolve().parent

OWNER_NAME = re.compile(r"save_\d+|NEXUS_template")
# An owner name inside a DSN or URL: after a path slash, ``=``, or whitespace.
OWNER_IN_DSN = re.compile(r"(?:^|[/=\s])(?:save_\d+|NEXUS_template)(?:$|[?&\s])")
# An f-string's leading text that a formatted slot number completes.
SLOT_PREFIX_IN_DSN = re.compile(r"(?:^|[/=\s])save_$")
# Shell control operators, which end a word without whitespace
# (``pg_dump -d save_04>dump.sql``, ``pg_dump -d save_04;true``).
SHELL_OPERATORS = re.compile(r"&&|\|\||[;&|<>()]")
# Quote characters around a DSN value: libpq's single quotes, and double
# quotes, which a caller may mistake for them.
DSN_QUOTES = re.compile(r"['\"]")
CONNECTION_CALLS = frozenset(
    {
        "connect",
        "get_connection",
        "asyncpg_kwargs",
        "connection_kwargs",
        "database_url",
        "sqlalchemy_url",
    }
)

RULE_SLOT_URL = "get_slot_db_url-literal-slot"
RULE_SLOT_DBNAME = "slot_dbname-literal-slot"
RULE_CONNECTION = "connection-owner-literal"
RULE_DBNAME_CONSTANT = "dbname-constant-owner-literal"
RULE_DATA_CLONE = "include_data-without-requires_corpus"
RULE_SUBPROCESS = "subprocess-owner-literal"
RULE_SLOT_CLONE = "clone-or-dump-literal-slot-without-requires_corpus"
# A callee named ``*_clone`` or ``*_dump`` copies a slot's database.
CLONE_OR_DUMP = re.compile(r".+_(?:clone|dump)")
# Child processes (pg_dump, psql, a CLI) connect outside the in-process
# connection audit; an owner name in their argument list reaches the owner.
SUBPROCESS_CALLS = frozenset({"run", "Popen", "check_call", "check_output", "call"})

# Exact paths (relative to tests/) whose subject is the owner names.
ALLOWLISTED_FILES: dict[str, str] = {
    "test_slot_utils.py": (
        "the slot contract's own tests: slot numbers map to owner names by "
        "design, and nothing connects"
    ),
    "test_database_contract.py": (
        "the PostgreSQL contract's resolver tests render owner names into "
        "keywords and URLs without connecting; its connection tests run on "
        "private clusters it starts itself"
    ),
    "test_connection_lifecycle.py": (
        "runs production entry points against save_04 on two private "
        "clusters it starts and registers with the connection audit; the "
        "owner's NEXUS_template is read only by pg_dump for schema"
    ),
    "test_pg_disposable_target.py": (
        "tests of the routing and refusal helpers, which resolve owner slot "
        "names to prove they are rerouted or refused"
    ),
    "test_pg_target_contract.py": (
        "the offline PostgreSQL target guard's own tests; their fixtures "
        "spell owner targets as source under test"
    ),
}


class Exemption(NamedTuple):
    """One permitted finding in one file, and why it is safe.

    ``source`` is the finding's exact source text (``Finding.source``), so an
    exemption admits that one use and no other finding of its rule.
    """

    path: str
    rule: str
    source: str
    reason: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.path, self.rule, self.source)


EXEMPTIONS: tuple[Exemption, ...] = (
    *(
        Exemption(
            "test_scheduler_helpers_routing.py",
            RULE_SLOT_DBNAME,
            source,
            "a test of route_slot itself: the slot number resolves to prove "
            "routing and its restoration; nothing connects",
        )
        for source in (
            "module.slot_dbname(4)",
            "module.slot_dbname(5)",
            "slot_utils.slot_dbname(4)",
        )
    ),
    *(
        Exemption(
            "test_memnon_db_access.py",
            RULE_CONNECTION,
            'database_url("save_04")',
            "fake-backed label: the URL is handed to a monkeypatched "
            "psycopg2.connect that returns a recording fake",
        )
        for _ in range(2)
    ),
    Exemption(
        "test_memnon/test_source_embeddings.py",
        RULE_CONNECTION,
        'database.connect("save_05", dict_cursor=True)',
        "fake-backed label: connect is a method of the test's own _Database "
        "fake, which records statements and never reaches a driver",
    ),
    Exemption(
        "test_idf_dictionary_pg.py",
        RULE_DATA_CLONE,
        'disposable_slot_database( "qa762_corpus_copy", source_db=idf_slot, '
        "include_data=True )",
        "the data clone's source_db is the module's own disposable idf_slot "
        "clone (qa762_*), not an owner slot",
    ),
)


class Finding(NamedTuple):
    """One owner-target spelling the guard refuses."""

    path: str
    line: int
    rule: str
    source: str

    def __str__(self) -> str:
        return f"tests/{self.path}:{self.line}: {self.rule}: {self.source}"


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_int_literal(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    )


def _spellings(text: str) -> set[str]:
    """Return ``text`` as written and as libpq would read its names.

    Percent-decoding reads a URL's encoded characters; dropping backslashes
    reads libpq's escapes inside a quoted value; and each quote becomes a
    space, so a quoted value is delimited the way an unquoted one is.
    """

    written = {text, unquote(text)}
    return written | {DSN_QUOTES.sub(" ", item.replace("\\", "")) for item in written}


def _text_names_owner(text: str) -> bool:
    """Whether ``text`` names an owner database, as a whole or in a DSN or URL."""

    return any(
        OWNER_NAME.fullmatch(spelling.strip()) or OWNER_IN_DSN.search(spelling)
        for spelling in _spellings(text)
    )


def _completes_slot_name(text: str, *, head: bool) -> bool:
    """Whether a formatted slot number after ``text`` completes an owner name.

    Any constant part of an f-string that ends a DSN value with ``save_``
    (``" dbname='save_"``) does; the head part also does when it starts
    ``save_``.
    """

    return any(
        (head and spelling.strip().startswith("save_"))
        or SLOT_PREFIX_IN_DSN.search(spelling)
        for spelling in _spellings(text)
    )


def _names_owner(node: ast.expr) -> bool:
    """Whether ``node`` is a string literal spelling an owner database."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _text_names_owner(node.value)
    if isinstance(node, ast.JoinedStr):
        parts = node.values
        for index, part in enumerate(parts):
            if not (isinstance(part, ast.Constant) and isinstance(part.value, str)):
                continue
            if _text_names_owner(part.value):
                return True
            followed_by_value = index + 1 < len(parts) and isinstance(
                parts[index + 1], ast.FormattedValue
            )
            if followed_by_value and _completes_slot_name(part.value, head=index == 0):
                return True
    return False


def _shell_words(text: str) -> list[str]:
    """Return a shell command's words, split at whitespace and control operators.

    ``shlex`` in punctuation mode reads quotes and escapes as the shell does;
    text it cannot read (an unbalanced quote, or an f-string part cut inside a
    quoted word) is split at whitespace and ``SHELL_OPERATORS`` instead.
    """

    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return SHELL_OPERATORS.sub(" ", text).split()


def _shell_names_owner(node: ast.expr) -> bool:
    """Whether a ``shell=True`` command literal names an owner database.

    Each word the shell would pass is checked on its own, so an operator glued
    to the database argument (``-d save_04>dump.sql``) does not hide it.
    """

    if _names_owner(node):
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        texts = [node.value]
    elif isinstance(node, ast.JoinedStr):
        texts = [
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        ]
    else:
        return False
    return any(_text_names_owner(word) for text in texts for word in _shell_words(text))


def _subprocess_names_owner(value: ast.expr, *, shell: bool) -> bool:
    """Whether a child-process call's argument names an owner database.

    An argument list is checked element by element; with ``shell=True`` a
    command string (or a list's command string) is checked word by word.
    """

    if isinstance(value, (ast.List, ast.Tuple)):
        elements = value.elts
    elif shell:
        elements = [value]
    else:
        return False
    check = _shell_names_owner if shell else _names_owner
    return any(check(element) for element in elements)


def _expanded_keywords(mapping: ast.expr) -> list[tuple[str | None, ast.expr]]:
    """Return the ``(name, value)`` pairs a ``**`` expansion spells literally.

    A dict literal's string keys and a ``dict(...)`` call's keywords are
    keywords of the call they expand into, nested expansions and a
    ``dict(...)`` call's positional dict literals and ``dict(...)`` calls
    included; any other expansion is one ``(None, expression)`` pair.
    """

    pairs: list[tuple[str | None, ast.expr]] = []
    if isinstance(mapping, ast.Dict):
        for key, value in zip(mapping.keys, mapping.values):
            if key is None:
                pairs.extend(_expanded_keywords(value))
            elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                pairs.append((key.value, value))
            else:
                pairs.append((None, value))
    elif isinstance(mapping, ast.Call) and _called_name(mapping.func) == "dict":
        for arg in mapping.args:
            if isinstance(arg, (ast.Dict, ast.Call)):
                pairs.extend(_expanded_keywords(arg))
            else:
                pairs.append((None, arg))
        for keyword in mapping.keywords:
            if keyword.arg is None:
                pairs.extend(_expanded_keywords(keyword.value))
            else:
                pairs.append((keyword.arg, keyword.value))
    else:
        pairs.append((None, mapping))
    return pairs


def _call_keywords(node: ast.Call) -> list[tuple[str | None, ast.expr]]:
    """Return a call's keywords, with literal ``**`` expansions spelled out."""

    pairs: list[tuple[str | None, ast.expr]] = []
    for keyword in node.keywords:
        if keyword.arg is None:
            pairs.extend(_expanded_keywords(keyword.value))
        else:
            pairs.append((keyword.arg, keyword.value))
    return pairs


def _is_true_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and bool(node.value) and node.value != ""


def _applies_requires_corpus(tree: ast.Module) -> bool:
    """Whether the module applies the ``requires_corpus`` marker anywhere."""

    return any(
        isinstance(node, ast.Attribute) and node.attr == "requires_corpus"
        for node in ast.walk(tree)
    )


def scan_source(source: str, path: str) -> list[Finding]:
    """Return every owner-target spelling in one module's source."""

    tree = ast.parse(source, filename=path)
    lines = source.splitlines()
    corpus_marked = _applies_requires_corpus(tree)
    findings: list[Finding] = []

    def add(node: ast.AST, rule: str) -> None:
        line = getattr(node, "lineno", 0)
        segment = ast.get_source_segment(source, node)
        if segment is None:
            segment = lines[line - 1] if 0 < line <= len(lines) else ""
        # The whole call or assignment, whitespace collapsed: an exemption
        # names this exact text.
        findings.append(Finding(path, line, rule, " ".join(segment.split())))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _called_name(node.func)
            # ``connect(**{"dbname": "save_02"})`` spells its keywords as a
            # dict literal; they are keywords of the call, and their values
            # are arguments too.
            keywords = _call_keywords(node)
            values = [*node.args, *(value for _, value in keywords)]
            if name == "get_slot_db_url" and (
                any(_is_int_literal(arg) for arg in node.args)
                or any(
                    keyword == "slot" and _is_int_literal(value)
                    for keyword, value in keywords
                )
            ):
                add(node, RULE_SLOT_URL)
            if name == "slot_dbname" and (
                (node.args and _is_int_literal(node.args[0]))
                or any(_is_int_literal(value) for _, value in keywords)
            ):
                add(node, RULE_SLOT_DBNAME)
            if name in CONNECTION_CALLS and any(_names_owner(v) for v in values):
                add(node, RULE_CONNECTION)
            shell = any(
                keyword == "shell" and _is_true_literal(value)
                for keyword, value in keywords
            )
            if name in SUBPROCESS_CALLS and any(
                _subprocess_names_owner(value, shell=shell) for value in values
            ):
                add(node, RULE_SUBPROCESS)
            if (
                not corpus_marked
                and name is not None
                and CLONE_OR_DUMP.fullmatch(name)
                and (
                    any(_is_int_literal(arg) for arg in node.args)
                    or any(
                        keyword == "slot" and _is_int_literal(value)
                        for keyword, value in keywords
                    )
                )
            ):
                add(node, RULE_SLOT_CLONE)
            # A ``dict(...)`` call is judged as the ``**`` expansion of the
            # call it feeds, so ``clone(**dict(include_data=True))`` is one
            # finding, not two.
            if (
                not corpus_marked
                and name != "dict"
                and any(
                    keyword == "include_data" and _is_true_literal(value)
                    for keyword, value in keywords
                )
            ):
                add(node, RULE_DATA_CLONE)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if node.value is not None and _names_owner(node.value):
                for target in targets:
                    if isinstance(target, ast.Name) and "DBNAME" in target.id.upper():
                        add(node, RULE_DBNAME_CONSTANT)
    return sorted(findings, key=lambda finding: (finding.line, finding.rule))


def _test_modules() -> Iterator[Path]:
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def tree_findings() -> list[Finding]:
    """Scan every module under ``tests/`` outside ``ALLOWLISTED_FILES``."""

    findings: list[Finding] = []
    for path in _test_modules():
        relative = path.relative_to(TESTS_ROOT).as_posix()
        if relative in ALLOWLISTED_FILES:
            continue
        findings.extend(scan_source(path.read_text(), relative))
    return findings


def unexempted(findings: list[Finding]) -> list[Finding]:
    """Return the findings no exemption admits.

    Each exemption admits one finding with its exact (path, rule, source); a
    finding beyond the exemptions listed for its source is not admitted.
    """

    remaining = Counter(item.key for item in EXEMPTIONS)
    offending: list[Finding] = []
    for finding in findings:
        key = (finding.path, finding.rule, finding.source)
        if remaining[key] > 0:
            remaining[key] -= 1
        else:
            offending.append(finding)
    return offending


def test_no_test_spells_an_owner_target() -> None:
    """Every owner spelling outside the allowlist and exemptions fails here."""

    offending = [str(item) for item in unexempted(tree_findings())]
    assert offending == [], "Owner database targets in tests:\n" + "\n".join(offending)


def test_every_allowlist_and_exemption_entry_is_live() -> None:
    """A stale allowlisted file or exemption is removed, not kept."""

    for relative, reason in ALLOWLISTED_FILES.items():
        assert (TESTS_ROOT / relative).is_file(), relative
        assert reason.strip(), relative
    found = Counter(
        (finding.path, finding.rule, finding.source) for finding in tree_findings()
    )
    listed = Counter(item.key for item in EXEMPTIONS)
    for item in EXEMPTIONS:
        assert item.reason.strip(), item
    stale = {key: count for key, count in listed.items() if found[key] < count}
    assert stale == {}, f"stale exemptions (listed more than found): {stale}"


def test_an_exemption_admits_only_its_own_use() -> None:
    """A second use of an exempted rule in an exempted file is still a finding."""

    source = (
        'database_url("save_04")\n'
        'database_url("save_04")\n'
        'psycopg2.connect(dbname="save_02")\n'
    )
    findings = scan_source(source, "test_memnon_db_access.py")
    assert [finding.rule for finding in findings] == [RULE_CONNECTION] * 3
    # The two listed database_url uses are admitted; the new connect is not.
    assert [str(item) for item in unexempted(findings)] == [
        "tests/test_memnon_db_access.py:3: connection-owner-literal: "
        'psycopg2.connect(dbname="save_02")'
    ]
    # A third copy of an exempted source exceeds its listed count.
    tripled = scan_source('database_url("save_04")\n' * 3, "test_memnon_db_access.py")
    assert [finding.line for finding in unexempted(tripled)] == [3]


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("get_slot_db_url(slot=2)", RULE_SLOT_URL),
        ("slot_utils.get_slot_db_url(5)", RULE_SLOT_URL),
        ("slot_dbname(4)", RULE_SLOT_DBNAME),
        ("slot_utils.slot_dbname(1)", RULE_SLOT_DBNAME),
        ("slot_dbname(slot_number=1)", RULE_SLOT_DBNAME),
        ("connect('save_02')", RULE_CONNECTION),
        ("psycopg2.connect(dbname='save_05', host='')", RULE_CONNECTION),
        ("psycopg2.connect('dbname=save_03 connect_timeout=1')", RULE_CONNECTION),
        ("connect(**{'dbname': 'save_02'})", RULE_CONNECTION),
        ("psycopg2.connect(host='', **{'dbname': 'NEXUS_template'})", RULE_CONNECTION),
        ("get_connection(f'save_{slot:02d}')", RULE_CONNECTION),
        ("asyncpg.connect(**asyncpg_kwargs('NEXUS_template'))", RULE_CONNECTION),
        ("create_engine(database_url('save_01'))", RULE_CONNECTION),
        ("sqlalchemy_url('postgresql://u@audit.invalid/save_04')", RULE_CONNECTION),
        (
            "subprocess.run(['pg_dump', '--dbname', 'save_04'], check=True)",
            RULE_SUBPROCESS,
        ),
        ("Popen(('psql', '-d', 'NEXUS_template'))", RULE_SUBPROCESS),
        ("TEST_DBNAME = 'save_04'", RULE_DBNAME_CONSTANT),
        ("SOURCE_DBNAME: str = 'NEXUS_template'", RULE_DBNAME_CONSTANT),
        (
            "disposable_slot_database('qa', source_db='save_04', include_data=True)",
            RULE_DATA_CLONE,
        ),
        ("slot_clone(1)", RULE_SLOT_CLONE),
        ("ann_gate.slot_clone(slot=1)", RULE_SLOT_CLONE),
        ("corpus_dump(4, path)", RULE_SLOT_CLONE),
        ("slot_clone(**{'slot': 1})", RULE_SLOT_CLONE),
        ("slot_dbname(**{'slot_number': 3})", RULE_SLOT_DBNAME),
        # Quoted libpq spellings of an owner name (review of PR #1045).
        (
            "subprocess.run(['pg_dump', '--dbname', \"dbname='save_04'\"], "
            "check=True)",
            RULE_SUBPROCESS,
        ),
        (
            "subprocess.run(['pg_dump', '--dbname', 'dbname=\"save_04\"'])",
            RULE_SUBPROCESS,
        ),
        ("subprocess.run(\"pg_dump -d 'save_04'\", shell=True)", RULE_SUBPROCESS),
        (
            "check_output(['psql', 'postgresql://u@audit.invalid/save%5F04'])",
            RULE_SUBPROCESS,
        ),
        ("psycopg2.connect(\"dbname='save_04' connect_timeout=1\")", RULE_CONNECTION),
        ("psycopg2.connect('dbname = save_03')", RULE_CONNECTION),
        ("psycopg2.connect(r\"dbname='save\\_05'\")", RULE_CONNECTION),
        ("connect('postgresql://u@audit.invalid/save%5F04')", RULE_CONNECTION),
        (
            "connect(\"postgresql://u@audit.invalid/?dbname='save_02'\")",
            RULE_CONNECTION,
        ),
        ("get_connection(f\"dbname='save_{slot:02d}'\")", RULE_CONNECTION),
        ("connect(f\"dbname='NEXUS_template' host={host}\")", RULE_CONNECTION),
        # A slot number completing a later part of an f-string (final round).
        ("connect(f\"host={host} dbname='save_{slot:02d}'\")", RULE_CONNECTION),
        ('connect(f"host={host} dbname=save_{slot:02d}")', RULE_CONNECTION),
        # Shell operators glued to the database argument (final round).
        ('subprocess.run("pg_dump -d save_04>dump.sql", shell=True)', RULE_SUBPROCESS),
        (
            'subprocess.run(args="pg_dump -d save_04; true", shell=True)',
            RULE_SUBPROCESS,
        ),
        ('subprocess.run("pg_dump -d save_04;true", shell=True)', RULE_SUBPROCESS),
        ('run("pg_dump -d save_04&&true", shell=True)', RULE_SUBPROCESS),
        ('run("pg_dump -d save_04 && true", shell=True)', RULE_SUBPROCESS),
        ('run("pg_dump -d save_04||true", shell=True)', RULE_SUBPROCESS),
        ('run("pg_dump -d save_04|gzip", shell=True)', RULE_SUBPROCESS),
        ('run("psql -d NEXUS_template<in.sql", shell=True)', RULE_SUBPROCESS),
        ('run("pg_dump -d save_04&", shell=True)', RULE_SUBPROCESS),
        ("run(\"pg_dump -d 'save_04'>dump.sql\", shell=True)", RULE_SUBPROCESS),
        ('run(["pg_dump -d save_04>dump.sql"], shell=True)', RULE_SUBPROCESS),
        ('run(f"pg_dump -d save_04>{out}", shell=True)', RULE_SUBPROCESS),
        ('run("pg_dump -d \'save_04>x", shell=True)', RULE_SUBPROCESS),
        # Literal keyword expansion of include_data (review of PR #1045).
        (
            "disposable_slot_database('qa_probe', source_db='save_04', "
            "**{'include_data': True})",
            RULE_DATA_CLONE,
        ),
        (
            "disposable_slot_database('qa_probe', **dict(include_data=True))",
            RULE_DATA_CLONE,
        ),
        (
            "disposable_slot_database('qa_probe', **{**{'include_data': True}})",
            RULE_DATA_CLONE,
        ),
        # A dict(...) call's positional dict literal (final round).
        (
            "disposable_slot_database('qa', **dict({'include_data': True}))",
            RULE_DATA_CLONE,
        ),
        (
            "disposable_slot_database('qa', **dict(dict({'include_data': True})))",
            RULE_DATA_CLONE,
        ),
        ("connect(**dict({'dbname': 'save_02'}))", RULE_CONNECTION),
    ],
)
def test_each_refused_spelling_is_found(source: str, rule: str) -> None:
    """Each rule fires on the spelling it names."""

    assert [finding.rule for finding in scan_source(source, "probe.py")] == [rule]


@pytest.mark.parametrize(
    "source",
    [
        "connect('qa640_offline_gate_0123456789ab')",
        "connect('postgres')",
        "connect(dbname)",
        "get_slot_db_url(slot=slot)",
        "slot_dbname(slot)",
        "route_slot_to_disposable(patch, slot=4, dbname=clone)",
        "disposable_slot_database('qa640_x')",
        "FAKE_DBNAME = 'fake_wizard_slot'",
        "connect('qa640_save_05_copy')",
        "subprocess.run(['pg_dump', '--dbname', dbname], check=True)",
        # A marked module may clone an owner corpus with data.
        "pytestmark = pytest.mark.requires_corpus\n"
        "disposable_slot_database('qa', source_db='save_04', include_data=True)",
        "slot_clone(slot)",
        "measure_clone('qa640_766_x', config)",
        "pytestmark = pytest.mark.requires_corpus\nslot_clone(1)",
        "connect(\"dbname='qa640_save_04_copy'\")",
        "disposable_slot_database('qa640_x', **{'include_data': False})",
        "subprocess.run(['pg_dump', '--dbname', f\"dbname='{clone}'\"])",
        "subprocess.run('pg_dump -d qa640_save_04_copy>dump.sql', shell=True)",
        "subprocess.run('pg_dump -d save_04>dump.sql')",
        "connect(f\"host={host} dbname='qa640_{slot:02d}'\")",
        "disposable_slot_database('qa', **dict({'include_data': False}))",
    ],
)
def test_disposable_and_marked_spellings_pass(source: str) -> None:
    """Disposable names, variables, and marked corpus clones are not findings."""

    assert scan_source(source, "probe.py") == []
