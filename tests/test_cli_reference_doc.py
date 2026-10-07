"""The generated CLI reference stays in lockstep with the parser (#817)."""

from __future__ import annotations

import argparse
import re
import sys
import typing
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import pytest

from nexus import cli
from nexus.cli_contract import (
    COMMAND_TRANSPORTS,
    FLAG_TRANSPORTS,
    TRANSPORT_OPENS,
    Transport,
    iter_command_parsers,
    iter_command_paths,
)
from scripts.render_cli_reference import render_cli_reference

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "cli_reference.md"
REGENERATE = "python -m scripts.render_cli_reference --write"


def _committed() -> str:
    """The committed reference document."""
    assert DOC_PATH.exists(), f"{DOC_PATH} does not exist. Run: {REGENERATE}"
    return DOC_PATH.read_text()


def _section(text: str, heading: str) -> str:
    """The body of one ``###`` section of the committed document."""
    start = text.index(f"{heading}\n")
    end = text.find("\n### ", start + len(heading))
    return text[start : end if end != -1 else len(text)]


def _transport_rows(text: str) -> Dict[str, List[str]]:
    """The Transports table: each transport's Commands cell, split into entries."""
    start = text.index("## Transports\n")
    end = text.index("\n## ", start + 1)
    rows: Dict[str, List[str]] = {}
    for line in text[start:end].splitlines():
        match = re.fullmatch(r"\| `([a-z_]+)` \| [^|]+ \| (.*) \|", line)
        if match is None:
            continue
        cell = match.group(2)
        rows[match.group(1)] = re.findall(r"`([^`]+)`", cell)
    return rows


def test_cli_reference_is_current() -> None:
    """The committed file equals a fresh render of the real parser."""
    expected = render_cli_reference(cli.build_parser())
    if _committed() != expected:
        raise AssertionError(f"{DOC_PATH} is stale.\nRun: {REGENERATE}")


def test_every_parser_has_one_section() -> None:
    """Every group and leaf has exactly one heading, in walk order."""
    headings = re.findall(r"^### `nexus (.+)`$", _committed(), flags=re.MULTILINE)
    paths = [path for path, _parser, _help in iter_command_parsers(cli.build_parser())]
    assert headings == paths


def test_transports_table_matches_the_registry() -> None:
    """Each registry command and flag variant sits once in its transport's row."""
    rows = _transport_rows(_committed())
    assert list(rows) == list(TRANSPORT_OPENS)
    assert set(TRANSPORT_OPENS) == set(typing.get_args(Transport))

    entries = [entry for commands in rows.values() for entry in commands]
    for command, transport in COMMAND_TRANSPORTS.items():
        assert entries.count(command) == 1, command
        assert command in rows[transport], (command, transport)

    parsers = {
        path: child for path, child, _help in iter_command_parsers(cli.build_parser())
    }
    for command, variants in FLAG_TRANSPORTS.items():
        for dest, transport in variants:
            (flag,) = [
                option
                for action in parsers[command]._actions
                if action.dest == dest
                for option in action.option_strings
                if option.startswith("--")
            ]
            variant = f"{command} {flag}"
            assert variant in rows[transport], (variant, transport)
            assert entries.count(variant) == 1, variant


def _leaf_without_transport() -> Tuple[argparse.ArgumentParser, Dict[str, Transport]]:
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("orphan", help="Has no declared transport")
    return parser, {}


def _subparser_without_help() -> Tuple[argparse.ArgumentParser, Dict[str, Transport]]:
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("orphan")
    return parser, {"orphan": "http"}


def _star_nargs() -> Tuple[argparse.ArgumentParser, Dict[str, Transport]]:
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    leaf = subparsers.add_parser("orphan", help="Takes any number of ids")
    leaf.add_argument("--ids", nargs="*", help="Ids")
    return parser, {"orphan": "http"}


@pytest.mark.parametrize(
    "build",
    [_leaf_without_transport, _subparser_without_help, _star_nargs],
    ids=["leaf-without-transport", "subparser-without-help", "nargs-star"],
)
def test_renderer_refuses_unrenderable_parsers(
    build: Callable[[], Tuple[argparse.ArgumentParser, Dict[str, Transport]]],
) -> None:
    """The renderer raises, naming the command, instead of guessing."""
    parser, transports = build()
    with pytest.raises(ValueError, match="nexus orphan"):
        render_cli_reference(
            parser,
            command_transports=transports,
            flag_transports={},
            remote_profile_transports={},
        )


def test_zero_default_is_not_blank() -> None:
    """A default of 0 renders as `0`, not as the blank of False or None."""
    section = _section(_committed(), "### `nexus trait-audit`")
    rows = [
        line for line in section.splitlines() if line.startswith("| `--character-id` |")
    ]
    assert len(rows) == 1
    cells = [cell.strip() for cell in rows[0].strip("|").split("|")]
    assert cells[2] == "`0`"


def test_render_ignores_width_and_program_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The render reads no terminal width and no program name."""
    monkeypatch.setenv("COLUMNS", "40")
    monkeypatch.setattr(sys, "argv", ["x"])
    narrow = render_cli_reference(cli.build_parser())
    monkeypatch.setenv("COLUMNS", "300")
    monkeypatch.setattr(sys, "argv", ["nexus"])
    wide = render_cli_reference(cli.build_parser())
    assert narrow == wide


def test_iter_command_paths_are_the_leaves() -> None:
    """iter_command_paths yields exactly the leaves of iter_command_parsers."""
    parser = cli.build_parser()
    leaves = [
        path
        for path, child, _help in iter_command_parsers(parser)
        if not any(
            isinstance(action, argparse._SubParsersAction) for action in child._actions
        )
    ]
    assert list(iter_command_paths(parser)) == leaves
