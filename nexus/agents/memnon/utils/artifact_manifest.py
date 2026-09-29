"""Production model artifact lock behind ``nexus models lock|verify``.

The runtime loads exactly one embedder (the single ``is_active`` entry in
``[memnon.models]``) and, while reranking is enabled, the cross-encoder at
``[memnon.retrieval.cross_encoder_reranking].model_path``, both from local
artifact directories. ``lock`` records what those directories hold (repository,
revision and where the revision was read, license, dimensions, and each file's
sha256 and size) in the JSON lock named by ``[memnon.artifacts].lock_file``.
``verify`` is read-only: it re-hashes the configured directories and reports
every missing, changed or unexpected file, a folder revision that differs from
the lock, and any drift between nexus.toml and the lock, with the command that
repairs it. Every ``hf download`` restore command, here and in the loaders,
pins ``--revision`` whenever the lock or the folder records one.

Neither command downloads anything. ``lock`` runs on the host that already
holds the artifacts (issue #812).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from nexus.config.loader import RUNTIME_CONFIG_ENV, load_settings
from nexus.config.settings_models import Settings
from nexus.runtime.contract import HOME_ENV
from nexus.runtime.home import RuntimeHomeError

MANIFEST_SCHEMA_VERSION = 1
EMBEDDER_ROLE = "embedder"
RERANKER_ROLE = "reranker"

# Where a locked revision was read (the lock's ``revision_source``): Hugging
# Face download metadata, or the HEAD commit of a git checkout of the model
# repository.
REVISION_SOURCE_HUGGINGFACE = "huggingface"
REVISION_SOURCE_GIT = "git"

# Local bookkeeping that is not part of a model artifact: Hugging Face
# download metadata (.cache/huggingface), VCS state (a .git directory, or the
# .git file a separate git directory leaves) and Finder litter.
_IGNORED_DIRECTORIES = frozenset({".cache", ".git"})
_IGNORED_FILES = frozenset({".DS_Store", ".git"})

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HF_DOWNLOAD_METADATA = Path(".cache") / "huggingface" / "download"
_FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
_LICENSE_LINE = re.compile(
    r"^license:[ \t]*['\"]?([^'\"\n#]+?)['\"]?[ \t]*(?:#.*)?$", re.M
)


class ArtifactLockError(RuntimeError):
    """A production artifact cannot be locked, or the lock cannot be read."""


@dataclass(frozen=True)
class ArtifactSpec:
    """One production model artifact as nexus.toml declares it."""

    role: str
    name: str
    repo_id: Optional[str]
    local_path: Path
    dimensions: Optional[int]

    @property
    def label(self) -> str:
        """Human-readable identity used in lock and verify messages."""
        return f"{self.role} '{self.name}'"


@dataclass(frozen=True)
class VerifyReport:
    """Outcome of comparing the local artifacts and nexus.toml with the lock."""

    problems: List[str]
    remediation: List[str]

    @property
    def ok(self) -> bool:
        """True when nexus.toml agrees with the lock and every file matches."""
        return not self.problems


def production_artifact_specs(settings: Settings) -> List[ArtifactSpec]:
    """Return the active embedder and, while reranking is enabled, the reranker.

    The reranker's repository comes from the candidate registry entry whose
    ``local_path`` is the production ``model_path``.
    """

    active = [
        (name, model)
        for name, model in settings.memnon.models.items()
        if model.is_active
    ]
    if len(active) != 1:
        raise ArtifactLockError(
            "[memnon.models] must mark exactly one embedder is_active = true; "
            f"found {[name for name, _ in active]}"
        )
    name, model = active[0]
    specs = [
        ArtifactSpec(
            role=EMBEDDER_ROLE,
            name=name,
            repo_id=model.remote_path or None,
            local_path=Path(model.local_path),
            dimensions=model.dimensions,
        )
    ]

    reranking = settings.memnon.retrieval.cross_encoder_reranking
    if reranking.enabled:
        model_path = Path(reranking.model_path)
        matches = sorted(
            candidate_name
            for candidate_name, candidate in reranking.candidates.items()
            if Path(candidate.local_path) == model_path
        )
        if len(matches) != 1:
            raise ArtifactLockError(
                f"The production reranker model_path {model_path} must match "
                "exactly one [memnon.retrieval.cross_encoder_reranking.candidates] "
                f"entry naming its repository; found {matches}"
            )
        candidate = reranking.candidates[matches[0]]
        specs.append(
            ArtifactSpec(
                role=RERANKER_ROLE,
                name=matches[0],
                repo_id=candidate.remote_path or None,
                local_path=model_path,
                dimensions=None,
            )
        )
    return specs


def lock_file_path(settings: Settings) -> Path:
    """Resolve ``[memnon.artifacts].lock_file`` against the repository root."""

    path = Path(settings.memnon.artifacts.lock_file)
    return path if path.is_absolute() else _REPO_ROOT / path


def declared_embedding_dimensions(root: Path) -> int:
    """Read the output dimension a sentence-transformers artifact declares.

    Walks ``modules.json`` in order: a Pooling module emits
    ``word_embedding_dimension`` per enabled pooling mode, and a Dense module
    replaces the running dimension with its ``out_features``.
    """

    modules_path = root / "modules.json"
    if not modules_path.is_file():
        raise ArtifactLockError(
            f"{root} has no modules.json; the embedder must be a "
            "sentence-transformers artifact that declares its output dimension"
        )
    dimension: Optional[int] = None
    for module in json.loads(modules_path.read_text(encoding="utf-8")):
        module_type = str(module.get("type", ""))
        config_path = root / str(module.get("path", "")) / "config.json"
        if module_type.endswith("Pooling"):
            config = json.loads(config_path.read_text(encoding="utf-8"))
            modes = sum(
                1
                for key, value in config.items()
                if key.startswith("pooling_mode_") and value is True
            )
            if modes == 0:
                raise ArtifactLockError(f"{config_path} enables no pooling mode")
            dimension = int(config["word_embedding_dimension"]) * modes
        elif module_type.endswith("Dense"):
            config = json.loads(config_path.read_text(encoding="utf-8"))
            dimension = int(config["out_features"])
    if dimension is None:
        raise ArtifactLockError(
            f"{modules_path} declares no Pooling or Dense module, so the "
            "embedding dimension cannot be read from the artifact"
        )
    return dimension


def _artifact_files(root: Path) -> List[str]:
    """List the artifact's files as sorted POSIX paths relative to ``root``."""

    found: List[str] = []
    for directory, subdirectories, filenames in os.walk(root, followlinks=True):
        subdirectories[:] = [
            name for name in subdirectories if name not in _IGNORED_DIRECTORIES
        ]
        base = Path(directory)
        found.extend(
            (base / filename).relative_to(root).as_posix()
            for filename in filenames
            if filename not in _IGNORED_FILES
        )
    return sorted(found)


def _sha256(path: Path) -> str:
    """Return the hex sha256 of a file's contents."""

    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _snapshot_revision(root: Path, files: Sequence[str]) -> Optional[str]:
    """Return the Hugging Face commit the artifact was downloaded at, if recorded.

    A Hub cache snapshot directory (``.../snapshots/<commit>``) is named by
    its commit. ``hf download --local-dir`` records the commit as the first
    line of ``.cache/huggingface/download/<file>.metadata``. Anything else
    (a copied or locally trained directory) has no recorded revision.
    """

    resolved = root.resolve()
    if resolved.parent.name == "snapshots":
        return resolved.name
    commits = set()
    for relative in files:
        metadata = root / _HF_DOWNLOAD_METADATA / f"{relative}.metadata"
        if metadata.is_file():
            lines = metadata.read_text(encoding="utf-8").splitlines()
            if lines and lines[0].strip():
                commits.add(lines[0].strip())
    if len(commits) > 1:
        raise ArtifactLockError(
            f"{root} mixes files downloaded at several revisions "
            f"{sorted(commits)}; re-download it at one revision before locking"
        )
    return next(iter(commits), None)


def _git_revision(root: Path) -> Optional[str]:
    """Return the HEAD commit of the git checkout at ``root``, if it is one.

    Only a ``.git`` directory or ``.git`` file in ``root`` itself counts, and
    ``--git-dir`` names it: git's own discovery would walk up to an enclosing
    repository (model folders sit inside this checkout, under ``models/``)
    whenever ``root`` has no valid ``.git``. The ``GIT_*`` variables a git hook
    exports are dropped so they cannot point the lookup elsewhere either.

    Raises:
        ArtifactLockError: When ``root`` has a ``.git`` but git cannot read a
            HEAD commit from it, or git is not installed.
    """

    git_dir = root / ".git"
    if not git_dir.exists():
        return None
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    try:
        result = subprocess.run(
            ["git", f"--git-dir={git_dir}", "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ArtifactLockError(
            f"{root} is a git checkout, but no git executable is on PATH to read "
            "its HEAD commit"
        ) from exc
    if result.returncode != 0:
        raise ArtifactLockError(
            f"{root} has a .git, but `git rev-parse --verify HEAD` failed there: "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def artifact_revision(
    root: Path, files: Optional[Sequence[str]] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Return the revision an artifact folder records and where it was read.

    Two sources, reported as the lock's ``revision_source``:
    ``huggingface``, the commit in Hugging Face download metadata (a Hub
    cache snapshot directory, or the files ``hf download --local-dir``
    writes); and ``git``, the HEAD commit of a git checkout of the model
    repository. A Hub commit and a git commit of the same repository are the
    same identifier, so either pins ``hf download --revision``.

    Args:
        root: The artifact directory
        files: Its artifact files, when already listed

    Returns:
        ``(revision, source)``, or ``(None, None)`` when the folder records
        neither.

    Raises:
        ArtifactLockError: When the two sources name different revisions, the
            download metadata mixes revisions, or git cannot read the
            checkout's HEAD.
    """

    listed = _artifact_files(root) if files is None else files
    found = [
        (revision, source)
        for revision, source in (
            (_snapshot_revision(root, listed), REVISION_SOURCE_HUGGINGFACE),
            (_git_revision(root), REVISION_SOURCE_GIT),
        )
        if revision
    ]
    if len({revision for revision, _ in found}) > 1:
        raise ArtifactLockError(
            f"{root} records revision {found[0][0]} in its Hugging Face download "
            f"metadata, but its git checkout is at {found[1][0]}; the folder must "
            "hold one revision"
        )
    return found[0] if found else (None, None)


def _declared_license(root: Path) -> Optional[str]:
    """Return the ``license`` from the model card front matter, if declared."""

    readme = root / "README.md"
    if not readme.is_file():
        return None
    front_matter = _FRONT_MATTER.match(
        readme.read_text(encoding="utf-8", errors="replace")
    )
    if front_matter is None:
        return None
    license_line = _LICENSE_LINE.search(front_matter.group(1))
    return license_line.group(1).strip() if license_line else None


def hf_download_command(
    repo_id: str, local_dir: Union[str, Path], revision: Optional[str]
) -> str:
    """Return the ``hf download`` command that restores ``repo_id``.

    ``--revision`` pins the command whenever a revision is known, so the
    restore reproduces the locked files after the repository's default branch
    moves.
    """

    pinned = f" --revision {revision}" if revision else ""
    return f"hf download {repo_id}{pinned} --local-dir {local_dir}"


def restore_revision(
    repo_id: str, local_path: Path, lock_path: Optional[Path]
) -> Optional[str]:
    """Return the revision a restore of ``repo_id`` into ``local_path`` pins.

    The lock's revision for the repository wins; otherwise the folder's own
    (:func:`artifact_revision`), when the folder exists. A lock file that does
    not exist records nothing; one that exists must parse.

    Raises:
        ArtifactLockError: When the lock cannot be read, or the folder's
            revision cannot be determined.
    """

    if lock_path is not None and lock_path.is_file():
        for entry in read_manifest(lock_path)["artifacts"]:
            if entry.get("repo_id") == repo_id and entry.get("revision"):
                return str(entry["revision"])
    if local_path.is_dir():
        return artifact_revision(local_path)[0]
    return None


def restore_command(repo_id: str, local_path: Union[str, Path]) -> str:
    """Return the pinned ``hf download`` command the model loaders name.

    Reads the lock at ``[memnon.artifacts].lock_file`` of the active settings,
    the lock ``nexus models verify`` checks, and the folder. Loaders call it
    only once a load has failed.
    """

    folder = Path(local_path)
    revision = restore_revision(repo_id, folder, lock_file_path(load_settings()))
    return hf_download_command(repo_id, folder, revision)


def _restore_hint(spec: ArtifactSpec, revision: Optional[str], then: str) -> str:
    """Name the command that restores an artifact, then the ``nexus models`` verb."""

    if spec.repo_id:
        command = hf_download_command(spec.repo_id, spec.local_path, revision)
        restore = f"`{command}`"
    else:
        restore = f"a backup of {spec.local_path}"
    return f"Restore {spec.label} from {restore}, then re-run `nexus models {then}`."


def lock_artifact(
    spec: ArtifactSpec, lock_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Compute one artifact's lock entry from its local directory.

    Args:
        spec: The artifact nexus.toml declares
        lock_path: The lock being replaced; for a missing directory, its
            revision for the repository pins the restore command

    Raises:
        ArtifactLockError: When the directory is missing, empty, declares a
            different dimension, or records conflicting revisions.
    """

    root = spec.local_path
    if not root.is_dir():
        revision = (
            restore_revision(spec.repo_id, root, lock_path) if spec.repo_id else None
        )
        raise ArtifactLockError(
            f"{spec.label}: artifact directory {root} does not exist or is not a "
            f"directory. {_restore_hint(spec, revision, 'lock')}"
        )
    files = _artifact_files(root)
    if not files:
        raise ArtifactLockError(f"{spec.label}: artifact directory {root} is empty")
    if spec.role == EMBEDDER_ROLE:
        declared = declared_embedding_dimensions(root)
        if declared != spec.dimensions:
            raise ArtifactLockError(
                f"{spec.label} produces {declared}-dimensional vectors according "
                f"to its sentence-transformers modules, but nexus.toml declares "
                f"dimensions = {spec.dimensions}"
            )
    entries = [
        {
            "path": relative,
            "size": (root / relative).stat().st_size,
            "sha256": _sha256(root / relative),
        }
        for relative in files
    ]
    revision, revision_source = artifact_revision(root, files)
    return {
        "role": spec.role,
        "name": spec.name,
        "repo_id": spec.repo_id,
        "revision": revision,
        "revision_source": revision_source,
        "license": _declared_license(root),
        "dimensions": spec.dimensions,
        "total_size": sum(entry["size"] for entry in entries),
        "files": entries,
    }


def build_manifest(
    specs: Sequence[ArtifactSpec], lock_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Compute the full lock for the production artifacts.

    ``lock_path`` is the lock being replaced; it only pins the restore
    command for a missing artifact directory.
    """

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "artifacts": [lock_artifact(spec, lock_path) for spec in specs],
    }


def write_manifest(manifest: Dict[str, Any], path: Path) -> None:
    """Write the lock deterministically (sorted keys, trailing newline)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_manifest(path: Path) -> Dict[str, Any]:
    """Read a lock written by :func:`write_manifest`.

    Raises:
        ArtifactLockError: When the lock is absent, is not a JSON object (for
            example truncated, or holding merge-conflict markers), or does not
            have the current schema.
    """

    if not path.is_file():
        raise ArtifactLockError(
            f"No model artifact lock at {path}. Run `nexus models lock` on the "
            "host that holds the production artifacts, then commit the lock."
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ArtifactLockError(
            f"{path} is not UTF-8 text ({exc.reason} at byte {exc.start}). "
            "Re-run `nexus models lock`."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ArtifactLockError(
            f"{path} is not valid JSON: {exc}. It may be truncated or hold "
            "merge-conflict markers. Re-run `nexus models lock`."
        ) from exc
    if not isinstance(manifest, dict):
        raise ArtifactLockError(
            f"{path} does not hold a JSON object at its top level. "
            "Re-run `nexus models lock`."
        )
    version = manifest.get("schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        raise ArtifactLockError(
            f"{path} has schema_version {version!r}; expected "
            f"{MANIFEST_SCHEMA_VERSION}. Re-run `nexus models lock`."
        )
    if not _well_formed_artifacts(manifest.get("artifacts")):
        raise ArtifactLockError(
            f"{path} is malformed: every entry in `artifacts` needs a role and a "
            "`files` list of path, size and sha256. Re-run `nexus models lock`."
        )
    return manifest


def _well_formed_artifacts(artifacts: Any) -> bool:
    """True when the lock's artifact entries have the fields verify reads."""

    return isinstance(artifacts, list) and all(
        isinstance(entry, dict)
        and isinstance(entry.get("role"), str)
        and isinstance(entry.get("files"), list)
        and all(
            isinstance(file, dict) and {"path", "size", "sha256"} <= file.keys()
            for file in entry["files"]
        )
        for entry in artifacts
    )


def _verify_files(spec: ArtifactSpec, entry: Dict[str, Any]) -> List[str]:
    """Compare one artifact directory with its locked file list."""

    root = spec.local_path
    if not root.is_dir():
        return [f"artifact directory {root} does not exist or is not a directory"]
    locked = {file["path"]: file for file in entry["files"]}
    present = set(_artifact_files(root))
    problems: List[str] = []
    for relative in sorted(locked):
        path = root / relative
        if relative not in present or not path.is_file():
            problems.append(f"missing file {relative}")
            continue
        size = path.stat().st_size
        if size != locked[relative]["size"]:
            problems.append(
                f"{relative} is {size} bytes; the lock records "
                f"{locked[relative]['size']}"
            )
        elif _sha256(path) != locked[relative]["sha256"]:
            problems.append(f"{relative} sha256 differs from the lock")
    problems.extend(
        f"unexpected file {relative} is not in the lock"
        for relative in sorted(present - set(locked))
    )
    return problems


def verify_manifest(
    specs: Sequence[ArtifactSpec], manifest: Dict[str, Any]
) -> VerifyReport:
    """Check nexus.toml and the local artifact directories against the lock.

    Read-only: nothing is written, downloaded or repaired.
    """

    problems: List[str] = []
    remediation: List[str] = []
    locked = {entry["role"]: entry for entry in manifest["artifacts"]}
    config_drift = False
    file_drift = False
    for spec in specs:
        entry = locked.pop(spec.role, None)
        if entry is None:
            problems.append(f"{spec.label} is configured but absent from the lock")
            config_drift = True
            continue
        drifted = [
            field
            for field, configured in (
                ("name", spec.name),
                ("repo_id", spec.repo_id),
                ("dimensions", spec.dimensions),
            )
            if entry.get(field) != configured
        ]
        for field in drifted:
            problems.append(
                f"{spec.label}: nexus.toml {field} {getattr(spec, field)!r} "
                f"differs from the locked {entry.get(field)!r}"
            )
            config_drift = True
        if {"name", "repo_id"} & set(drifted):
            # A different model is configured; its files cannot match.
            continue
        file_problems = _verify_files(spec, entry)
        folder_revision: Optional[str] = None
        if spec.local_path.is_dir():
            folder_revision, source = artifact_revision(spec.local_path)
            if folder_revision is not None and folder_revision != entry.get("revision"):
                file_problems.append(
                    f"{source} revision {folder_revision!r} differs from the "
                    f"locked {entry.get('revision')!r}"
                )
        if file_problems:
            problems.extend(f"{spec.label}: {problem}" for problem in file_problems)
            remediation.append(
                _restore_hint(spec, entry.get("revision") or folder_revision, "verify")
            )
            file_drift = True
    for role, entry in sorted(locked.items()):
        problems.append(
            f"the lock records {role} '{entry.get('name')}', which nexus.toml "
            "no longer configures"
        )
        config_drift = True
    if file_drift:
        remediation.append(
            "If a changed artifact is an intentional upgrade, re-run "
            "`nexus models lock` on the host that holds it and commit the lock."
        )
    if config_drift:
        remediation.append(
            "If the nexus.toml change is intentional, re-run `nexus models lock` "
            "on the host that holds the artifacts and commit the lock; otherwise "
            "revert nexus.toml."
        )
    return VerifyReport(problems=problems, remediation=remediation)


def _format_size(size: int) -> str:
    """Render a byte count in MiB, the scale of model artifacts."""

    return f"{size / (1024 * 1024):.1f} MiB"


def _lock_summary(manifest: Dict[str, Any], path: Path) -> str:
    """Describe a freshly written lock for the CLI."""

    lines = [f"Locked {len(manifest['artifacts'])} artifact(s) in {path}:"]
    for entry in manifest["artifacts"]:
        if entry["revision"]:
            revision = f"{entry['revision']} ({entry['revision_source']})"
        else:
            revision = "unknown (no Hugging Face download metadata or git checkout)"
        dimensions = f", {entry['dimensions']}d" if entry["dimensions"] else ""
        lines.append(
            f"  {entry['role']} {entry['name']}: {entry['repo_id'] or 'no repository'}"
            f" @ {revision}{dimensions}, {len(entry['files'])} files, "
            f"{_format_size(entry['total_size'])}"
        )
    return "\n".join(lines)


def run_models_command(command: str, config_path: Optional[str]) -> Dict[str, Any]:
    """Run ``nexus models lock`` or ``nexus models verify`` for the CLI.

    ``config_path`` is ``--config``; without it, :func:`load_settings` owns the
    fallback chain (an active settings scope, then the runtime-home locator
    rule: NEXUS_HOME, NEXUS_RUNTIME_CONFIG, the checkout's nexus.toml).
    Returns the CLI result mapping: ``success`` plus a ``message`` on success,
    or an ``error`` naming every problem and its remediation on failure.
    """

    if command not in ("lock", "verify"):
        raise ValueError(f"Unknown models command: {command!r}")
    try:
        settings = load_settings(config_path or None)
    except FileNotFoundError as exc:
        return {
            "success": False,
            "error": f"{exc}. Pass --config with the path to nexus.toml, set "
            f"{HOME_ENV} to a home containing nexus.toml, or set "
            f"{RUNTIME_CONFIG_ENV} to an existing nexus.toml.",
        }
    except RuntimeHomeError as exc:
        return {"success": False, "error": str(exc)}
    lock_path = lock_file_path(settings)
    try:
        specs = production_artifact_specs(settings)
        if command == "lock":
            manifest = build_manifest(specs, lock_path)
            write_manifest(manifest, lock_path)
            return {
                "success": True,
                "lock_file": str(lock_path),
                "message": _lock_summary(manifest, lock_path),
            }
        report = verify_manifest(specs, read_manifest(lock_path))
    except ArtifactLockError as exc:
        return {"success": False, "error": str(exc)}
    if report.ok:
        verified = ", ".join(f"{spec.role} {spec.name}" for spec in specs)
        return {
            "success": True,
            "lock_file": str(lock_path),
            "message": f"Model artifacts match {lock_path}: {verified}",
        }
    lines = [f"Model artifacts do not match {lock_path}:"]
    lines.extend(f"  - {problem}" for problem in report.problems)
    lines.append("Remediation:")
    lines.extend(f"  - {step}" for step in report.remediation)
    return {
        "success": False,
        "lock_file": str(lock_path),
        "problems": report.problems,
        "error": "\n".join(lines),
    }
