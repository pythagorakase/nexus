"""The registry of generated documents (#817, Decision 817-Q8).

One list names every document a generator writes and the command that rewrites
it. The staleness tests read their paths and commands from it, and the
classification ratchet in ``tests/test_doc_front_matter.py`` exempts exactly
these paths and checks their generated header.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GeneratedDocument:
    """A generated document: its repository-relative POSIX path and generator."""

    path: str
    regenerate: str


CLI_REFERENCE = GeneratedDocument(
    "docs/cli_reference.md", "python -m scripts.render_cli_reference --write"
)
ORRERY_CATALOG = GeneratedDocument(
    "docs/orrery_packages.md", "python -m nexus.agents.orrery.catalog --write"
)
GENERATED_DOCUMENTS: tuple[GeneratedDocument, ...] = (CLI_REFERENCE, ORRERY_CATALOG)
