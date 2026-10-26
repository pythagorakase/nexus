"""Story and player text reaches application logs only at DEBUG (#842).

Ruling 43 (2026-10-26): DEBUG may contain story and player text; INFO and
every higher level redact it. Decision 842-D5 enforces the rule with an AST
sweep over ``nexus/`` and the provider modules: an INFO-or-higher logger call
may not reference a declared story-text name, except inside ``len(...)`` or
the test of a conditional expression. ``METADATA_ONLY_USES`` settles the known
metadata-only uses in advance. A real-path test runs the alias search against
a disposable PostgreSQL clone and reads what reaches the log at each level.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from nexus.agents.memnon.utils.alias_search import hybrid_alias_search
from tests.pg_fixtures import disposable_slot_database, sqlalchemy_url

REPO_ROOT = Path(__file__).resolve().parents[2]

STORY_TEXT_NAMES = frozenset(
    {
        "user_input",
        "user_text",
        "resolved_user_text",
        "note",
        "directive",
        "directives",
        "query",
        "query_text",
        "storyteller_text",
        "choice_text",
        "choices",
        "ui_choices",
        "raw",
        "raw_text",
        "prose",
        "title",
        "text",
    }
)

PROVIDER_MODULES = (
    "scripts/api_openai.py",
    "scripts/api_anthropic.py",
    "scripts/api_openrouter.py",
)

SCANNED = tuple(
    sorted(
        [
            path.relative_to(REPO_ROOT).as_posix()
            for path in (REPO_ROOT / "nexus").rglob("*.py")
        ]
        + list(PROVIDER_MODULES)
    )
)

_WIRE_NOTES = (
    "wire notes hold names, ids, tags, paths and wire messages, and feed the "
    "prompt-window ledger (842-D4)"
)

METADATA_ONLY_USES: dict[tuple[str, str, str], str] = {
    ("nexus/telemetry/usage.py", "validation_attempt", "note"): _WIRE_NOTES,
    ("nexus/telemetry/usage.py", "record_wire_repair", "note"): _WIRE_NOTES,
    ("nexus/agents/memnon/test_idf_dictionary.py", "main", "query"): (
        "standalone CLI main() echoing its own --query argument (842-D9)"
    ),
}

_INFO_OR_ABOVE = frozenset(
    {"info", "warning", "warn", "error", "exception", "critical", "fatal"}
)

Violation = tuple[str, int, str, str]


def _receiver_identifier(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_logging_debug(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "DEBUG"
        and isinstance(node.value, ast.Name)
        and node.value.id == "logging"
    )


def _is_info_or_above(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    receiver = _receiver_identifier(func.value)
    if receiver is None or "log" not in receiver.lower():
        return False
    if func.attr in _INFO_OR_ABOVE:
        return True
    if func.attr == "log":
        return not (call.args and _is_logging_debug(call.args[0]))
    return False


def _story_text_references(node: ast.AST) -> list[str]:
    """Return story-text names referenced in ``node``, outside metadata forms."""

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
    ):
        return []
    if isinstance(node, ast.IfExp):
        return _story_text_references(node.body) + _story_text_references(node.orelse)
    found: list[str] = []
    if isinstance(node, ast.Name) and node.id in STORY_TEXT_NAMES:
        found.append(node.id)
    elif isinstance(node, ast.Attribute) and node.attr in STORY_TEXT_NAMES:
        found.append(node.attr)
    for child in ast.iter_child_nodes(node):
        found.extend(_story_text_references(child))
    return found


class _LogCallScanner(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.functions: list[str] = []
        self.violations: list[Violation] = []

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Call(self, node: ast.Call) -> None:
        if _is_info_or_above(node):
            function = self.functions[-1] if self.functions else "<module>"
            arguments: list[ast.AST] = list(node.args)
            arguments.extend(keyword.value for keyword in node.keywords)
            for argument in arguments:
                for name in _story_text_references(argument):
                    self.violations.append((self.path, node.lineno, function, name))
        self.generic_visit(node)


def story_text_violations(source: str, path: str) -> list[tuple[str, int, str, str]]:
    """Return ``(path, line, function, name)`` per story-text reference.

    A reference is a declared story-text name used in the arguments of an
    INFO-or-higher logger call, outside ``len(...)`` and outside the test of a
    conditional expression.
    """

    scanner = _LogCallScanner(path)
    scanner.visit(ast.parse(source, filename=path))
    return scanner.violations


def _all_violations() -> list[Violation]:
    violations: list[Violation] = []
    for path in SCANNED:
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        violations.extend(story_text_violations(source, path))
    return violations


def _format(violations: list[Violation]) -> str:
    return "\n".join(
        f"{path}:{line} {name} [{function}]"
        for path, line, function, name in violations
    )


def test_no_story_text_reaches_info_or_above() -> None:
    """No INFO-or-higher logger call references story or player text."""

    violations = [
        violation
        for violation in _all_violations()
        if (violation[0], violation[2], violation[3]) not in METADATA_ONLY_USES
    ]
    assert violations == [], (
        "Story or player text reaches INFO or above; log a metadata line at "
        "the level and the text on a paired DEBUG line (#842):\n" + _format(violations)
    )


def test_metadata_allowlist_entries_are_live() -> None:
    """Every allowlisted metadata-only use still matches a logger call."""

    seen = {(path, function, name) for path, _, function, name in _all_violations()}
    stale = sorted(set(METADATA_ONLY_USES) - seen)
    assert stale == [], f"Stale METADATA_ONLY_USES entries: {stale}"


def test_scanner_flags_each_level_and_exempts_metadata_forms() -> None:
    """Each INFO-or-higher form is flagged; DEBUG, len() and flags are not."""

    for flagged in (
        'logger.info("%s", user_input)\n',
        'self.logger.warning(f"{seed.title}")\n',
        'qa_logger.error("%s", query)\n',
        'logger.log(logging.INFO, "%s", query)\n',
    ):
        assert story_text_violations(flagged, "probe.py") != [], flagged
    for exempt in (
        'logger.debug("%s", user_input)\n',
        'logger.info("%d", len(user_input))\n',
        'logger.info("x%s", " [n]" if note else "")\n',
    ):
        assert story_text_violations(exempt, "probe.py") == [], exempt


SENTINEL = "qa842-sentinel Ask Kessa Brin what she remembers"


@pytest.mark.requires_postgres
def test_alias_search_logs_query_text_only_at_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The real alias search keeps its query text out of INFO (#842)."""

    expected_info = f"Query of {len(SENTINEL)} chars contains character references: []"
    with disposable_slot_database("qa640_842s5_redaction") as dbname:
        engine = create_engine(sqlalchemy_url(dbname))
        try:
            for level, present in ((logging.INFO, False), (logging.DEBUG, True)):
                caplog.clear()
                with caplog.at_level(level, logger="nexus.memnon.alias_search"):
                    with engine.connect() as conn:
                        # No chunk_embeddings_0007d table exists, so the real
                        # path logs the query and returns before any search.
                        assert (
                            hybrid_alias_search(
                                conn,
                                SENTINEL,
                                [0.0] * 7,
                                "qa640-842",
                                7,
                                alias_lookup={},
                            )
                            == []
                        )
                assert (SENTINEL in caplog.text) is present, (level, caplog.text)
                assert any(
                    record.levelno == logging.INFO
                    and record.getMessage() == expected_info
                    for record in caplog.records
                ), (level, caplog.text)
        finally:
            engine.dispose()
