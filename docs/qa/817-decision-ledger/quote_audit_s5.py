"""Quote audit for the 817-S5 decision records 0056-0083.

Usage: python quote_audit_s5.py <worktree>

Fetches every cited comment fresh from GitHub with ``gh api``, renders the
quoted block that work order 817-S4S5 (Required Changes 7) defines for each
record, and checks it byte for byte against the record under docs/decisions/.
It also checks the ``Source:`` URL, the Links line, and that the two quoted
Rejected Alternatives sentences occur in their fetched comments. It imports
nothing from the repository and uses the standard library only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

API = "repos/pythagorakase/nexus"
URL = "https://github.com/pythagorakase/nexus/issues/"
QUOTE_LINE = re.compile(r"^>( |$)")
DEFAULT_REJECTED = "- None recorded in the public relay."
REOPENING = "- A later owner ruling on the linked issue."

# number -> (issue, comment id, relay kind); transcribed from the order's table.
# "L41", "L42" and "L43" are loom relays of that Arachne sequence; "C" is a
# coordinator review of 2026-10-26.
TABLE: dict[str, tuple[int, int, str]] = {
    "0056": (784, 6043523766, "L41"),
    "0057": (788, 6043524251, "L41"),
    "0058": (840, 6043527972, "L41"),
    "0059": (823, 6156195936, "L42"),
    "0060": (820, 6156196220, "L42"),
    "0061": (824, 6421993908, "L43"),
    "0062": (816, 6421994645, "L43"),
    "0063": (815, 6421995432, "L43"),
    "0064": (842, 6421996124, "L43"),
    "0065": (813, 6423067570, "C"),
    "0066": (1102, 6423072099, "C"),
    "0067": (821, 6423073509, "C"),
    "0068": (1106, 6423079194, "C"),
    "0069": (842, 6423079832, "C"),
    "0070": (845, 6423081217, "C"),
    "0071": (812, 6423082662, "C"),
    "0072": (817, 6423083545, "C"),
    "0073": (815, 6423086585, "C"),
    "0074": (1126, 6423092502, "C"),
    "0075": (1129, 6423094037, "C"),
    "0076": (816, 6423096474, "C"),
    "0077": (1069, 6423099961, "C"),
    "0078": (1091, 6423107274, "C"),
    "0079": (824, 6423109883, "C"),
    "0080": (848, 6423111652, "C"),
    "0081": (802, 6423123761, "C"),
    "0082": (810, 6423201171, "C"),
    "0083": (811, 6423208720, "C"),
}
# The two quoted Rejected Alternatives sentences (Required Changes 7).
REJECTED: dict[str, str] = {
    "0056": (
        "The option not chosen added a bounded per-character texture line to "
        "the prompts."
    ),
    "0057": (
        "The two options not chosen rehomed or wrapped the shipped source under "
        "the new gates."
    ),
}
EXTRA_LINKS: dict[str, str] = {"0078": "#1091, #1119"}


def fetch_comment(cid: int) -> dict[str, str]:
    """Fetch one issue comment by id, fresh, as the API returns it."""
    out = subprocess.run(
        ["gh", "api", f"{API}/issues/comments/{cid}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    data: dict[str, str] = json.loads(out)
    return data


def first_run(lines: list[str], start: int, keep: re.Pattern[str]) -> list[str]:
    """The maximal run of lines matching ``keep`` from ``start``."""
    run: list[str] = []
    index = start
    while index < len(lines) and keep.match(lines[index]):
        run.append(lines[index])
        index += 1
    return run


def source_lines(number: str, kind: str, body: str) -> list[str]:
    """The comment lines the record quotes, before the quoting rule."""
    lines = body.splitlines()
    if kind == "L41":
        marker = next(i for i, line in enumerate(lines) if "verbatim" in line.lower())
        index = marker + 1
        while lines[index] == "":
            index += 1
        return first_run(lines, index, QUOTE_LINE)
    if kind in ("L42", "L43"):
        index = next(i for i, line in enumerate(lines) if line.startswith("- "))
        return first_run(lines, index, re.compile(r"^- "))
    if number == "0082":
        found = [line for line in lines if line.startswith("- **810-S4a-ext.**")]
        assert len(found) == 1, found
        return found
    start = lines.index("### Decisions")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("### "))
    return lines[start + 1 : end]


def quoted(lines: list[str]) -> list[str]:
    """Drop outer blank lines, then apply the quoting rule."""
    while lines and lines[0] == "":
        lines = lines[1:]
    while lines and lines[-1] == "":
        lines = lines[:-1]
    return [
        line if line.startswith(">") else (">" if line == "" else f"> {line}")
        for line in lines
    ]


def record_block(lines: list[str]) -> tuple[str, list[str]]:
    """The record's ``Source:`` line and the quoted block that follows it."""
    sources = [i for i, line in enumerate(lines) if line.startswith("Source: ")]
    assert len(sources) == 1, f"{len(sources)} Source lines"
    index = sources[0]
    assert lines[index + 1] == "", "no blank line after the Source line"
    block = first_run(lines, index + 2, re.compile(r"^>"))
    after = index + 2 + len(block)
    assert after < len(lines) and lines[after] == "", "block not closed by a blank"
    stray = [
        n + 1
        for n, line in enumerate(lines)
        if line.startswith(">") and not index + 2 <= n < after
    ]
    assert not stray, f"quoted lines outside the block: {stray}"
    return lines[index], block


def section(lines: list[str], heading: str) -> list[str]:
    """The non-blank lines of one ``##`` section."""
    start = lines.index(heading) + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return [line for line in lines[start:end] if line]


def audit(root: Path, number: str) -> list[str]:
    """Every difference between one record and its fetched comment."""
    issue, cid, kind = TABLE[number]
    records = list((root / "docs/decisions").glob(f"{number}-*.md"))
    if len(records) != 1:
        return [f"{number}: {len(records)} record files"]
    lines = records[0].read_text(encoding="utf-8").splitlines()
    data = fetch_comment(cid)
    failures: list[str] = []
    url = f"{URL}{issue}#issuecomment-{cid}"
    if data["html_url"] != url:
        failures.append(f"{number}: comment {cid} is {data['html_url']}, not {url}")
    if kind == "C":
        links = f"{EXTRA_LINKS.get(number, f'#{issue}')}, coordinator review 2026-10-26"
    else:
        links = f"#{issue}, Loom sequence {kind[1:]}"
    if f"**Links:** {links}" not in lines:
        failures.append(f"{number}: Links line is not {links!r}")
    try:
        source, block = record_block(lines)
    except AssertionError as error:
        return [*failures, f"{number}: {error}"]
    if source != f"Source: {url}.":
        failures.append(f"{number}: {source!r} does not cite {url}")
    expected = quoted(source_lines(number, kind, data["body"]))
    if not expected:
        failures.append(f"{number}: the fetched comment yields no quoted lines")
    if "\n".join(block).encode() != "\n".join(expected).encode():
        failures.append(f"{number}: quoted block differs from comment {cid}")
    rejected = section(lines, "## Rejected Alternatives")
    if number in REJECTED:
        sentence = REJECTED[number]
        if rejected != [f'- "{sentence}" No reason recorded.']:
            failures.append(f"{number}: Rejected Alternatives is {rejected!r}")
        if sentence not in data["body"]:
            failures.append(f"{number}: the rejected sentence is not in {cid}")
    elif rejected != [DEFAULT_REJECTED]:
        failures.append(f"{number}: Rejected Alternatives is {rejected!r}")
    if section(lines, "## Reopening Criteria") != [REOPENING]:
        failures.append(f"{number}: Reopening Criteria differs")
    print(f"| {number} | {url} | {kind} | {len(block)} | {not failures} |")
    return failures


def main() -> None:
    """Audit records 0056-0083 and exit non-zero on any difference."""
    if len(sys.argv) != 2:
        sys.exit("usage: python quote_audit_s5.py <worktree>")
    root = Path(sys.argv[1])
    present = sorted(
        path.name[:4]
        for path in (root / "docs/decisions").glob("[0-9][0-9][0-9][0-9]-*.md")
        if path.name[:4] >= "0056"
    )
    print("| Record | Source | Relay | Quoted lines | Match |")
    print("|---|---|---|---|---|")
    failures = [] if present == sorted(TABLE) else [f"record set {present}"]
    for number in sorted(TABLE):
        failures += audit(root, number)
    if failures:
        print("FAILURES:")
        print("\n".join(failures))
        sys.exit(1)
    print(f"all {len(TABLE)} records match")


if __name__ == "__main__":
    main()
