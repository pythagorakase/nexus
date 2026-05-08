#!/usr/bin/env python3
"""Detect literal model IDs that have drifted away from the registry.

Background
----------
nexus.toml is the single source of truth for which API models the project uses
(see [global.model.api_models]). Consumer sections reference roles via
"@provider.role" syntax, which is resolved at config-load time. Outside the
registry, literal model IDs ("gpt-5.5", "claude-sonnet-4-6", ...) should not
appear in source code — every reference should either flow through the registry
or be marked as an *intentional* pin.

Intentional pins are allowed via two mechanisms:

1. The file is in an explicit allow-list (e.g., test parametrizations live in
   tests/, alias maps for external services live in scripts/api_openrouter.py).
2. The line carries a "# pin: <reason>" comment.

What this script does
---------------------
Walks the repo, scans .py / .toml / .md files (excluding skip-listed dirs and
files), and reports any line that contains a literal model ID without a pin.
Exits non-zero if any drift is found, so it can be wired into CI / pre-commit.

Usage
-----
    python scripts/check_model_drift.py            # report and exit 1 on drift
    python scripts/check_model_drift.py --quiet    # exit code only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

# Patterns that look like *currently-managed* API-model IDs. The point is to
# guard against drift in the families this project actively uses today (GPT-5
# and Claude 4). Older model strings (gpt-3.5, gpt-4.1, etc.) appear in legacy
# utility scripts and aren't part of this issue's acceptance criterion.
MODEL_ID_PATTERN = re.compile(
    r"\b("
    r"gpt-5(?:\.\d+)?"                        # gpt-5, gpt-5.1, gpt-5.5, ...
    r"|claude-(?:sonnet|opus|haiku)-\d+-\d+"  # claude-sonnet-4-6, claude-opus-4-7, ...
    r")\b"
)

# Comment marker that exempts a single line from drift checking.
# Use sparingly — prefer routing through the registry where possible.
PIN_MARKER = re.compile(r"#\s*pin\s*:")

# Directories never scanned.
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "models",
    "dist",
    "build",
    "__pycache__",
    "temp",
    "tests",       # parametrized test pins are intentional per issue #181
    "docs",        # documentation often references frozen examples
    "archive",     # archived legacy code, frozen in time
    "llama.cpp",   # vendored third-party
    ".claude",     # Claude Code skills/docs (CC-internal)
}

# Specific files always skipped — each has a documented reason for housing
# literal model strings unrelated to runtime defaults.
SKIP_FILES = {
    # The registry itself — this is *the* source of truth.
    "nexus.toml",
    # Legacy enum mirroring database ENUM types; not a runtime default.
    "nexus/agents/logon/apex_enums.py",
    # Tiktoken alias for token counting (tiktoken doesn't recognize newer IDs).
    "nexus/agents/lore/utils/chunk_operations.py",
    # External-service routing tables (OpenRouter / tiktoken).
    "scripts/api_openrouter.py",
    "scripts/token_counter.py",
    # The drift-checker itself contains pattern strings.
    "scripts/check_model_drift.py",
    # Legacy IR eval V1 entrypoint and helper (V2 lives under ir_eval/engine/).
    "ir_eval/ir_eval.py",
    "ir_eval/scripts/auto_judge.py",
}

# File extensions checked. TOML is included so consumer sections that haven't
# yet migrated to "@provider.role" surface as drift.
SCAN_EXTENSIONS = {".py", ".toml", ".md"}


def find_violations(repo_root: Path) -> List[Tuple[Path, int, str]]:
    """Return (path, line_number, line_text) for every drift violation.

    Each tuple represents a single literal model ID that's neither in the
    registry, nor in a skip-listed file, nor on a "# pin:"-annotated line.
    """
    violations: List[Tuple[Path, int, str]] = []

    for path in _iter_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        if rel in SKIP_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Binary or unreadable files — silently skip.
            continue

        for line_num, line in enumerate(text.splitlines(), start=1):
            if not MODEL_ID_PATTERN.search(line):
                continue
            if PIN_MARKER.search(line):
                continue
            violations.append((path, line_num, line.rstrip()))

    return violations


def _iter_files(repo_root: Path) -> Iterable[Path]:
    """Yield every scannable file beneath repo_root."""
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        # Skip anything under a skip-listed directory.
        if any(part in SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=None,
        help="Repo root to scan (defaults to the directory containing this script).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-line output; just exit 0/1 based on violations.",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    violations = find_violations(repo_root)

    if not violations:
        if not args.quiet:
            print("OK: no model-ID drift detected.")
        return 0

    if not args.quiet:
        print(f"Found {len(violations)} drift violation(s):", file=sys.stderr)
        print(file=sys.stderr)
        for path, line_num, line in violations:
            rel = path.relative_to(repo_root).as_posix()
            print(f"  {rel}:{line_num}: {line.strip()}", file=sys.stderr)
        print(file=sys.stderr)
        print(
            "Each line above mentions a literal model ID. Either route it through "
            "the [global.model.api_models] registry (preferably via a "
            '"@provider.role" reference resolved at config load) or, if the '
            'literal is intentional (e.g., a regression-test pin), append a '
            '"# pin: <reason>" comment on that line.',
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
