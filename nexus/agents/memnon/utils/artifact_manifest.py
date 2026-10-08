"""Production artifact lock and ``nexus models lock|verify|plan|fetch``.

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

``plan`` reports missing or drifted artifacts without hashing or downloading.
``fetch`` downloads only absent, pinned artifacts, then verifies their hashes;
it refuses existing drifted folders and never replaces them or rewrites the
lock. ``lock`` runs on the host that already holds the artifacts (issue #812).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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
    config_problems: List[str]

    @property
    def ok(self) -> bool:
        """True when nexus.toml agrees with the lock and every file matches."""
        return not self.problems


@dataclass(frozen=True)
class ArtifactCheck:
    """One production configuration and lock with their verification result."""

    lock_path: Path
    specs: List[ArtifactSpec]
    manifest: Dict[str, Any]
    report: VerifyReport


def production_artifact_specs(settings: Settings) -> List[ArtifactSpec]:
    """Return the active embedder and, while reranking is enabled, the reranker.

    The reranker's lock name and repository are the production
    ``[memnon.retrieval.cross_encoder_reranking]`` ``name`` and
    ``remote_path``.
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
        specs.append(
            ArtifactSpec(
                role=RERANKER_ROLE,
                name=reranking.name,
                repo_id=reranking.remote_path,
                local_path=Path(reranking.model_path),
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


def _verify_files(
    spec: ArtifactSpec, entry: Dict[str, Any], *, hash_files: bool
) -> List[str]:
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
        elif hash_files and _sha256(path) != locked[relative]["sha256"]:
            problems.append(f"{relative} sha256 differs from the lock")
    problems.extend(
        f"unexpected file {relative} is not in the lock"
        for relative in sorted(present - set(locked))
    )
    return problems


def _artifact_problems(
    spec: ArtifactSpec, entry: Dict[str, Any], *, hash_files: bool
) -> List[str]:
    """Compare one folder's files and revision with its locked artifact."""
    problems = _verify_files(spec, entry, hash_files=hash_files)
    if spec.local_path.is_dir():
        revision, source = artifact_revision(spec.local_path)
        if revision is not None and revision != entry.get("revision"):
            problems.append(
                f"{source} revision {revision!r} differs from the "
                f"locked {entry.get('revision')!r}"
            )
    return problems


def fetch_remedy(spec: ArtifactSpec) -> str:
    """Explain how to fetch a pinned artifact without replacing existing data."""
    if not os.path.lexists(spec.local_path):
        return (
            f"Run `nexus models fetch` to download {spec.label} into {spec.local_path}."
        )
    return (
        f"Move {spec.local_path} aside (`nexus models fetch` never replaces an "
        "existing folder), then run `nexus models fetch` to download "
        f"{spec.label} again."
    )


def fetch_remedy_for(
    repo_id: Optional[str], local_path: Union[str, Path]
) -> Optional[str]:
    """Return a fetch remedy only for the configured, locked production artifact."""
    if not repo_id:
        return None
    settings = load_settings()
    specs = production_artifact_specs(settings)
    for spec in specs:
        if spec.local_path != Path(local_path) or spec.repo_id != repo_id:
            continue
        path = lock_file_path(settings)
        if not path.exists():
            return None
        for entry in read_manifest(path)["artifacts"]:
            if (
                entry["role"] == spec.role
                and entry.get("name") == spec.name
                and entry.get("repo_id") == repo_id
                and entry.get("revision")
            ):
                return fetch_remedy(spec)
    return None


def _drift_remedy(spec: ArtifactSpec, entry: Dict[str, Any]) -> str:
    """Use fetch for pinned production artifacts and the old hint otherwise."""
    if spec.repo_id and entry.get("revision"):
        return fetch_remedy(spec)
    folder_revision = (
        artifact_revision(spec.local_path)[0] if spec.local_path.is_dir() else None
    )
    return _restore_hint(spec, entry.get("revision") or folder_revision, "verify")


def verify_manifest(
    specs: Sequence[ArtifactSpec], manifest: Dict[str, Any], *, hash_files: bool
) -> VerifyReport:
    """Check nexus.toml and the local artifact directories against the lock.

    Read-only: nothing is written, downloaded or repaired.
    """

    problems: List[str] = []
    remediation: List[str] = []
    config_problems: List[str] = []
    locked = {entry["role"]: entry for entry in manifest["artifacts"]}
    config_drift = False
    file_drift = False
    for spec in specs:
        entry = locked.pop(spec.role, None)
        if entry is None:
            problem = f"{spec.label} is configured but absent from the lock"
            problems.append(problem)
            config_problems.append(problem)
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
            problem = (
                f"{spec.label}: nexus.toml {field} {getattr(spec, field)!r} "
                f"differs from the locked {entry.get(field)!r}"
            )
            problems.append(problem)
            config_problems.append(problem)
            config_drift = True
        if {"name", "repo_id"} & set(drifted):
            # A different model is configured; its files cannot match.
            continue
        file_problems = _artifact_problems(spec, entry, hash_files=hash_files)
        if file_problems:
            problems.extend(f"{spec.label}: {problem}" for problem in file_problems)
            remediation.append(_drift_remedy(spec, entry))
            file_drift = True
    for role, entry in sorted(locked.items()):
        problem = (
            f"the lock records {role} '{entry.get('name')}', which nexus.toml "
            "no longer configures"
        )
        problems.append(problem)
        config_problems.append(problem)
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
    return VerifyReport(
        problems=problems, remediation=remediation, config_problems=config_problems
    )


def verify_artifacts(settings: Settings, *, hash_files: bool) -> ArtifactCheck:
    """Read and verify the configured artifacts without writing or repairing them."""
    path = lock_file_path(settings)
    specs = production_artifact_specs(settings)
    manifest = read_manifest(path)
    report = verify_manifest(specs, manifest, hash_files=hash_files)
    return ArtifactCheck(path, specs, manifest, report)


def _mismatch_lines(report: VerifyReport) -> List[str]:
    """Render problem and remediation lines, leaving the header to the caller."""
    return [
        *(f"  - {problem}" for problem in report.problems),
        "Remediation:",
        *(f"  - {step}" for step in report.remediation),
    ]


def check_artifacts_at_boot(settings: Settings) -> str:
    """Refuse gateway boot on file-list, size, revision or configuration drift."""
    check = verify_artifacts(settings, hash_files=False)
    if not check.report.ok:
        raise ArtifactLockError(
            "\n".join(
                [
                    "The gateway will not start: model artifacts do not match "
                    f"{check.lock_path} by file list, size and revision:",
                    *_mismatch_lines(check.report),
                ]
            )
        )
    verified = ", ".join(f"{spec.role} {spec.name}" for spec in check.specs)
    return (
        f"Model artifacts match {check.lock_path} by file list, size and revision: "
        f"{verified}; nexus models verify also compares sha256."
    )


def _unpinned_problem(spec: ArtifactSpec, entry: Dict[str, Any]) -> Optional[str]:
    """Name the missing repository or locked revision that prevents a fetch."""
    if spec.repo_id and entry.get("revision"):
        return None
    missing = "repository" if not spec.repo_id else "revision"
    return (
        f"{spec.label}: fetch runs only a pinned download, and the lock records "
        f"no {missing} for it"
    )


def _failed_artifact_command(
    command: str, check: ArtifactCheck, report: VerifyReport
) -> Dict[str, Any]:
    return {
        "success": False,
        "lock_file": str(check.lock_path),
        "problems": report.problems,
        "error": "\n".join(
            [
                f"Model artifact {command} refused for {check.lock_path}:",
                *_mismatch_lines(report),
            ]
        ),
    }


def _plan_artifacts(check: ArtifactCheck) -> Dict[str, Any]:
    """Describe fetch eligibility without hashing, downloading or writing."""
    if check.report.config_problems:
        return _failed_artifact_command("plan", check, check.report)
    locked = {entry["role"]: entry for entry in check.manifest["artifacts"]}
    plan: List[Dict[str, Any]] = []
    lines = []
    for spec in check.specs:
        entry = locked[spec.role]
        download_bytes = free_bytes = None
        if os.path.lexists(spec.local_path):
            problems = _artifact_problems(spec, entry, hash_files=False)
            state = "drifted" if problems else "present"
            detail = (
                "; ".join(problems) + ". " + _drift_remedy(spec, entry)
                if problems
                else "nexus models verify also compares sha256."
            )
        elif (problem := _unpinned_problem(spec, entry)) is not None:
            state, problems = "unpinned", [problem]
            detail = problem + ". " + _restore_hint(spec, None, "verify")
        else:
            state, problems = "absent", []
            download_bytes = entry["total_size"]
            ancestor = spec.local_path.parent
            while not ancestor.exists():
                ancestor = ancestor.parent
            free_bytes = shutil.disk_usage(ancestor).free
            detail = f"fetch downloads {download_bytes} bytes; {free_bytes} bytes free."
        plan.append(
            {
                "role": spec.role,
                "name": spec.name,
                "local_path": str(spec.local_path),
                "state": state,
                "repo_id": spec.repo_id,
                "revision": entry.get("revision"),
                "download_bytes": download_bytes,
                "free_bytes": free_bytes,
                "problems": problems,
            }
        )
        lines.append(f"{spec.label}: {state} at {spec.local_path}; {detail}")
    success = all(item["state"] not in ("drifted", "unpinned") for item in plan)
    return {
        "success": success,
        "lock_file": str(check.lock_path),
        "plan": plan,
        "message" if success else "error": "\n".join(lines),
    }


def _fetch_artifacts(check: ArtifactCheck) -> Dict[str, Any]:
    """Fetch absent pinned artifacts only after every existing folder verifies."""
    if check.report.config_problems:
        return _failed_artifact_command("fetch", check, check.report)
    locked = {entry["role"]: entry for entry in check.manifest["artifacts"]}
    problems: List[str] = []
    remediation: List[str] = []
    absent: List[ArtifactSpec] = []
    for spec in check.specs:
        entry = locked[spec.role]
        if os.path.lexists(spec.local_path):
            drift = _artifact_problems(spec, entry, hash_files=True)
            if drift:
                problems.extend(f"{spec.label}: {problem}" for problem in drift)
                remediation.append(_drift_remedy(spec, entry))
        elif (problem := _unpinned_problem(spec, entry)) is not None:
            problems.append(problem)
            remediation.append(_restore_hint(spec, None, "verify"))
        else:
            absent.append(spec)
    if problems:
        return _failed_artifact_command(
            "fetch", check, VerifyReport(problems, remediation, [])
        )
    from huggingface_hub import snapshot_download

    lines = []
    for spec in check.specs:
        entry = locked[spec.role]
        if spec not in absent:
            lines.append(f"{spec.label}: already matching {check.lock_path}")
            continue
        if os.path.lexists(spec.local_path):
            raise ArtifactLockError(
                f"{spec.local_path} appeared before download; fetch never writes "
                "into an existing folder. Run nexus models verify first."
            )
        if spec.repo_id is None:
            raise ArtifactLockError(f"{spec.label} has no pinned repository")
        try:
            snapshot_download(
                repo_id=spec.repo_id,
                revision=entry["revision"],
                local_dir=str(spec.local_path),
            )
        except (
            OSError
        ) as exc:  # nexus-exception-disposition: fail; reason=hub; safety=failed result
            problem = (
                f"{spec.label}: download of {spec.repo_id} @ {entry['revision']} "
                f"failed: {exc}"
            )
            remedy = (
                f"{spec.local_path} may hold a partial download; nothing was removed. "
                "Move it aside before running nexus models fetch again."
                if os.path.lexists(spec.local_path)
                else fetch_remedy(spec)
            )
            return _failed_artifact_command(
                "fetch", check, VerifyReport([problem], [remedy], [])
            )
        drift = _artifact_problems(spec, entry, hash_files=True)
        if drift:
            return _failed_artifact_command(
                "fetch",
                check,
                VerifyReport(
                    [f"{spec.label}: {problem}" for problem in drift],
                    [fetch_remedy(spec)],
                    [],
                ),
            )
        lines.append(
            f"{spec.label}: downloaded {spec.repo_id} @ {entry['revision']} "
            f"into {spec.local_path}"
        )
    return {
        "success": True,
        "lock_file": str(check.lock_path),
        "message": "\n".join(lines),
    }


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
    """Run ``nexus models lock|verify|plan|fetch`` for the CLI.

    ``config_path`` is ``--config``; without it, :func:`load_settings` owns the
    fallback chain (an active settings scope, then the runtime-home locator
    rule: NEXUS_HOME, NEXUS_RUNTIME_CONFIG, the checkout's nexus.toml).
    Returns the CLI result mapping: ``success`` plus a ``message`` on success,
    or an ``error`` naming every problem and its remediation on failure.
    """

    if command not in ("lock", "verify", "plan", "fetch"):
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
        if command == "lock":
            specs = production_artifact_specs(settings)
            manifest = build_manifest(specs, lock_path)
            write_manifest(manifest, lock_path)
            return {
                "success": True,
                "lock_file": str(lock_path),
                "message": _lock_summary(manifest, lock_path),
            }
        check = verify_artifacts(settings, hash_files=command == "verify")
        if command == "plan":
            return _plan_artifacts(check)
        if command == "fetch":
            return _fetch_artifacts(check)
        specs, report = check.specs, check.report
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
    lines.extend(_mismatch_lines(report))
    return {
        "success": False,
        "lock_file": str(lock_path),
        "problems": report.problems,
        "error": "\n".join(lines),
    }
