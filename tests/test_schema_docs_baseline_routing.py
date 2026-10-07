"""Offline check that every schema-documentation baseline entry is routed.

Decision 819-Q1 routes each entry of ``config/schema_docs_baseline.json`` into
#813's manifest, ``docs/dead_retrieval_subtraction.md``. Each baseline reason
names one manifest section, and that section lists the entry's object in
backticks. These tests read both files from the repository root; they need no
database and no network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "config" / "schema_docs_baseline.json"
MANIFEST = ROOT / "docs" / "dead_retrieval_subtraction.md"

HEADING = re.compile(r"^(#{2,6}) (.+)$")
POINTER = re.compile(r'docs/dead_retrieval_subtraction\.md, section "([^"]+)"')


def _baseline() -> dict[str, str]:
    """Return the baseline as an ordered mapping of key to reason."""
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "schema docs baseline must be a JSON object"
    return data


def _manifest_sections() -> list[tuple[str, str]]:
    """Return ``(heading text, body)`` for every heading of level two to six.

    A body is the lines after its heading up to the next heading of the same
    or a higher level (the same number of ``#`` or fewer).
    """
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2)))
    sections: list[tuple[str, str]] = []
    for position, (index, level, text) in enumerate(headings):
        end = len(lines)
        for later_index, later_level, _ in headings[position + 1 :]:
            if later_level <= level:
                end = later_index
                break
        sections.append((text, "\n".join(lines[index + 1 : end])))
    return sections


def _section_name(key: str, reason: str) -> str:
    """Return the manifest section the reason names, failing if none."""
    match = POINTER.search(reason)
    assert match, f"{key}: reason names no section of {MANIFEST.name}: {reason!r}"
    return match.group(1)


def test_every_baseline_reason_names_a_manifest_section() -> None:
    """Each reason points at exactly one existing manifest heading."""
    headings = [text for text, _ in _manifest_sections()]
    for key, reason in _baseline().items():
        name = _section_name(key, reason)
        count = headings.count(name)
        assert count == 1, (
            f"{key}: section {name!r} matches {count} headings in "
            f"{MANIFEST.name}; expected exactly one"
        )


def test_every_baseline_object_is_listed_in_its_section() -> None:
    """Each key's object appears in backticks in the section its reason names."""
    bodies: dict[str, list[str]] = {}
    for text, body in _manifest_sections():
        bodies.setdefault(text, []).append(body)
    for key, reason in _baseline().items():
        name = _section_name(key, reason)
        matches = bodies.get(name, [])
        assert len(matches) == 1, (
            f"{key}: section {name!r} matches {len(matches)} headings in "
            f"{MANIFEST.name}; expected exactly one"
        )
        identifier = key.split(":", 1)[1]
        assert f"`{identifier}`" in matches[0], (
            f"{key}: `{identifier}` is not listed in section {name!r} of "
            f"{MANIFEST.name}"
        )
