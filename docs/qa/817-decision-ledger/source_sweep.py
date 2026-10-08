"""Source sweep for the 817-S3 decision records.

Usage: python source_sweep.py <worktree>

Lists, per record under docs/decisions/, every file the record's body names
that its ``sources`` list omits. A name counts when it is a tracked repository
path, a bare file name with tracked matches (every match is listed), or a path
with a file extension that is not tracked (printed as ``UNTRACKED:<name>``). A
``:<line>`` suffix is dropped. The sweep finds candidates only: a candidate
joins a record's sources when the record's text cites it as the basis of its
ruling or refutation. Commands, prompts and other artifacts named without a
file path are left to a reading of the records (verification.md lists them).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

EXTENSIONS = "py|md|toml|tsx|ts|sql|json|css|yml|yaml"
TOKEN = re.compile(rf"`[^`]+`|[A-Za-z0-9_./~-]+\.(?:{EXTENSIONS})\b")
FILE_NAME = re.compile(rf"\.(?:{EXTENSIONS})$")
LINE_SUFFIX = re.compile(r":[0-9].*$")


def tracked_files(root: Path) -> list[str]:
    """Every path git tracks in the worktree."""
    output = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return output.split()


def candidates(
    token: str, tracked: set[str], by_name: dict[str, list[str]]
) -> list[str]:
    """The repository files a token names, or an UNTRACKED marker."""
    name = LINE_SUFFIX.sub("", token.strip("`")).rstrip(".,;)")
    if name in tracked:
        return [name]
    if "/" not in name and name in by_name:
        return by_name[name]
    if FILE_NAME.search(name):
        return [f"UNTRACKED:{name}"]
    return []


def sweep(root: Path) -> dict[str, dict[str, list[int]]]:
    """Map each record to its omitted candidates and their body line numbers."""
    tracked = tracked_files(root)
    by_name: dict[str, list[str]] = {}
    for path in tracked:
        by_name.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    found: dict[str, dict[str, list[int]]] = {}
    for record in sorted((root / "docs/decisions").glob("[0-9]*.md")):
        _, front, body = record.read_text(encoding="utf-8").split("---\n", 2)
        sources = yaml.safe_load(front)["sources"]
        omitted: dict[str, list[int]] = {}
        for number, line in enumerate(body.splitlines(), 1):
            for match in TOKEN.finditer(line):
                for name in candidates(match.group(0), set(tracked), by_name):
                    if name not in sources:
                        omitted.setdefault(name, []).append(number)
        if omitted:
            found[record.name] = omitted
    return found


def main() -> None:
    """Print each record's omitted candidates, then the tracked-file count."""
    if len(sys.argv) != 2:
        sys.exit("usage: python source_sweep.py <worktree>")
    found = sweep(Path(sys.argv[1]))
    tracked = 0
    for record, omitted in found.items():
        print(record)
        for name, lines in omitted.items():
            tracked += not name.startswith("UNTRACKED:")
            print(f"    {name} (body lines {', '.join(map(str, lines))})")
    print(f"tracked files cited but not in sources: {tracked}")


if __name__ == "__main__":
    main()
