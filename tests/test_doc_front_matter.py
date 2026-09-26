"""Enforce the document front matter contract in ``docs/decisions/README.md``.

Classified documents (Markdown at the repository root or under ``docs/``) open
with a YAML block declaring ``status``, ``verified_commit``, and, for canonical
documents, the ``sources`` they describe. README.md must not reference a
superseded document and must label every historical one it references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
import posixpath
import re
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from scripts.check_reachability import repository_files

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ("canonical", "historical", "superseded")
KNOWN_KEYS = frozenset(
    {"status", "sources", "verified_commit", "supersedes", "superseded_by"}
)
COMMIT_SHA = re.compile(r"[0-9a-f]{7,40}")
# A Markdown path token, optionally ./ or ../ relative; the lookbehind keeps
# URLs and mid-token matches out.
MARKDOWN_REFERENCE = re.compile(r"(?<![\w./*:-])(?:\.\.?/)*\w[\w./*-]*\.md\b")

# The classification landed by #817. Changing one is a deliberate edit here.
CLASSIFIED = {
    "AGENTS.md": "canonical",
    "docs/decisions/README.md": "canonical",
    "docs/turn_flow_sequence.md": "canonical",
    "docs/blueprint_gaia.md": "historical",
    "docs/blueprint_nemesis.md": "historical",
    "docs/blueprint_psyche.md": "historical",
    "docs/hybrid_search.md": "historical",
    "docs/orrery_slot2_backfill_plan.md": "historical",
    "docs/vector_embeddings.md": "historical",
}


class FrontMatterError(ValueError):
    """A document's front matter block cannot be read as a YAML mapping."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    """Build a mapping, failing on a key that YAML would silently overwrite."""
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


@dataclass
class Classification:
    """Every classified document's front matter and every contract violation."""

    documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def repository_paths(root: Path) -> frozenset[str]:
    """Return git's view of ``root`` as POSIX paths, or every file outside git."""
    tracked = repository_files(root)
    if tracked is not None:
        return frozenset(path for path in tracked if (root / path).is_file())
    return frozenset(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )


def classified_scope(paths: frozenset[str]) -> list[str]:
    """Markdown files at the repository root or anywhere under ``docs/``."""
    return sorted(
        path
        for path in paths
        if path.endswith(".md") and ("/" not in path or path.startswith("docs/"))
    )


def read_front_matter(text: str) -> dict[str, Any] | None:
    """Parse the leading ``---`` YAML block, or return None when there is none."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            data = yaml.load("\n".join(lines[1:index]), Loader=_UniqueKeyLoader)
            if not isinstance(data, dict) or not data:
                raise FrontMatterError("front matter must be a non-empty mapping")
            return data
    raise FrontMatterError("front matter opened on line 1 is never closed")


def _path_error(value: Any, paths: frozenset[str], directories: set[str]) -> str:
    """Describe why ``value`` is not an existing repository path, or return ''."""
    if not isinstance(value, str) or not value:
        return f"{value!r} is not a non-empty string"
    if "\\" in value or value.startswith("/"):
        return f"{value!r} is not a repository-relative POSIX path"
    parts = PurePosixPath(value.rstrip("/")).parts
    if any(part in {".", ".."} for part in parts) or "//" in value:
        return f"{value!r} is not a normalized repository-relative path"
    if value.endswith("/"):
        if value.rstrip("/") not in directories:
            return f"directory {value!r} does not exist"
    elif value not in paths:
        suffix = " (directories need a trailing slash)" if value in directories else ""
        return f"file {value!r} does not exist{suffix}"
    return ""


def _string_list(value: Any) -> bool:
    """True for a list whose entries are all strings."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_document(
    path: str,
    front_matter: dict[str, Any],
    documents: dict[str, dict[str, Any]],
    paths: frozenset[str],
    directories: set[str],
) -> list[str]:
    """Check one document's front matter against the documented contract."""
    errors: list[str] = []
    unknown = sorted(str(key) for key in set(front_matter) - KNOWN_KEYS)
    if unknown:
        errors.append(f"{path}: unknown front matter keys {unknown}")

    status = front_matter.get("status")
    if status not in STATUSES:
        errors.append(f"{path}: status must be one of {list(STATUSES)}, not {status!r}")

    commit = front_matter.get("verified_commit")
    if not isinstance(commit, str):
        errors.append(
            f"{path}: verified_commit must be a quoted string of 7-40 lowercase "
            f"hex characters, not {commit!r}"
        )
    elif not COMMIT_SHA.fullmatch(commit):
        errors.append(
            f"{path}: verified_commit {commit!r} is not 7-40 lowercase hex characters"
        )

    if "sources" in front_matter or status == "canonical":
        sources = front_matter.get("sources")
        if not _string_list(sources) or not sources:
            errors.append(f"{path}: sources must be a non-empty list of paths")
        else:
            if len(set(sources)) != len(sources):
                errors.append(f"{path}: sources lists a path more than once")
            for source in sources:
                problem = _path_error(source, paths, directories)
                if problem:
                    errors.append(f"{path}: source {problem}")

    successor = front_matter.get("superseded_by")
    if status == "superseded" and successor is None:
        errors.append(f"{path}: a superseded document must name superseded_by")
    if successor is not None:
        if status != "superseded":
            errors.append(f"{path}: superseded_by requires status: superseded")
        target = documents.get(successor) if isinstance(successor, str) else None
        # A successor may itself be superseded later: each link keeps the
        # replacement history, and the chain check below finds the end.
        if target is None:
            errors.append(
                f"{path}: superseded_by {successor!r} is not a classified document"
            )
        elif path not in (target.get("supersedes") or []):
            errors.append(
                f"{path}: {successor} does not list this document under supersedes"
            )

    if "supersedes" in front_matter:
        replaced = front_matter["supersedes"]
        if not _string_list(replaced) or not replaced:
            errors.append(f"{path}: supersedes must be a non-empty list of paths")
        else:
            for old in replaced:
                record = documents.get(old)
                if record is None:
                    errors.append(
                        f"{path}: supersedes {old!r}, which is not a classified "
                        "document"
                    )
                elif (
                    record.get("status") != "superseded"
                    or record.get("superseded_by") != path
                ):
                    errors.append(
                        f"{path}: {old} must be superseded with superseded_by "
                        f"{path!r}"
                    )
    return errors


def _chain_errors(path: str, documents: dict[str, dict[str, Any]]) -> list[str]:
    """Follow ``superseded_by`` links and fail when they loop without an end."""
    seen = [path]
    current = documents[path]
    while current.get("status") == "superseded":
        successor = current.get("superseded_by")
        if not isinstance(successor, str) or successor not in documents:
            return []  # The missing link is reported by _validate_document.
        if successor in seen:
            chain = " -> ".join([*seen, successor])
            return [f"{path}: supersession chain loops ({chain})"]
        seen.append(successor)
        current = documents[successor]
    return []


def classify(root: Path, paths: frozenset[str]) -> Classification:
    """Read every classified document under ``root`` and validate the contract."""
    result = Classification()
    for path in classified_scope(paths):
        try:
            front_matter = read_front_matter((root / path).read_text(encoding="utf-8"))
        except (FrontMatterError, yaml.YAMLError) as exc:
            result.errors.append(f"{path}: {exc}")
            continue
        if front_matter is not None:
            result.documents[path] = front_matter
    directories = {
        str(parent)
        for path in paths
        for parent in PurePosixPath(path).parents
        if str(parent) != "."
    }
    for path, front_matter in result.documents.items():
        result.errors.extend(
            _validate_document(path, front_matter, result.documents, paths, directories)
        )
        result.errors.extend(_chain_errors(path, result.documents))
    return result


def readme_reference_errors(
    root: Path, paths: frozenset[str], documents: dict[str, dict[str, Any]]
) -> list[str]:
    """Check every Markdown path README.md references against its status."""
    errors: list[str] = []
    text = (root / "README.md").read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        for match in MARKDOWN_REFERENCE.finditer(line):
            reference = match.group(0)
            normalized = posixpath.normpath(reference)
            if normalized == ".." or normalized.startswith("../"):
                errors.append(
                    f"README.md:{number}: {reference} points outside the repository"
                )
                continue
            if "*" in normalized:
                targets = sorted(
                    path for path in paths if fnmatchcase(path, normalized)
                )
            else:
                targets = [normalized] if normalized in paths else []
            if not targets:
                errors.append(f"README.md:{number}: {reference} does not exist")
            for target in targets:
                status = documents.get(target, {}).get("status")
                if status == "superseded":
                    errors.append(
                        f"README.md:{number}: {target} is superseded; reference "
                        "its successor instead"
                    )
                elif status == "historical" and "historical" not in line.lower():
                    errors.append(
                        f"README.md:{number}: {target} is historical and must be "
                        "labeled historical on the line that references it"
                    )
    return errors


@pytest.fixture(scope="module")
def repository() -> tuple[frozenset[str], Classification]:
    """The checkout's file view and its classified documents."""
    paths = repository_paths(ROOT)
    return paths, classify(ROOT, paths)


def test_classified_documents_follow_the_contract(
    repository: tuple[frozenset[str], Classification],
) -> None:
    """Every document with front matter satisfies the documented contract."""
    _, classification = repository
    assert classification.errors == []


def test_readme_references_are_real_and_current(
    repository: tuple[frozenset[str], Classification],
) -> None:
    """README.md names only existing documents and labels historical ones."""
    paths, classification = repository
    assert readme_reference_errors(ROOT, paths, classification.documents) == []


def test_issue_817_classifications_hold(
    repository: tuple[frozenset[str], Classification],
) -> None:
    """The documents #817 classified keep their declared status."""
    _, classification = repository
    declared = {
        path: classification.documents.get(path, {}).get("status")
        for path in CLASSIFIED
    }
    assert declared == CLASSIFIED


def _write(root: Path, path: str, text: str) -> None:
    """Create one file of a synthetic repository tree."""
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _document(front_matter: str, title: str = "# Title\n") -> str:
    """Render a Markdown document with the given front matter body."""
    return f"---\n{front_matter}---\n\n{title}"


VALID = 'status: canonical\nsources:\n  - src/app.py\nverified_commit: "abc1234"\n'


@pytest.mark.parametrize(
    ("front_matter", "message"),
    [
        (VALID + "owner: me\n", "unknown front matter keys ['owner']"),
        (VALID.replace("canonical", "current"), "status must be one of"),
        (VALID.replace('"abc1234"', "1234567"), "must be a quoted string"),
        (VALID.replace('"abc1234"', '"ABC1234"'), "is not 7-40 lowercase hex"),
        (VALID.replace('"abc1234"', '"abc12"'), "is not 7-40 lowercase hex"),
        ('status: canonical\nverified_commit: "abc1234"\n', "non-empty list"),
        (VALID.replace("src/app.py", "src/missing.py"), "does not exist"),
        (VALID.replace("src/app.py", "/src/app.py"), "repository-relative POSIX"),
        (VALID.replace("src/app.py", "src/../src/app.py"), "normalized"),
        (VALID.replace("src/app.py", "src"), "need a trailing slash"),
        (VALID.replace("src/app.py", "lib/"), "directory 'lib/' does not exist"),
        (
            VALID.replace("  - src/app.py\n", "  - src/app.py\n" * 2),
            "more than once",
        ),
        (VALID + "status: historical\n", "duplicate key 'status'"),
        (VALID.replace("canonical", "superseded"), "must name superseded_by"),
        (VALID + "superseded_by: docs/b.md\n", "requires status: superseded"),
        (VALID + "supersedes:\n  - docs/gone.md\n", "not a classified document"),
    ],
)
def test_validator_rejects_contract_violations(
    tmp_path: Path, front_matter: str, message: str
) -> None:
    """Each broken front matter field fails with a message naming the field."""
    _write(tmp_path, "src/app.py", "")
    _write(tmp_path, "docs/a.md", _document(front_matter))
    paths = repository_paths(tmp_path)
    errors = classify(tmp_path, paths).errors
    assert any(message in error for error in errors), errors
    assert all(error.startswith("docs/a.md: ") for error in errors), errors


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("---\nstatus: canonical\n# Title\n", "never closed"),
        ("---\n- canonical\n---\n# Title\n", "non-empty mapping"),
        ("---\n---\n# Title\n", "non-empty mapping"),
        ("---\nstatus: [\n---\n# Title\n", "flow node"),
    ],
)
def test_unreadable_front_matter_fails_loudly(
    tmp_path: Path, text: str, message: str
) -> None:
    """A malformed block is an error, never an unclassified document."""
    _write(tmp_path, "docs/a.md", text)
    classification = classify(tmp_path, repository_paths(tmp_path))
    assert classification.documents == {}
    assert len(classification.errors) == 1
    assert classification.errors[0].startswith("docs/a.md: ")
    assert message in classification.errors[0]


def test_supersession_must_agree_in_both_directions(tmp_path: Path) -> None:
    """A replacement and its superseded document must name each other."""
    _write(tmp_path, "src/app.py", "")
    _write(
        tmp_path,
        "docs/new.md",
        _document(VALID + "supersedes:\n  - docs/old.md\n"),
    )
    _write(
        tmp_path,
        "docs/old.md",
        _document(
            'status: superseded\nverified_commit: "abc1234"\n'
            "superseded_by: docs/new.md\n"
        ),
    )
    paths = repository_paths(tmp_path)
    assert classify(tmp_path, paths).errors == []

    _write(tmp_path, "docs/new.md", _document(VALID))
    errors = classify(tmp_path, paths).errors
    assert errors == [
        "docs/old.md: docs/new.md does not list this document under supersedes"
    ]


def _superseded(successor: str, supersedes: tuple[str, ...] = ()) -> str:
    """Render a superseded document pointing at ``successor``."""
    replaced = "".join(f"  - {old}\n" for old in supersedes)
    return _document(
        'status: superseded\nverified_commit: "abc1234"\n'
        f"superseded_by: {successor}\n"
        + (f"supersedes:\n{replaced}" if replaced else "")
    )


def test_supersession_chains_keep_their_history(tmp_path: Path) -> None:
    """A -> B -> C stays valid without rewriting A to point at C."""
    _write(tmp_path, "src/app.py", "")
    _write(tmp_path, "docs/a.md", _superseded("docs/b.md"))
    _write(tmp_path, "docs/b.md", _superseded("docs/c.md", ("docs/a.md",)))
    _write(
        tmp_path,
        "docs/c.md",
        _document(VALID + "supersedes:\n  - docs/b.md\n"),
    )
    paths = repository_paths(tmp_path)
    assert classify(tmp_path, paths).errors == []

    _write(tmp_path, "docs/b.md", _superseded("docs/c.md"))
    assert classify(tmp_path, paths).errors == [
        "docs/a.md: docs/b.md does not list this document under supersedes"
    ]


def test_supersession_chain_must_end_at_a_current_document(tmp_path: Path) -> None:
    """Superseded documents that only replace each other leave no successor."""
    _write(tmp_path, "docs/a.md", _superseded("docs/b.md", ("docs/b.md",)))
    _write(tmp_path, "docs/b.md", _superseded("docs/a.md", ("docs/a.md",)))
    assert classify(tmp_path, repository_paths(tmp_path)).errors == [
        "docs/a.md: supersession chain loops (docs/a.md -> docs/b.md -> docs/a.md)",
        "docs/b.md: supersession chain loops (docs/b.md -> docs/a.md -> docs/b.md)",
    ]


def test_scope_is_root_and_docs_markdown(tmp_path: Path) -> None:
    """Front matter elsewhere (prompts, skills) follows other contracts."""
    broken = _document("status: draft\n")
    _write(tmp_path, "prompts/wizard.md", broken)
    _write(tmp_path, "nexus/agents/README.md", broken)
    _write(tmp_path, "NOTES.md", broken)
    _write(tmp_path, "docs/qa/run/notes.md", broken)
    errors = classify(tmp_path, repository_paths(tmp_path)).errors
    assert sorted({error.split(":")[0] for error in errors}) == [
        "NOTES.md",
        "docs/qa/run/notes.md",
    ]


def test_readme_rules_reject_missing_superseded_and_unlabeled_historical(
    tmp_path: Path,
) -> None:
    """README.md references resolve, avoid superseded docs, and label history."""
    _write(tmp_path, "src/app.py", "")
    _write(tmp_path, "docs/current.md", _document(VALID))
    _write(
        tmp_path,
        "docs/retired_a.md",
        _document('status: historical\nverified_commit: "abc1234"\n'),
    )
    _write(
        tmp_path,
        "docs/retired_b.md",
        _document('status: historical\nverified_commit: "abc1234"\n'),
    )
    _write(
        tmp_path,
        "docs/old.md",
        _document(
            'status: superseded\nverified_commit: "abc1234"\n'
            "superseded_by: docs/current.md\n"
        ),
    )
    _write(
        tmp_path,
        "README.md",
        "\n".join(
            [
                "- `docs/current.md` — current",
                "- `docs/retired_*.md` — Historical designs",
                "- [old](docs/old.md)",
                "- `docs/retired_a.md` — the plan",
                "- `docs/missing.md`",
                "- https://example.com/docs/elsewhere.md",
                "",
            ]
        ),
    )
    paths = repository_paths(tmp_path)
    documents = classify(tmp_path, paths).documents
    assert readme_reference_errors(tmp_path, paths, documents) == [
        "README.md:3: docs/old.md is superseded; reference its successor instead",
        "README.md:4: docs/retired_a.md is historical and must be labeled "
        "historical on the line that references it",
        "README.md:5: docs/missing.md does not exist",
    ]


def test_readme_checks_dot_relative_links(tmp_path: Path) -> None:
    """./-relative links resolve from the root; ../ links leave the repository."""
    _write(tmp_path, "src/app.py", "")
    _write(tmp_path, "docs/current.md", _document(VALID))
    _write(
        tmp_path,
        "docs/retired.md",
        _document('status: historical\nverified_commit: "abc1234"\n'),
    )
    _write(
        tmp_path,
        "README.md",
        "\n".join(
            [
                "- [guide](./docs/current.md)",
                "- [plan](./docs/retired.md) — historical plan",
                "- [guide](./docs/missing.md)",
                "- [plan](./docs/retired.md)",
                "- [outside](../elsewhere/notes.md)",
                "",
            ]
        ),
    )
    paths = repository_paths(tmp_path)
    documents = classify(tmp_path, paths).documents
    assert readme_reference_errors(tmp_path, paths, documents) == [
        "README.md:3: ./docs/missing.md does not exist",
        "README.md:4: docs/retired.md is historical and must be labeled "
        "historical on the line that references it",
        "README.md:5: ../elsewhere/notes.md points outside the repository",
    ]
