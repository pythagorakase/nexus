#!/usr/bin/env python3
"""Require COMMENT ON for every schema object a new migration creates.

PostgreSQL comments are the NEXUS schema reference (docs/database.md). The
PostgreSQL-gated ratchet in tests/test_schema_documentation_pg.py checks table,
column, enum, function, and view coverage on a live clone; this stdlib-only lint
runs offline at commit time and covers every object kind a migration adds.

For each migrations/NNN_*.sql file, and each SQL string literal in an
NNN_*.py migration, numbered above WATERMARK, the lint finds:

* CREATE TABLE and CREATE FOREIGN TABLE: the table and every column declared
  in its body;
* ALTER TABLE ... ADD [COLUMN]: each added column;
* CREATE TYPE ... AS ENUM;
* CREATE [OR REPLACE] FUNCTION and PROCEDURE, one per argument signature;
* CREATE [OR REPLACE] VIEW and CREATE MATERIALIZED VIEW;

including DDL inside DO blocks and EXECUTE commands (``||`` operands are
joined, with ``{}`` standing for each operand that is not a literal), and
requires a non-blank COMMENT ON TABLE/FOREIGN TABLE/COLUMN/TYPE/FUNCTION/
PROCEDURE/VIEW/MATERIALIZED VIEW for each in the same file (COMMENT ON ROUTINE
documents a function or a procedure; a foreign table is documented only by
COMMENT ON FOREIGN TABLE, which is the one form PostgreSQL accepts for it).
ALTER FOREIGN TABLE ... ADD COLUMN is not checked. Unqualified names resolve
to ``public``, or to the schema a CREATE SCHEMA statement creates for its own
elements; unquoted identifiers fold to lower case, quoted identifiers keep
their exact spelling. Temporary tables and views are exempt because they end
with the migration session. Not seen: SQL a Python migration does not spell as
a string literal in its own file (an imported constant such as
``from nexus.x import DDL; cur.execute(DDL)``, names joined only at run time
such as ``cur.execute(A + B)``, a file it reads, or a bytes literal).

A routine comment documents the overload PostgreSQL resolves it to. Argument
types compare after parameter names, modes, and DEFAULT clauses are dropped,
unquoted words fold to lower case, and whitespace collapses. Type modifiers,
interval fields, and array bounds drop as well, because they do not identify a
routine; every array spelling reads ``[]``; and a built-in alias reads as the
name PostgreSQL prints (_TYPE_ALIASES), so ``int`` matches ``integer`` and
``varchar(20)`` matches ``character varying``. A function comment lists the
function's non-OUT argument types; a procedure comment may instead list every
argument type when it marks none OUT. A comment without an argument list names
the one overload of its kind that the file creates, and a comment that names
more than one documents none, because PostgreSQL rejects it as not unique.

DDL that cannot be verified statically fails rather than passing: verbs,
object kinds, names, and ALTER TABLE actions built at run time (f-strings,
``+`` or ``||`` with a non-literal operand, psycopg2 placeholders,
format('%I')), including a Python string passed straight to execute() whose
command starts with a placeholder; an EXECUTE whose command does not start
with literal text, such as EXECUTE of a variable; a CREATE, ALTER, or ALTER
TABLE that names no object kind or action, which can only be a fragment of a
command assembled at run time; columns a statement does not declare
(CREATE TABLE ... AS without a column list, PARTITION OF, OF type, INHERITS,
or LIKE whose options, applied left to right, do not include COMMENTS);
IMPORT FOREIGN SCHEMA; and SELECT ... INTO outside PL/pgSQL. SELECT ... INTO
written as a PL/pgSQL statement in a DO body assigns a variable, creates
nothing, and is not checked; inside an EXECUTE command it is SQL and is
checked. A COMMENT that is NULL or blank is reported as removed documentation.

Usage
-----
    python scripts/check_migration_comments.py
    python scripts/check_migration_comments.py --migrations-dir path/to/migrations
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIGRATIONS_DIR = REPO_ROOT / "migrations"

# Migrations at or below this number predate the lint; the PostgreSQL ratchet
# and config/schema_docs_baseline.json own their debt. Never raise it to exempt
# a new migration.
WATERMARK = 129

# Mirrors scripts/migrate.py discover_migrations(), which imports psycopg2.
MIGRATION_FILE = re.compile(r"^(\d{3})_.+\.(sql|py)$")

_I = re.IGNORECASE
_IDENTIFIER = r'(?:"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_$]*)'
_DOTTED_NAME = re.compile(rf"{_IDENTIFIER}(?:\s*\.\s*{_IDENTIFIER})*")
_NAME_PART = re.compile(_IDENTIFIER)
# A %(name)s placeholder is one token, so a message names it whole.
_RAW_TOKEN = re.compile(r'(?:"(?:[^"]|"")*"|%\(\w+\)[sIL]|[^\s(),;"])+')
_NAME_END = frozenset(" \t\r\n\f\v(),;*")
_PLAIN_NAME = re.compile(r"[a-z_][a-z0-9_$]*")
_IDENT_CHAR = re.compile(r"[A-Za-z0-9_$]")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")

_CREATE_TABLE = re.compile(
    r"\bCREATE\s+(?:(?:GLOBAL|LOCAL)\s+)?"
    r"(?:(?P<temp>TEMP|TEMPORARY)\s+|UNLOGGED\s+|(?P<foreign>FOREIGN)\s+)?"
    r"TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
    _I,
)
# What follows the INTO of a SELECT INTO, as CREATE TABLE spells it.
_SELECT_INTO_TARGET = re.compile(
    r"\s*(?:(?:GLOBAL|LOCAL)\s+)?(?:(?P<temp>TEMP|TEMPORARY)\s+|UNLOGGED\s+)?"
    r"(?:TABLE\s+)?",
    _I,
)
# Words that decide whether a statement is a SELECT INTO: the first of them at
# parenthesis depth 0 names the command, and a later depth-0 INTO its target.
_DML_VERBS = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"})
_IMPORT_FOREIGN_SCHEMA = re.compile(r"\bIMPORT\s+FOREIGN\s+SCHEMA\b", _I)
_ALTER_TABLE = re.compile(
    r"\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(?!ALL\s+IN\b)", _I
)
_ADD_ACTION = re.compile(
    r"\s*ADD\s+(?P<column>COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?", _I
)
_CREATE_TYPE = re.compile(r"\bCREATE\s+TYPE\s+", _I)
_AS_ENUM = re.compile(r"\s*AS\s+ENUM\b", _I)
_CREATE_ROUTINE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?P<kind>FUNCTION|PROCEDURE)\s+", _I
)
_CREATE_VIEW = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:(?P<temp>TEMP|TEMPORARY)\s+)?"
    r"(?:RECURSIVE\s+)?VIEW\s+",
    _I,
)
_CREATE_MATVIEW = re.compile(
    r"\bCREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?", _I
)
_COMMENT_ON = re.compile(
    r"\bCOMMENT\s+ON\s+(?P<kind>MATERIALIZED\s+VIEW|FOREIGN\s+TABLE|TABLE|COLUMN"
    r"|TYPE|FUNCTION|PROCEDURE|ROUTINE|VIEW)\s+",
    _I,
)
_IS = re.compile(r"\s*IS\b", _I)
_CREATE_SCHEMA = re.compile(
    r"\s*CREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:AUTHORIZATION\s+)?", _I
)
_DO = re.compile(r"\bDO\s+(?:LANGUAGE\s+\w+\s+)?", _I)
# PL/pgSQL EXECUTE, not trigger EXECUTE FUNCTION/PROCEDURE or GRANT EXECUTE ON.
_EXECUTE = re.compile(
    r"\bEXECUTE(?!\s*(?:(?:FUNCTION|PROCEDURE|ON)\b|,))\s+"
    r"(?P<format>format\s*\(\s*)?",
    _I,
)
_EXECUTE_END = re.compile(r"\b(?:INTO|USING|LOOP)\b", _I)
# Values filled in at run time: str.format and f-strings (rendered as {}),
# psycopg2 parameters, and format() specifiers.
_PLACEHOLDER_SOURCE = r"(?:\{[^{}\s]*\}|%(?:\(\w+\)|\d+\$)?[sIL])"
_PLACEHOLDER = re.compile(_PLACEHOLDER_SOURCE)
# Where a command's verb stands: the statement start, or a PL/pgSQL statement
# after one of these words inside a DO body.
_VERB_POSITION = re.compile(r"\b(?:BEGIN|THEN|ELSE|LOOP)\b", _I)
# Words between CREATE and the object kind (CREATE OR REPLACE TEMP VIEW, ...).
_CREATE_MODIFIERS = {
    "OR",
    "REPLACE",
    "GLOBAL",
    "LOCAL",
    "TEMP",
    "TEMPORARY",
    "UNLOGGED",
    "FOREIGN",
    "RECURSIVE",
    "MATERIALIZED",
    "UNIQUE",
    "CONSTRAINT",
    "DEFAULT",
    "TRUSTED",
    "PROCEDURAL",
}
_DDL_AFTER_PLACEHOLDER = re.compile(
    r"\s+(?:\S+\s+){0,2}(?:TABLE|VIEW|TYPE|FUNCTION|PROCEDURE|COLUMN)\b", _I
)
_INHERITS = re.compile(r"\bINHERITS\b", _I)
_LIKE_OPTION = re.compile(r"\b(INCLUDING|EXCLUDING)\s+(\w+)", _I)

# Table elements and ALTER TABLE ... ADD targets that are not columns.
_NON_COLUMN_WORDS = {"CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "EXCLUDE"}

# A Python string can only create or document an object if it matches one of
# these; other literals (log text, error messages) are not lexed as SQL. The
# first argument of these methods is SQL by construction and always lexed.
_EXECUTION_METHODS = {"execute", "executemany"}
_PY_SQL_HINT = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:\w+\s+){0,3}"
    r"(?:TABLE|TYPE|FUNCTION|PROCEDURE|VIEW)\b"
    r"|^\s*(?:CREATE|ALTER)\b"
    rf"|\b(?:CREATE|ALTER)\s+(?:\w+\s+){{0,3}}{_PLACEHOLDER_SOURCE}"
    r"|\bALTER\s+TABLE\b|\bADD\s+COLUMN\b|\bCOMMENT\s+ON\b"
    r"|\bDO\s+(?:LANGUAGE\s+\w+\s+)?(?:\$|E?')"
    r"|\bEXECUTE\s+(?:format\s*\(\s*)?(?:\$|E?')"
    r"|\bIMPORT\s+FOREIGN\s+SCHEMA\b"
    r"|\A\s*(?:WITH\b[\s\S]*\bSELECT|SELECT)\b[\s\S]*\bINTO\b",
    _I,
)
# A placeholder before DDL words ("{} TABLE t") marks SQL only alongside a DDL
# verb; alone it is ordinary log text such as "{} rows copied into table t".
_PY_PLACEHOLDER_DDL_HINT = re.compile(
    rf"{_PLACEHOLDER_SOURCE}\s+(?:\w+\s+){{0,3}}"
    r"(?:TABLE|TYPE|FUNCTION|PROCEDURE|VIEW|COLUMN)\b",
    _I,
)
_PY_DDL_VERB = re.compile(r"\b(?:CREATE|ALTER)\b", _I)


def _looks_like_sql(rendered: str) -> bool:
    """Whether a rendered Python string can create or document an object."""
    return bool(
        _PY_SQL_HINT.search(rendered)
        or (_PY_PLACEHOLDER_DDL_HINT.search(rendered) and _PY_DDL_VERB.search(rendered))
    )


# Obligation kind -> the COMMENT ON object type that documents it.
_COMMENT_KINDS = {
    "table": "TABLE",
    "foreign table": "FOREIGN TABLE",
    "column": "COLUMN",
    "enum": "TYPE",
    "function": "FUNCTION",
    "procedure": "PROCEDURE",
    "view": "VIEW",
    "materialized view": "MATERIALIZED VIEW",
}
_DOCUMENTED_KINDS = {label: kind for kind, label in _COMMENT_KINDS.items()}
# COMMENT ON object types that document a routine, and the kinds each covers.
_ROUTINE_COMMENT_KINDS = {
    "FUNCTION": frozenset({"function"}),
    "PROCEDURE": frozenset({"procedure"}),
    "ROUTINE": frozenset({"function", "procedure"}),
}
# Argument modes; PostgreSQL accepts one before or after the parameter name.
_ARGUMENT_MODES = frozenset({"IN", "OUT", "INOUT", "VARIADIC"})
# Words that start a built-in type and cannot name a parameter, so an argument
# that begins with one has no name: ``character varying`` is one type, while
# ``p character varying`` names p. ``double`` can name a parameter, so it
# starts a type only before ``precision``.
_TYPE_START_WORDS = frozenset(
    "bigint bit boolean char character dec decimal float int integer interval "
    "national nchar numeric real smallint time timestamp varchar".split()
)
# Built-in type spellings PostgreSQL treats as one type, mapped to the name its
# format_type prints; any other spelling compares as written. Only unquoted
# words match, so the quoted single-byte type "char" stays distinct from char.
# serial and bigserial read as their integer types, although PostgreSQL rejects
# them as argument types. float(p) is real for p up to 24 and double precision
# above (_canonical_type).
_TYPE_ALIASES = {
    alias: canonical
    for canonical, aliases in (
        ("integer", ("int", "int4", "serial")),
        ("bigint", ("int8", "bigserial")),
        ("smallint", ("int2",)),
        ("boolean", ("bool",)),
        ("character varying", ("varchar",)),
        ("character", ("char",)),
        ("double precision", ("float", "float8")),
        ("real", ("float4",)),
        ("numeric", ("decimal",)),
        ("bit varying", ("varbit",)),
        ("timestamp with time zone", ("timestamptz",)),
        ("timestamp without time zone", ("timestamp",)),
        ("time with time zone", ("timetz",)),
        ("time without time zone", ("time",)),
    )
    for alias in aliases
}
_FLOAT_PRECISION = re.compile(r"float\((\d+)\)")

# One routine argument: its mode (None when unmarked) and its spelled type.
_Argument = tuple[str | None, str]
# What identifies a routine overload: kind, qualified name, and input types.
_Overload = tuple[str, tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True)
class Finding:
    """One undocumented or statically unverifiable object at file:line."""

    path: Path
    line: int
    message: str

    def render(self, root: Path = REPO_ROOT) -> str:
        """Return ``path:line: message`` with the path relative to root if possible."""
        try:
            shown = self.path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            shown = str(self.path)
        return f"{shown}:{self.line}: {self.message}"


@dataclass(frozen=True)
class _Literal:
    """A string literal's content span, quoting style, and closing offset."""

    content_start: int
    content_end: int
    kind: str  # "quote", "escape" (E'...'), or "dollar"
    end: int  # offset just past the closing delimiter

    def text(self, source: str) -> str:
        raw = source[self.content_start : self.content_end]
        if self.kind == "dollar":
            return raw
        if self.kind == "escape":
            raw = re.sub(r"\\(.)", r"\1", raw, flags=re.DOTALL)
        return raw.replace("''", "'")


@dataclass(frozen=True)
class _Signature:
    """A routine's argument types, spelled as the lint compares them."""

    inputs: tuple[str, ...]  # IN, INOUT, and VARIADIC arguments
    everything: tuple[str, ...]  # every argument, OUT included

    @classmethod
    def of(cls, arguments: tuple[_Argument, ...]) -> _Signature:
        return cls(
            tuple(spelled for mode, spelled in arguments if mode != "OUT"),
            tuple(spelled for _, spelled in arguments),
        )


def _routine_display(key: tuple[str, ...], types: tuple[str, ...]) -> str:
    return f"{_display(key)}({', '.join(types)})"


@dataclass(frozen=True)
class _Obligation:
    """An object a migration creates, which needs a COMMENT ON in the same file."""

    kind: str
    key: tuple[str, ...]
    line: int
    signature: _Signature | None = None  # functions and procedures only

    def describe(self) -> str:
        name = _display(self.key)
        if self.signature is not None:
            name = _routine_display(self.key, self.signature.inputs)
        return f"{self.kind} {name} has no COMMENT ON {_COMMENT_KINDS[self.kind]}"


@dataclass(frozen=True)
class _RoutineComment:
    """A non-blank COMMENT ON FUNCTION, PROCEDURE, or ROUTINE."""

    label: str
    key: tuple[str, ...]
    arguments: tuple[_Argument, ...] | None  # None when it gives no list
    line: int

    def names(self, kind: str, key: tuple[str, ...], signature: _Signature) -> bool:
        """Whether PostgreSQL could resolve this comment to that routine.

        Checked against PostgreSQL 17: a function comment names the function's
        non-OUT types (OUT-marked entries are ignored); a procedure comment
        that marks no argument OUT may list either the input types or every
        argument type.
        """
        if key != self.key or kind not in _ROUTINE_COMMENT_KINDS[self.label]:
            return False
        if self.arguments is None:
            return True
        listed = _Signature.of(self.arguments)
        if kind == "procedure" and listed.inputs == listed.everything:
            return listed.everything in (signature.inputs, signature.everything)
        return listed.inputs == signature.inputs

    def ambiguity(self, named: set[_Overload]) -> str:
        shown = _display(self.key)
        if self.arguments is not None:
            shown = _routine_display(
                self.key,
                tuple(
                    f"OUT {spelled}" if mode == "OUT" else spelled
                    for mode, spelled in self.arguments
                ),
            )
        listed = ", ".join(
            sorted(_routine_display(key, inputs) for _, key, inputs in named)
        )
        return (
            f"COMMENT ON {self.label} {shown} matches {len(named)} overloads this "
            f"migration creates ({listed}); PostgreSQL rejects it as not unique, "
            "so it documents none"
        )


@dataclass
class _Scan:
    """Obligations, documenting comments, and findings collected from one file."""

    obligations: list[_Obligation] = field(default_factory=list)
    comments: set[tuple[str, tuple[str, ...]]] = field(default_factory=set)
    routine_comments: list[_RoutineComment] = field(default_factory=list)
    findings: list[tuple[int, str]] = field(default_factory=list)

    def resolve(self) -> list[tuple[int, str]]:
        """Return (line, message) for every finding once the file is scanned.

        A routine comment documents the one overload it names; a comment that
        names several documents none and is reported instead.
        """
        findings = list(self.findings)
        documented: set[_Overload] = set()
        for comment in self.routine_comments:
            named = {
                (obligation.kind, obligation.key, signature.inputs)
                for obligation in self.obligations
                if (signature := obligation.signature) is not None
                and comment.names(obligation.kind, obligation.key, signature)
            }
            if len(named) == 1:
                documented |= named
            elif named:
                findings.append((comment.line, comment.ambiguity(named)))
        for obligation in self.obligations:
            if obligation.signature is None:
                is_documented = (obligation.kind, obligation.key) in self.comments
            else:
                overload = (
                    obligation.kind,
                    obligation.key,
                    obligation.signature.inputs,
                )
                is_documented = overload in documented
            if not is_documented:
                findings.append((obligation.line, obligation.describe()))
        return findings


class _LexError(Exception):
    def __init__(self, offset: int, message: str) -> None:
        super().__init__(message)
        self.offset = offset
        self.message = message


def _lex(sql: str) -> tuple[str, dict[int, _Literal]]:
    """Blank comments and string contents, keeping offsets and newlines intact.

    Quoted identifiers stay visible because they are names. Literals are keyed
    by the offset of their opening delimiter.
    """
    masked = list(sql)
    literals: dict[int, _Literal] = {}

    def blank(start: int, end: int) -> None:
        for index in range(start, end):
            if masked[index] != "\n":
                masked[index] = " "

    index, size = 0, len(sql)
    while index < size:
        char = sql[index]
        if sql.startswith("--", index):
            end = sql.find("\n", index)
            end = size if end == -1 else end
            blank(index, end)
            index = end
        elif sql.startswith("/*", index):
            depth, cursor = 1, index + 2
            while depth:
                if cursor >= size:
                    raise _LexError(index, "unterminated block comment")
                if sql.startswith("/*", cursor):
                    depth, cursor = depth + 1, cursor + 2
                elif sql.startswith("*/", cursor):
                    depth, cursor = depth - 1, cursor + 2
                else:
                    cursor += 1
            blank(index, cursor)
            index = cursor
        elif char == "'":
            escape = (
                index >= 1
                and sql[index - 1] in "eE"
                and (index == 1 or not _IDENT_CHAR.match(sql[index - 2]))
            )
            cursor = index + 1
            while True:
                if cursor >= size:
                    raise _LexError(index, "unterminated quoted string")
                if escape and sql[cursor] == "\\":
                    cursor += 2
                elif sql.startswith("''", cursor):
                    cursor += 2
                elif sql[cursor] == "'":
                    break
                else:
                    cursor += 1
            kind = "escape" if escape else "quote"
            literals[index] = _Literal(index + 1, cursor, kind, cursor + 1)
            blank(index + 1, cursor)
            index = cursor + 1
        elif char == '"':
            cursor = index + 1
            while True:
                if cursor >= size:
                    raise _LexError(index, "unterminated quoted identifier")
                if sql.startswith('""', cursor):
                    cursor += 2
                elif sql[cursor] == '"':
                    break
                else:
                    cursor += 1
            index = cursor + 1
        elif char == "$" and (index == 0 or not _IDENT_CHAR.match(sql[index - 1])):
            tag = _DOLLAR_TAG.match(sql, index)
            if tag is None:
                index += 1
                continue
            close = sql.find(tag.group(), tag.end())
            if close == -1:
                raise _LexError(index, "unterminated dollar-quoted string")
            end = close + len(tag.group())
            literals[index] = _Literal(tag.end(), close, "dollar", end)
            blank(tag.end(), close)
            index = end
        else:
            index += 1
    return "".join(masked), literals


def _statements(masked: str) -> Iterator[tuple[int, int]]:
    """Yield (start, end) offsets of semicolon-separated statements."""
    start = 0
    for match in re.finditer(";", masked):
        yield start, match.start()
        start = match.end()
    yield start, len(masked)


def _split_top_level(text: str, separator: str = ",") -> list[tuple[int, str]]:
    """Split on separator outside parentheses, brackets, and quoted identifiers."""
    parts: list[tuple[int, str]] = []
    depth, quoted, start, index = 0, False, 0, 0
    while index < len(text):
        char = text[index]
        if char == '"':
            quoted = not quoted
        elif quoted:
            pass
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif depth == 0 and text.startswith(separator, index):
            parts.append((start, text[start:index]))
            start = index = index + len(separator)
            continue
        index += 1
    parts.append((start, text[start:]))
    return parts


def _matching_paren(text: str, open_index: int) -> int | None:
    """Return the index of the parenthesis closing the one at open_index."""
    depth, quoted = 0, False
    for index in range(open_index, len(text)):
        char = text[index]
        if char == '"':
            quoted = not quoted
        elif quoted:
            continue
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _identifier(part: str) -> str:
    if part.startswith('"'):
        return part[1:-1].replace('""', '"')
    return part.lower()


def _parse_name(raw: str) -> tuple[str, ...] | None:
    """Parse a possibly qualified, possibly quoted name; None if not literal."""
    if not _DOTTED_NAME.fullmatch(raw):
        return None
    return tuple(_identifier(part) for part in _NAME_PART.findall(raw))


def _read_name(text: str, pos: int) -> tuple[str, tuple[str, ...] | None, int]:
    """Read the raw name token at pos; return (raw, parsed name, end offset)."""
    while pos < len(text) and text[pos].isspace():
        pos += 1
    dotted = _DOTTED_NAME.match(text, pos)
    if dotted and (dotted.end() == len(text) or text[dotted.end()] in _NAME_END):
        return dotted.group(), _parse_name(dotted.group()), dotted.end()
    match = _RAW_TOKEN.match(text, pos)
    if match is None:
        return "", None, pos
    return match.group(), None, match.end()


def _qualify(
    parts: tuple[str, ...] | None, size: int, schema: str
) -> tuple[str, ...] | None:
    """Qualify a name of `size` unqualified parts with the default schema."""
    if parts is None:
        return None
    if len(parts) == size:
        return (schema, *parts)
    if len(parts) == size + 1:
        return parts
    return None


def _display(key: tuple[str, ...]) -> str:
    return ".".join(
        part if _PLAIN_NAME.fullmatch(part) else '"' + part.replace('"', '""') + '"'
        for part in key
    )


def _element_schema(statement: str) -> str:
    """Return the schema that unqualified names in one statement belong to.

    ``CREATE SCHEMA s CREATE TABLE t (...)`` creates ``s.t``; every other
    statement resolves unqualified names to ``public``.
    """
    match = _CREATE_SCHEMA.match(statement)
    if match is None:
        return "public"
    _, parts, _ = _read_name(statement, match.end())
    return parts[0] if parts is not None and len(parts) == 1 else "public"


def _like_copies_comments(element: str) -> bool:
    """Whether a LIKE element's options, applied left to right, copy comments.

    ALL stands for every option, so a later EXCLUDING COMMENTS undoes an
    earlier INCLUDING ALL and vice versa.
    """
    copies = False
    for verb, option in _LIKE_OPTION.findall(element):
        if option.upper() in ("ALL", "COMMENTS"):
            copies = verb.upper() == "INCLUDING"
    return copies


def _next_token(text: str, pos: int) -> tuple[int, str]:
    """Return (offset, raw token) of the first token at or after pos."""
    while pos < len(text) and text[pos].isspace():
        pos += 1
    match = _RAW_TOKEN.match(text, pos)
    return pos, match.group() if match else ""


def _first_token(text: str) -> tuple[int, str]:
    """Return (offset, raw token) of the first token in a list element."""
    stripped = len(text) - len(text.lstrip())
    match = _RAW_TOKEN.match(text, stripped)
    return stripped, match.group() if match else ""


def _is_keyword(token: str, words: set[str]) -> bool:
    return not token.startswith('"') and token.upper() in words


def _quoted_end(text: str, index: int) -> int:
    """Return the offset just past the quoted identifier opening at index."""
    close = index + 1
    while True:
        close = text.find('"', close)
        if close == -1:
            return len(text)
        if not text.startswith('""', close):
            return close + 1
        close += 2


def _top_level_words(text: str) -> Iterator[tuple[int, str]]:
    """Yield (offset, upper-cased word) for each unquoted word at depth 0.

    Words inside parentheses or brackets and quoted identifiers are skipped.
    """
    depth, index = 0, 0
    while index < len(text):
        char = text[index]
        if char == '"':
            index = _quoted_end(text, index)
            continue
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif depth == 0 and (index == 0 or not _IDENT_CHAR.match(text[index - 1])):
            word = _WORD.match(text, index)
            if word:
                yield index, word.group().upper()
                index = word.end()
                continue
        index += 1


def _argument_words(text: str) -> list[str]:
    """Split one argument into words, stopping at its DEFAULT or ``=`` clause.

    Unquoted text folds to lower case; quoted identifiers keep their spelling
    and quotes. Whitespace inside parentheses and brackets is dropped, and a
    word that starts with ``.``, ``(``, or ``[``, or follows a ``.``, joins
    the word before it, so ``numeric( 5, 2 )`` reads ``numeric(5,2)`` and
    ``assets . mood []`` reads ``assets.mood[]``. ``ARRAY`` and ``ARRAY[n]``
    after a type read ``[]`` and ``[n]``.
    """
    raw: list[str] = []
    word, depth, index = "", 0, 0
    while index < len(text):
        char = text[index]
        if char == '"':
            end = _quoted_end(text, index)
            word += text[index:end]
            index = end
            continue
        index += 1
        if char.isspace():
            if depth == 0 and word:
                raw.append(word)
                word = ""
            continue
        if depth == 0 and char == "=":
            break
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        word += char.lower()
    if word:
        raw.append(word)
    words: list[str] = []
    for item in raw:
        if item == "default":
            break
        if item == "array" or item.startswith("array["):
            item = item[len("array") :] or "[]"
        if words and (item[0] in ".([" or words[-1].endswith(".")):
            words[-1] += item
        else:
            words.append(item)
    return words


def _strip_modifiers(spelled: str) -> tuple[str, bool]:
    """Drop parenthesized type modifiers and bracketed array bounds.

    Return what remains and whether a bracket marked an array; quoted
    identifiers are kept whole.
    """
    kept: list[str] = []
    depth, is_array, index = 0, False, 0
    while index < len(spelled):
        char = spelled[index]
        if char == '"' and depth == 0:
            end = _quoted_end(spelled, index)
            kept.append(spelled[index:end])
            index = end
            continue
        if char in "([":
            is_array = is_array or (char == "[" and depth == 0)
            depth += 1
        elif char in ")]":
            depth -= 1
        elif depth == 0:
            kept.append(char)
        index += 1
    return "".join(kept).strip(), is_array


def _canonical_type(spelled: str) -> str:
    """Spell a type the way PostgreSQL identifies it in a routine signature."""
    base, is_array = _strip_modifiers(spelled)
    precision = _FLOAT_PRECISION.match(spelled)
    if precision:
        base = "real" if int(precision.group(1)) <= 24 else "double precision"
    elif base.startswith("interval "):
        base = "interval"  # interval fields are type modifiers
    base = _TYPE_ALIASES.get(base, base)
    return f"{base}[]" if is_array else base


def _word_base(word: str) -> str:
    """Return a word without its type modifiers or array bounds."""
    return re.split(r"[(\[]", word, maxsplit=1)[0]


def _parse_argument(text: str) -> _Argument:
    """Return (mode, spelled type) for one argument, dropping name and DEFAULT."""
    words = _argument_words(text)
    mode: str | None = None
    if words and words[0].upper() in _ARGUMENT_MODES:
        mode, words = words[0].upper(), words[1:]
    elif len(words) > 2 and words[1].upper() in _ARGUMENT_MODES:
        mode, words = words[1].upper(), [words[0], *words[2:]]
    if len(words) > 1:
        first = _word_base(words[0])
        if first == "double":
            names_parameter = _word_base(words[1]) != "precision"
        else:
            names_parameter = first not in _TYPE_START_WORDS
        if names_parameter:
            words = words[1:]
    return mode, _canonical_type(" ".join(words))


def _routine_arguments(
    masked: str, pos: int
) -> tuple[tuple[_Argument, ...] | None, int]:
    """Parse the argument list at pos; return (arguments, end offset).

    The arguments are None when no parenthesized list starts at pos.
    """
    while pos < len(masked) and masked[pos].isspace():
        pos += 1
    if not masked.startswith("(", pos):
        return None, pos
    close = _matching_paren(masked, pos)
    if close is None:
        return None, pos
    arguments = tuple(
        _parse_argument(text)
        for _, text in _split_top_level(masked[pos + 1 : close])
        if text.strip()
    )
    return arguments, close + 1


class _SqlScanner:
    """Scan one SQL source: a file, a Python literal, or a DO/EXECUTE body.

    ``plpgsql`` marks a DO body, where SELECT INTO assigns a variable instead
    of creating a table.
    """

    def __init__(
        self, sql: str, first_line: int, scan: _Scan, *, plpgsql: bool = False
    ) -> None:
        self.sql = sql
        self.first_line = first_line
        self.scan = scan
        self.plpgsql = plpgsql
        self.masked, self.literals = _lex(sql)
        self.schema = "public"

    def line_at(self, offset: int) -> int:
        return self.first_line + self.sql.count("\n", 0, offset)

    def finding(self, offset: int, message: str) -> None:
        self.scan.findings.append((self.line_at(offset), message))

    def unresolvable(self, offset: int, statement: str, raw: str) -> None:
        self.finding(
            offset,
            f"{statement} names {raw or '<nothing>'!r}, which is not a literal "
            "identifier; name the object literally so its COMMENT can be verified",
        )

    def require(
        self,
        kind: str,
        key: tuple[str, ...],
        offset: int,
        signature: _Signature | None = None,
    ) -> None:
        self.scan.obligations.append(
            _Obligation(kind, key, self.line_at(offset), signature)
        )

    def run(self) -> None:
        for start, end in _statements(self.masked):
            statement = self.masked[start:end]
            self.schema = _element_schema(statement)
            self._run_time_heads(statement, start)
            self._create_table(statement, start)
            self._alter_table(statement, start)
            self._create_named(statement, start)
            self._import_foreign_schema(statement, start)
            self._select_into(statement, start)
            self._comments(statement, start)
            for match in _DO.finditer(statement):
                literal = self._literal_at(start + match.end())
                if literal is not None:
                    _scan_sql(
                        literal.text(self.sql),
                        self.line_at(literal.content_start),
                        self.scan,
                        plpgsql=True,
                    )
            for match in _EXECUTE.finditer(statement):
                self._execute(statement, start, match)

    def _literal_at(self, pos: int) -> _Literal | None:
        if self.masked[pos : pos + 2] in ("E'", "e'"):
            pos += 1
        return self.literals.get(pos)

    def _literal_run(self, begin: int, finish: int) -> list[_Literal] | None:
        """Return the literals spanning begin..finish, or None for any other text.

        Adjacent literals separated only by whitespace are one constant, as in
        ``'DELETE FROM t '`` on one line and ``'WHERE ...'`` on the next.
        """
        run: list[_Literal] = []
        while True:
            literal = self._literal_at(begin)
            if literal is None:
                return None
            run.append(literal)
            gap = self.masked[literal.end : finish]
            if not gap.strip():
                return run
            begin = literal.end + len(gap) - len(gap.lstrip())

    def _run_time_heads(self, statement: str, start: int) -> None:
        """Report commands whose verb or object kind is filled in at run time.

        ``'CREATE ' || kind || ' t (id int)'`` becomes ``CREATE {} t (id int)``,
        which no DDL pattern matches, so it would otherwise pass. A verb
        position is the statement start, where any placeholder fails, or the
        word after BEGIN/THEN/ELSE/LOOP in a DO body, where a placeholder fails
        only before DDL words because ``CASE ... THEN {}`` is an expression.
        """
        positions = [(0, True)] + [
            (match.end(), False) for match in _VERB_POSITION.finditer(statement)
        ]
        for position, at_start in positions:
            offset, verb = _next_token(statement, position)
            end = offset + len(verb)
            placeholder = _PLACEHOLDER.match(statement, offset) or _PLACEHOLDER.search(
                verb
            )
            if placeholder:
                if at_start or _DDL_AFTER_PLACEHOLDER.match(statement, end):
                    self.finding(
                        start + offset,
                        f"statement begins with {placeholder.group()!r}, which is "
                        "filled in at run time; its schema changes cannot be "
                        "verified",
                    )
                continue
            if not _is_keyword(verb, {"CREATE", "ALTER"}):
                continue
            label = verb.upper()
            kind_offset, kind = _next_token(statement, end)
            while label == "CREATE" and _is_keyword(kind, _CREATE_MODIFIERS):
                kind_offset, kind = _next_token(statement, kind_offset + len(kind))
            placeholder = _PLACEHOLDER.match(
                statement, kind_offset
            ) or _PLACEHOLDER.search(kind)
            if placeholder:
                self.finding(
                    start + offset,
                    f"{label} object kind {placeholder.group()!r} is filled in at "
                    "run time; its schema changes cannot be verified",
                )
            elif not kind:
                self.finding(
                    start + offset,
                    f"{label} names no object kind, so it is a fragment of a "
                    "command assembled at run time; its schema changes cannot be "
                    "verified",
                )
            elif label == "CREATE" and _is_keyword(kind, {"SCHEMA"}):
                schema = _CREATE_SCHEMA.match(statement, offset)
                raw, parts, _ = _read_name(statement, schema.end() if schema else end)
                if parts is None:
                    self.unresolvable(start + offset, "CREATE SCHEMA", raw)

    def _execute(self, statement: str, start: int, match: re.Match[str]) -> None:
        """Scan the command an EXECUTE runs, joining its ``||`` operands.

        Operands that are not a single literal become ``{}``, so a name or
        action assembled at run time is reported where it lands. A command
        that does not start with literal text cannot be read at all.
        """
        pos = match.end()
        if match.group("format"):
            paren = statement.index("(", match.start("format"))
            close = _matching_paren(statement, paren)
            arguments = statement[pos : len(statement) if close is None else close]
            end = pos + len(_split_top_level(arguments)[0][1])
        else:
            stop = _EXECUTE_END.search(statement, pos)
            end = len(statement) if stop is None else stop.start()
        pieces: list[str] = []
        first_line = self.line_at(start + pos)
        for relative, operand in _split_top_level(statement[pos:end], "||"):
            begin = start + pos + relative + len(operand) - len(operand.lstrip())
            finish = start + pos + relative + len(operand.rstrip())
            run = self._literal_run(begin, finish)
            if run is not None:
                if not pieces:
                    first_line = self.line_at(run[0].content_start)
                pieces.append("".join(literal.text(self.sql) for literal in run))
            elif pieces:
                pieces.append("{}")
            else:
                expression = " ".join(self.sql[begin:finish].split())
                self.finding(
                    begin,
                    f"EXECUTE {expression!r} runs a command built at run time; "
                    "its schema changes cannot be verified",
                )
                return
        _scan_sql("".join(pieces), first_line, self.scan)

    def _create_table(self, statement: str, start: int) -> None:
        for match in _CREATE_TABLE.finditer(statement):
            if match.group("temp"):
                continue
            # PostgreSQL documents a foreign table only with COMMENT ON FOREIGN
            # TABLE; COMMENT ON TABLE rejects it as "not a table".
            kind = "foreign table" if match.group("foreign") else "table"
            statement_label = f"CREATE {kind.upper()}"
            offset = start + match.start()
            raw, parts, pos = _read_name(statement, match.end())
            table = _qualify(parts, 1, self.schema)
            if table is None:
                self.unresolvable(offset, statement_label, raw)
                continue
            self.require(kind, table, offset)
            label = f"{statement_label} {_display(table)}"
            while pos < len(statement) and statement[pos].isspace():
                pos += 1
            close = (
                _matching_paren(statement, pos)
                if statement.startswith("(", pos)
                else None
            )
            if close is None:
                self.finding(
                    offset,
                    f"{label} declares no column list; its columns cannot be "
                    "verified",
                )
                continue
            for relative, element in _split_top_level(statement[pos + 1 : close]):
                lead, token = _first_token(element)
                element_offset = start + pos + 1 + relative + lead
                if not token or _is_keyword(token, _NON_COLUMN_WORDS):
                    continue
                if _is_keyword(token, {"LIKE"}):
                    if not _like_copies_comments(element):
                        self.finding(
                            element_offset,
                            f"{label} copies columns with LIKE but without "
                            "INCLUDING COMMENTS; they cannot be verified",
                        )
                    continue
                column = _parse_name(token)
                if column is None or len(column) != 1:
                    self.unresolvable(element_offset, f"{label} column", token)
                    continue
                self.require("column", (*table, column[0]), element_offset)
            if _INHERITS.search(statement, close):
                self.finding(
                    offset, f"{label} INHERITS columns that cannot be verified"
                )

    def _import_foreign_schema(self, statement: str, start: int) -> None:
        """IMPORT FOREIGN SCHEMA creates tables whose names the migration omits."""
        for match in _IMPORT_FOREIGN_SCHEMA.finditer(statement):
            self.finding(
                start + match.start(),
                "IMPORT FOREIGN SCHEMA creates foreign tables it does not name; "
                "their columns cannot be verified",
            )

    def _select_into(self, statement: str, start: int) -> None:
        """Report SELECT INTO, which creates a table without a column list.

        A statement is a SELECT INTO when the first SELECT, INSERT, UPDATE,
        DELETE, or MERGE at parenthesis depth 0 is SELECT and a later depth-0
        INTO follows it. A temporary target is exempt, as CREATE TEMP TABLE
        is. In a DO body (``plpgsql``) SELECT INTO assigns a variable and
        creates nothing, so the rule does not apply there.
        """
        if self.plpgsql:
            return
        words = _top_level_words(statement)
        for _, word in words:
            if word in _DML_VERBS:
                if word != "SELECT":
                    return
                break
        else:
            return
        into = next((offset for offset, word in words if word == "INTO"), None)
        if into is None:
            return
        target = _SELECT_INTO_TARGET.match(statement, into + len("INTO"))
        assert target is not None  # every part of the pattern is optional
        if target.group("temp"):
            return
        offset = start + into
        raw, parts, _ = _read_name(statement, target.end())
        table = _qualify(parts, 1, self.schema)
        if table is None:
            self.unresolvable(offset, "SELECT INTO", raw)
            return
        self.require("table", table, offset)
        self.finding(
            offset,
            f"SELECT INTO {_display(table)} declares no column list; its columns "
            "cannot be verified",
        )

    def _alter_table(self, statement: str, start: int) -> None:
        for match in _ALTER_TABLE.finditer(statement):
            offset = start + match.start()
            raw, parts, pos = _read_name(statement, match.end())
            table = _qualify(parts, 1, self.schema)
            if table is None:
                self.unresolvable(offset, "ALTER TABLE", raw)
                continue
            label = f"ALTER TABLE {_display(table)}"
            star = re.match(r"\s*\*", statement[pos:])
            if star:
                pos += star.end()
            actions = _split_top_level(statement[pos:])
            if not any(action.strip() for _, action in actions):
                self.finding(
                    offset,
                    f"{label} names no action, so it is a fragment of a command "
                    "assembled at run time; its changes cannot be verified",
                )
                continue
            for relative, action in actions:
                lead = len(action) - len(action.lstrip())
                action_offset = start + pos + relative + lead
                placeholder = _PLACEHOLDER.match(action, lead)
                if placeholder:
                    self.finding(
                        action_offset,
                        f"{label} action {placeholder.group()!r} is filled in at "
                        "run time; its changes cannot be verified",
                    )
                    continue
                add = _ADD_ACTION.match(action)
                if add is None:
                    continue
                token_match = _RAW_TOKEN.match(action, add.end())
                token = token_match.group() if token_match else ""
                if not add.group("column") and _is_keyword(token, _NON_COLUMN_WORDS):
                    continue
                column = _parse_name(token)
                if column is None or len(column) != 1:
                    self.unresolvable(action_offset, f"{label} ADD COLUMN", token)
                    continue
                self.require("column", (*table, column[0]), action_offset)

    def _create_named(self, statement: str, start: int) -> None:
        """Enums, functions, procedures, views, and materialized views."""
        for match in _CREATE_TYPE.finditer(statement):
            raw, parts, pos = _read_name(statement, match.end())
            if not _AS_ENUM.match(statement, pos):
                continue
            self._require_named("enum", "CREATE TYPE", parts, raw, start, match)
        for match in _CREATE_ROUTINE.finditer(statement):
            kind = match.group("kind").lower()
            label = f"CREATE {kind.upper()}"
            raw, parts, pos = _read_name(statement, match.end())
            arguments, _ = _routine_arguments(statement, pos)
            if arguments is None and parts is not None:
                self.finding(
                    start + match.start(),
                    f"{label} {raw} has no parseable argument list",
                )
                continue
            signature = None if arguments is None else _Signature.of(arguments)
            self._require_named(kind, label, parts, raw, start, match, signature)
        for pattern, kind in (
            (_CREATE_VIEW, "view"),
            (_CREATE_MATVIEW, "materialized view"),
        ):
            for match in pattern.finditer(statement):
                if match.groupdict().get("temp"):
                    continue
                raw, parts, _ = _read_name(statement, match.end())
                statement_label = f"CREATE {kind.upper()}"
                self._require_named(kind, statement_label, parts, raw, start, match)

    def _require_named(
        self,
        kind: str,
        statement_label: str,
        parts: tuple[str, ...] | None,
        raw: str,
        start: int,
        match: re.Match[str],
        signature: _Signature | None = None,
    ) -> None:
        key = _qualify(parts, 1, self.schema)
        offset = start + match.start()
        if key is None:
            self.unresolvable(offset, statement_label, raw)
            return
        self.require(kind, key, offset, signature)

    def _comments(self, statement: str, start: int) -> None:
        for match in _COMMENT_ON.finditer(statement):
            label = " ".join(match.group("kind").upper().split())
            routine = label in _ROUTINE_COMMENT_KINDS
            raw, parts, pos = _read_name(statement, match.end())
            key = _qualify(parts, 2 if label == "COLUMN" else 1, self.schema)
            arguments: tuple[_Argument, ...] | None = None
            if routine:
                arguments, pos = _routine_arguments(statement, pos)
            is_match = _IS.match(statement, pos)
            if key is None or is_match is None:
                continue
            text_start, text_end = start + is_match.end(), start + len(statement)
            text = "".join(
                literal.text(self.sql)
                for offset, literal in self.literals.items()
                if text_start <= offset < text_end
            )
            if not text.strip():
                self.finding(
                    start + match.start(),
                    f"COMMENT ON {label} {_display(key)} is NULL or blank, which "
                    "removes documentation",
                )
                continue
            if routine:
                line = self.line_at(start + match.start())
                self.scan.routine_comments.append(
                    _RoutineComment(label, key, arguments, line)
                )
            else:
                self.scan.comments.add((_DOCUMENTED_KINDS[label], key))


def _scan_sql(sql: str, first_line: int, scan: _Scan, *, plpgsql: bool = False) -> None:
    """Scan one SQL source whose first character is on first_line.

    ``plpgsql`` is true only for a DO body (see _SqlScanner).
    """
    try:
        scanner = _SqlScanner(sql, first_line, scan, plpgsql=plpgsql)
    except _LexError as error:
        line = first_line + sql.count("\n", 0, error.offset)
        scan.findings.append((line, f"cannot parse SQL: {error.message}"))
        return
    scanner.run()


def _render_string(node: ast.AST) -> str | None:
    """Render a string expression; interpolated values become ``{}``."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        return "".join(
            (
                value.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
                else "{}"
            )
            for value in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _render_string(node.left), _render_string(node.right)
        if left is None and right is None:
            return None
        return (left if left is not None else "{}") + (
            right if right is not None else "{}"
        )
    return None


def python_sql_literals(source: str) -> list[tuple[str, int]]:
    """Return (sql, first line) for each SQL-bearing string in a Python migration.

    Docstrings are skipped; ``+`` concatenations and f-strings are rendered as
    one literal with ``{}`` for each run-time value. A string passed straight
    to ``execute`` or ``executemany`` is SQL whatever its words, so it is always
    returned, and a command whose verb is filled in at run time is reported.
    """
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    executed = {
        id(node.args[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _EXECUTION_METHODS
        and node.args
    }
    found: list[tuple[str, int]] = []

    def visit(node: ast.AST) -> None:
        rendered = _render_string(node)
        if rendered is not None:
            if id(node) in executed or (
                id(node) not in docstrings and _looks_like_sql(rendered)
            ):
                found.append((rendered, getattr(node, "lineno", 1)))
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return found


def check_file(path: Path) -> list[Finding]:
    """Return findings for one migration file, regardless of its number."""
    source = path.read_text(encoding="utf-8")
    scan = _Scan()
    if path.suffix == ".sql":
        _scan_sql(source, 1, scan)
    else:
        try:
            literals = python_sql_literals(source)
        except SyntaxError as error:
            return [Finding(path, error.lineno or 1, f"cannot parse Python: {error}")]
        for sql, line in literals:
            _scan_sql(sql, line, scan)
    findings = [Finding(path, line, message) for line, message in scan.resolve()]
    return sorted(findings, key=lambda finding: (finding.line, finding.message))


def check_migrations(directory: Path, watermark: int = WATERMARK) -> list[Finding]:
    """Return findings for every migration in directory numbered above watermark."""
    if not directory.is_dir():
        raise FileNotFoundError(f"Migrations directory not found: {directory}")
    findings: list[Finding] = []
    for path in sorted(directory.iterdir()):
        match = MIGRATION_FILE.match(path.name)
        if match and path.is_file() and int(match.group(1)) > watermark:
            findings.extend(check_file(path))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the lint from the command line; exit 1 when any finding remains."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIR,
        help="Directory of NNN_*.sql/.py migrations (default: repository migrations/).",
    )
    args = parser.parse_args(argv)
    findings = check_migrations(args.migrations_dir)
    if not findings:
        print(f"OK: every object created after migration {WATERMARK} has a comment.")
        return 0
    print(f"Found {len(findings)} schema documentation finding(s):", file=sys.stderr)
    for finding in findings:
        print(f"  {finding.render()}", file=sys.stderr)
    print(
        "\nNew tables, columns, enums, functions, procedures, and views need a "
        "non-blank COMMENT ON in the same migration (docs/database.md).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
