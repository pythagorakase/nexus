"""Enforce the document front matter contract in ``docs/decisions/README.md``.

Classified documents (Markdown at the repository root or under ``docs/``) open
with a YAML block declaring ``status``, ``verified_commit``, and, for canonical
documents, the ``sources`` they describe. README.md must not reference a
superseded document and must label every historical one it references. A
branch that changes a source declared by a canonical document must re-stamp
that document's ``verified_commit``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from scripts.check_reachability import repository_files

ROOT = Path(__file__).resolve().parents[1]
# Every worktree is cut from this branch; the freshness check diffs against it.
BASE_REF = "origin/main"
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


def _path_error(
    value: Any, paths: frozenset[str], directories: set[str], root: Path
) -> str:
    """Describe why ``value`` is not an existing repository path, or return ''."""
    if not isinstance(value, str) or not value:
        return f"{value!r} is not a non-empty string"
    if "\\" in value or value.startswith("/"):
        return f"{value!r} is not a repository-relative POSIX path"
    parts = PurePosixPath(value.rstrip("/")).parts
    if any(part in {".", ".."} for part in parts) or "//" in value:
        return f"{value!r} is not a normalized repository-relative path"
    # ``directories`` holds the parents of git-visible files; an existing
    # directory that holds only ignored files, or none, is on disk only.
    if value.endswith("/") or value in directories or (root / value).is_dir():
        return f"{value!r} names a directory; sources name files"
    if value not in paths:
        return f"file {value!r} does not exist"
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
    root: Path,
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
                problem = _path_error(source, paths, directories, root)
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
            _validate_document(
                path, front_matter, result.documents, paths, directories, root
            )
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


class FreshnessHistoryError(RuntimeError):
    """The history the freshness check compares against is missing."""


def _history_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``git -C root``, ignoring every inherited ``GIT_*`` variable."""
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    return subprocess.run(
        ["git", "-C", str(root), *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _history_output(root: Path, *args: str) -> str:
    """Return the stdout of a git command that must succeed."""
    result = _history_git(root, *args)
    if result.returncode != 0:
        raise FreshnessHistoryError(
            f"git {' '.join(args)} failed in {root}: {result.stderr.strip()}"
        )
    return result.stdout


def _null_separated(output: str) -> set[str]:
    """Split ``-z`` output into its paths."""
    return {path for path in output.split("\0") if path}


def _merge_base(root: Path, base_ref: str) -> str:
    """Return the merge base of ``base_ref`` and HEAD; raise when history lacks it."""
    toplevel = _history_git(root, "rev-parse", "--show-toplevel")
    if toplevel.returncode != 0:
        raise FreshnessHistoryError(
            f"{root} is not a git checkout; the freshness check needs its history: "
            f"{toplevel.stderr.strip()}"
        )
    if Path(toplevel.stdout.strip()).resolve() != root.resolve():
        raise FreshnessHistoryError(
            f"{root} has no git checkout of its own; git resolves it to "
            f"{toplevel.stdout.strip()}"
        )
    shallow = _history_output(root, "rev-parse", "--is-shallow-repository")
    if shallow.strip() == "true":
        raise FreshnessHistoryError(
            f"{root} is a shallow clone; run `git fetch --unshallow` before the gate"
        )
    if _resolve_commit(root, base_ref) is None:
        raise FreshnessHistoryError(
            f"{base_ref} names no commit in {root}; run `git fetch origin main` "
            "before the gate"
        )
    merge_base = _history_git(root, "merge-base", base_ref, "HEAD")
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        raise FreshnessHistoryError(
            f"{base_ref} and HEAD have no merge base in {root}: "
            f"{merge_base.stderr.strip()}"
        )
    return merge_base.stdout.strip()


def _resolve_commit(root: Path, value: Any) -> str | None:
    """Return the full SHA that ``value`` names, or None when it names no commit."""
    if not isinstance(value, str) or not value or value.startswith("-"):
        return None
    result = _history_git(
        root, "rev-parse", "--verify", "--quiet", f"{value}^{{commit}}"
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """True when ``ancestor`` is ``descendant`` or one of its ancestors."""
    result = _history_git(root, "merge-base", "--is-ancestor", ancestor, descendant)
    if result.returncode not in (0, 1):
        raise FreshnessHistoryError(
            f"git merge-base --is-ancestor {ancestor} {descendant} failed in "
            f"{root}: {result.stderr.strip()}"
        )
    return result.returncode == 0


def _changed_paths(root: Path, merge_base: str) -> list[str]:
    """Paths the working tree changes against ``merge_base``, untracked included."""
    changed = _null_separated(
        _history_output(
            root,
            "diff",
            "--no-ext-diff",
            "--name-only",
            "--no-renames",
            "-z",
            merge_base,
        )
    )
    changed |= _null_separated(
        _history_output(root, "ls-files", "--others", "--exclude-standard", "-z")
    )
    return sorted(changed)


def _history_paths(root: Path) -> frozenset[str]:
    """Git's file view of ``root``, read without any inherited ``GIT_*``."""
    listing = _history_output(
        root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"
    )
    return frozenset(
        path for path in _null_separated(listing) if (root / path).is_file()
    )


def _declared_sources(front_matter: dict[str, Any] | None) -> set[str]:
    """The string entries of a front matter block's ``sources`` list."""
    sources = (front_matter or {}).get("sources")
    if not isinstance(sources, list):
        return set()
    return {source for source in sources if isinstance(source, str) and source}


def _matches(path: str, source: str) -> bool:
    """True when a changed ``path`` is ``source`` or lies under a ``dir/`` entry."""
    return path == source or (source.endswith("/") and path.startswith(source))


def _stamp_errors(
    root: Path,
    path: str,
    stamp: Any,
    base_stamp: Any,
    merge_base: str,
) -> list[str]:
    """Check a moved or new ``verified_commit`` against the history on main."""
    resolved = _resolve_commit(root, stamp)
    if resolved is None:
        return [f"{path}: verified_commit {stamp!r} names no commit in this repository"]
    errors: list[str] = []
    if not _is_ancestor(root, resolved, merge_base):
        errors.append(
            f"{path}: verified_commit {stamp!r} is not the merge base "
            f"{merge_base[:12]} or one of its ancestors"
        )
    base_resolved = _resolve_commit(root, base_stamp)
    if base_resolved is not None and not _is_ancestor(root, base_resolved, resolved):
        errors.append(
            f"{path}: verified_commit {stamp!r} does not descend from the merge "
            f"base's value {base_stamp!r}"
        )
    return errors


def freshness_errors(root: Path, base_ref: str = BASE_REF) -> list[str]:
    """Fail every canonical document whose sources changed without a re-stamp.

    The branch's change is the working tree, uncommitted and untracked files
    included, against its merge base with ``base_ref``. A document canonical at
    the merge base or now, whose sources at either point were touched, must
    move ``verified_commit``; a moved or new stamp must name the merge base or
    an ancestor and descend from the stamp it replaces. Missing history raises
    ``FreshnessHistoryError`` rather than passing.
    """
    merge_base = _merge_base(root, base_ref)
    changed = _changed_paths(root, merge_base)
    errors: list[str] = []
    documents = classify(root, _history_paths(root)).documents
    for path, front_matter in documents.items():
        base: dict[str, Any] | None = None
        if _history_git(root, "cat-file", "-e", f"{merge_base}:{path}").returncode == 0:
            text = _history_output(root, "show", f"{merge_base}:{path}")
            try:
                base = read_front_matter(text)
            except (FrontMatterError, yaml.YAMLError) as exc:
                errors.append(
                    f"{path}: front matter at the merge base {merge_base[:12]} "
                    f"cannot be read: {exc}"
                )
                continue
        if "canonical" not in (front_matter.get("status"), (base or {}).get("status")):
            continue
        sources = _declared_sources(front_matter) | _declared_sources(base)
        touched = [
            changed_path
            for changed_path in changed
            if any(_matches(changed_path, source) for source in sources)
        ]
        stamp = front_matter.get("verified_commit")
        if base is None:
            errors.extend(_stamp_errors(root, path, stamp, None, merge_base))
            continue
        base_stamp = base.get("verified_commit")
        base_resolved = _resolve_commit(root, base_stamp)
        if base_resolved is not None:
            unchanged = _resolve_commit(root, stamp) == base_resolved
        else:
            unchanged = stamp == base_stamp
        if not unchanged:
            errors.extend(_stamp_errors(root, path, stamp, base_stamp, merge_base))
        elif touched:
            errors.append(
                f"{path}: {', '.join(touched)} changed since the merge base "
                f"{merge_base[:12]} without a re-stamped verified_commit"
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


def test_declared_sources_carry_a_fresh_verified_commit() -> None:
    """This branch re-stamps every canonical document whose sources it changes."""
    assert freshness_errors(ROOT) == []


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
        (VALID.replace("src/app.py", "src"), "names a directory; sources name files"),
        (VALID.replace("src/app.py", "src/"), "names a directory; sources name files"),
        (VALID.replace("src/app.py", "lib/"), "names a directory; sources name files"),
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


def test_unlisted_directory_source_is_named_a_directory(tmp_path: Path) -> None:
    """A directory git does not list (ignored or empty) is not a missing file."""
    _tree(tmp_path)
    _write(tmp_path, ".gitignore", "build/\n")
    _write(tmp_path, "build/out.txt", "")
    (tmp_path / "empty").mkdir()
    for value in ("build", "empty"):
        _write(tmp_path, "docs/a.md", _canonical((value,)))
        assert classify(tmp_path, repository_paths(tmp_path)).errors == [
            f"docs/a.md: source {value!r} names a directory; sources name files"
        ]


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


def _git(root: Path, *args: str) -> str:
    """Run git in ``root``, isolated from the user's config and any hook's GIT_*."""
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=NEXUS test",
            "-c",
            "user.email=test@nexus.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "init.defaultBranch=main",
            *args,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _canonical(
    sources: tuple[str, ...] = ("src/app.py",),
    stamp: str = "abc1234",
    status: str = "canonical",
    title: str = "# Title\n",
) -> str:
    """Render ``docs/a.md``-style front matter declaring ``sources``."""
    listed = "".join(f"  - {source}\n" for source in sources)
    return _document(
        f'status: {status}\nsources:\n{listed}verified_commit: "{stamp}"\n', title
    )


def _commit(root: Path, message: str) -> str:
    """Commit every change in ``root`` and return the new HEAD."""
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _tree(root: Path, document: str | None = None) -> str:
    """Build the synthetic repository on ``main`` and return its first commit.

    The tree holds ``src/app.py``, ``src/other.py`` and ``docs/a.md``
    (canonical, declaring ``src/app.py`` unless ``document`` says otherwise).
    """
    root.mkdir(parents=True, exist_ok=True)
    _write(root, "src/app.py", "VALUE = 1\n")
    _write(root, "src/other.py", "OTHER = 1\n")
    _write(root, "docs/a.md", _canonical() if document is None else document)
    _git(root, "init", "-q")
    return _commit(root, "main")


def _branch(root: Path) -> str:
    """Start ``feature`` at ``main`` and return the merge base."""
    _git(root, "checkout", "-q", "-b", "feature")
    return _git(root, "merge-base", "main", "HEAD")


def _stale(path: str, touched: str, merge_base: str) -> str:
    """The error for a source change that left ``verified_commit`` in place."""
    return (
        f"{path}: {touched} changed since the merge base {merge_base[:12]} "
        "without a re-stamped verified_commit"
    )


def test_source_change_without_restamp_fails(tmp_path: Path) -> None:
    """Committed, uncommitted and untracked source changes all need a re-stamp."""
    committed = tmp_path / "committed"
    _tree(committed)
    merge_base = _branch(committed)
    _write(committed, "src/app.py", "VALUE = 2\n")
    _commit(committed, "edit app")
    assert freshness_errors(committed, base_ref="main") == [
        _stale("docs/a.md", "src/app.py", merge_base)
    ]

    uncommitted = tmp_path / "uncommitted"
    _tree(uncommitted)
    merge_base = _branch(uncommitted)
    _write(uncommitted, "src/app.py", "VALUE = 2\n")
    assert freshness_errors(uncommitted, base_ref="main") == [
        _stale("docs/a.md", "src/app.py", merge_base)
    ]

    untracked = tmp_path / "untracked"
    _tree(untracked)
    merge_base = _branch(untracked)
    _write(untracked, "src/new.py", "NEW = 1\n")
    _write(untracked, "docs/a.md", _canonical(("src/app.py", "src/new.py")))
    assert freshness_errors(untracked, base_ref="main") == [
        _stale("docs/a.md", "src/new.py", merge_base)
    ]


def test_document_edit_alone_is_not_a_restamp(tmp_path: Path) -> None:
    """Editing the body, or respelling the same commit, does not re-verify."""
    body = tmp_path / "body"
    _tree(body)
    merge_base = _branch(body)
    _write(body, "src/app.py", "VALUE = 2\n")
    _write(body, "docs/a.md", _canonical(title="# Title\n\nA new paragraph.\n"))
    _commit(body, "edit app and the document body")
    assert freshness_errors(body, base_ref="main") == [
        _stale("docs/a.md", "src/app.py", merge_base)
    ]

    spelling = tmp_path / "spelling"
    first = _tree(spelling)
    _write(spelling, "docs/a.md", _canonical(stamp=first))
    _commit(spelling, "stamp the first commit")
    merge_base = _branch(spelling)
    _write(spelling, "src/app.py", "VALUE = 2\n")
    _write(spelling, "docs/a.md", _canonical(stamp=first[:7]))
    _commit(spelling, "edit app and shorten the stamp")
    assert freshness_errors(spelling, base_ref="main") == [
        _stale("docs/a.md", "src/app.py", merge_base)
    ]


def test_same_change_restamped_passes(tmp_path: Path) -> None:
    """A source change passes when the stamp moves to the merge base or before."""
    at_base = tmp_path / "at_base"
    _tree(at_base)
    merge_base = _branch(at_base)
    _write(at_base, "src/app.py", "VALUE = 2\n")
    _write(at_base, "docs/a.md", _canonical(stamp=merge_base))
    _commit(at_base, "edit app and re-stamp")
    assert freshness_errors(at_base, base_ref="main") == []

    at_parent = tmp_path / "at_parent"
    first = _tree(at_parent)
    _write(at_parent, "src/other.py", "OTHER = 2\n")
    _commit(at_parent, "second main commit")
    _branch(at_parent)
    _write(at_parent, "src/app.py", "VALUE = 2\n")
    _write(at_parent, "docs/a.md", _canonical(stamp=first))
    _commit(at_parent, "edit app and re-stamp at the parent")
    assert freshness_errors(at_parent, base_ref="main") == []


def test_dropping_a_source_does_not_evade(tmp_path: Path) -> None:
    """The merge base's sources and status count as much as the current ones."""
    dropped = tmp_path / "dropped"
    _tree(dropped)
    merge_base = _branch(dropped)
    _write(dropped, "src/app.py", "VALUE = 2\n")
    _write(dropped, "docs/a.md", _canonical(("src/other.py",)))
    _commit(dropped, "drop app from sources and edit it")
    assert freshness_errors(dropped, base_ref="main") == [
        _stale("docs/a.md", "src/app.py", merge_base)
    ]

    narrowed = tmp_path / "narrowed"
    _tree(narrowed, _canonical(("src/",)))
    merge_base = _branch(narrowed)
    _write(narrowed, "src/other.py", "OTHER = 2\n")
    _write(narrowed, "docs/a.md", _canonical())
    _commit(narrowed, "narrow sources to a file and edit another file")
    assert freshness_errors(narrowed, base_ref="main") == [
        _stale("docs/a.md", "src/other.py", merge_base)
    ]

    retired = tmp_path / "retired"
    _tree(retired)
    merge_base = _branch(retired)
    _write(retired, "src/app.py", "VALUE = 2\n")
    _write(retired, "docs/a.md", _canonical(status="historical"))
    _commit(retired, "retire the document and edit app")
    assert freshness_errors(retired, base_ref="main") == [
        _stale("docs/a.md", "src/app.py", merge_base)
    ]


def test_restamp_must_name_history_on_main(tmp_path: Path) -> None:
    """A moved stamp names the merge base or an ancestor and never moves back."""
    unknown = tmp_path / "unknown"
    _tree(unknown)
    _branch(unknown)
    _write(unknown, "src/app.py", "VALUE = 2\n")
    _write(unknown, "docs/a.md", _canonical(stamp="0000000"))
    _commit(unknown, "edit app and stamp no commit")
    assert freshness_errors(unknown, base_ref="main") == [
        "docs/a.md: verified_commit '0000000' names no commit in this repository"
    ]

    branch_only = tmp_path / "branch_only"
    _tree(branch_only)
    merge_base = _branch(branch_only)
    _write(branch_only, "src/app.py", "VALUE = 2\n")
    feature_commit = _commit(branch_only, "edit app")
    _write(branch_only, "docs/a.md", _canonical(stamp=feature_commit))
    _commit(branch_only, "stamp the branch commit")
    assert freshness_errors(branch_only, base_ref="main") == [
        f"docs/a.md: verified_commit {feature_commit!r} is not the merge base "
        f"{merge_base[:12]} or one of its ancestors"
    ]

    backward = tmp_path / "backward"
    first = _tree(backward)
    _write(backward, "docs/a.md", _canonical(stamp=first))
    second = _commit(backward, "stamp the first commit")
    _write(backward, "docs/a.md", _canonical(stamp=second))
    _commit(backward, "stamp the second commit")
    _branch(backward)
    _write(backward, "src/app.py", "VALUE = 2\n")
    _write(backward, "docs/a.md", _canonical(stamp=first))
    _commit(backward, "edit app and move the stamp back")
    assert freshness_errors(backward, base_ref="main") == [
        f"docs/a.md: verified_commit {first!r} does not descend from the merge "
        f"base's value {second!r}"
    ]


def test_new_canonical_document_needs_a_stamp_on_main(tmp_path: Path) -> None:
    """A document new on the branch must name a commit on main."""
    _tree(tmp_path)
    merge_base = _branch(tmp_path)
    _write(tmp_path, "docs/b.md", _canonical(stamp="0000000"))
    _commit(tmp_path, "add a canonical document")
    assert freshness_errors(tmp_path, base_ref="main") == [
        "docs/b.md: verified_commit '0000000' names no commit in this repository"
    ]

    _write(tmp_path, "docs/b.md", _canonical(stamp=merge_base))
    _commit(tmp_path, "stamp it with the merge base")
    assert freshness_errors(tmp_path, base_ref="main") == []


def test_unreadable_base_front_matter_is_an_error(tmp_path: Path) -> None:
    """A block the merge base cannot parse is reported, never treated as absent."""
    _tree(tmp_path, "---\nstatus: canonical\n# Title\n")
    _branch(tmp_path)
    _write(tmp_path, "docs/a.md", _canonical())
    _commit(tmp_path, "repair the front matter")
    merge_base = _git(tmp_path, "merge-base", "main", "HEAD")
    assert freshness_errors(tmp_path, base_ref="main") == [
        f"docs/a.md: front matter at the merge base {merge_base[:12]} cannot be "
        "read: front matter opened on line 1 is never closed"
    ]


def test_unrelated_and_historical_changes_pass(tmp_path: Path) -> None:
    """Undeclared paths and historical documents' sources need no re-stamp."""
    unrelated = tmp_path / "unrelated"
    _tree(unrelated)
    _branch(unrelated)
    _write(unrelated, "src/other.py", "OTHER = 2\n")
    _commit(unrelated, "edit an undeclared file")
    assert freshness_errors(unrelated, base_ref="main") == []

    historical = tmp_path / "historical"
    _tree(historical)
    _write(historical, "docs/h.md", _canonical(status="historical"))
    _commit(historical, "add a historical document")
    merge_base = _branch(historical)
    _write(historical, "src/app.py", "VALUE = 2\n")
    # docs/a.md moves its stamp with the change, so only docs/h.md could fail.
    _write(historical, "docs/a.md", _canonical(stamp=merge_base))
    _commit(historical, "edit app")
    assert freshness_errors(historical, base_ref="main") == []


def test_missing_history_fails_loudly(tmp_path: Path) -> None:
    """Without the history the check needs, it raises instead of passing."""
    plain = tmp_path / "plain"
    _write(plain, "src/app.py", "VALUE = 1\n")
    _write(plain, "docs/a.md", _canonical())
    with pytest.raises(FreshnessHistoryError, match="is not a git checkout"):
        freshness_errors(plain, base_ref="main")

    outer = tmp_path / "outer"
    _tree(outer)
    nested = outer / "nested"
    _write(nested, "src/app.py", "VALUE = 1\n")
    _write(nested, "docs/a.md", _canonical())
    with pytest.raises(FreshnessHistoryError, match="no git checkout of its own"):
        freshness_errors(nested, base_ref="main")

    source = tmp_path / "source"
    _tree(source)
    _write(source, "src/other.py", "OTHER = 2\n")
    _commit(source, "second commit")
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", source.as_uri(), str(shallow))
    assert _git(shallow, "rev-parse", "--is-shallow-repository") == "true"
    with pytest.raises(FreshnessHistoryError, match="git fetch --unshallow"):
        freshness_errors(shallow, base_ref="main")

    absent = tmp_path / "absent"
    _tree(absent)
    _branch(absent)
    with pytest.raises(FreshnessHistoryError, match="git fetch origin main"):
        freshness_errors(absent, base_ref="no-such-branch")

    orphan = tmp_path / "orphan"
    _tree(orphan)
    _git(orphan, "checkout", "-q", "--orphan", "lonely")
    _commit(orphan, "orphan commit")
    _git(orphan, "checkout", "-q", "main")
    with pytest.raises(FreshnessHistoryError, match="no merge base"):
        freshness_errors(orphan, base_ref="lonely")


def test_inherited_git_environment_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hook's GIT_DIR or GIT_WORK_TREE cannot hide documents from the check."""
    root = tmp_path / "repo"
    _tree(root)
    merge_base = _branch(root)
    _write(root, "src/app.py", "VALUE = 2\n")
    _commit(root, "edit app")
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    _write(other, ".git/info/exclude", "docs/\n")
    expected = [_stale("docs/a.md", "src/app.py", merge_base)]

    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    assert freshness_errors(root, base_ref="main") == expected

    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    assert freshness_errors(root, base_ref="main") == expected
