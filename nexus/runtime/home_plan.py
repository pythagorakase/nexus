"""Read-only, checksummed dry run of moving runtime data into a home (#820).

``plan_home_move`` inventories every file the checkout holds for the runtime:
the active configuration, the state directory (pidfiles, captured logs,
player preferences, local-model state, the usage ledger), the cache and
backup directories, uploaded images, and the model directories nexus.toml
references. For each it reports the size, SHA-256, current path and the path
the file would take in the target home, plus the nexus.toml keys a move would
have to rewrite. It opens files for reading only and creates nothing; moving
anything is a later #820 slice.

The plan's contract:

- Symlinks are reported with their target and never followed, in the checkout
  or in the target. The active configuration is inventoried as the locator
  rule selected it, so a symlinked ``nexus.toml`` is reported as the link.
- Every entry is ``move``, ``conflict``, ``in-place`` or ``missing``. A move
  conflicts when its destination exists, or when a path on the way to it
  inside the target is a file or a symlink; ``conflict_with`` names the
  blocking path.
- Every inventoried path has one owner, so each rewritten key names a
  directory that receives exactly that model's files. Model directories that
  nest or name one directory (directly or through symlinks), a model
  directory that is or contains the checkout or overlaps the active
  configuration or a runtime directory, and two models that would share a
  destination are refused before anything is checksummed.
- A target that is, contains or sits inside the checkout, or that is or sits
  beneath an existing non-directory, is refused.
- The order is a pure function of the file tree, so two runs over one tree
  print identical output.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
from typing import Dict, Iterator, List, Literal, Optional, Set, Tuple, Union

from nexus.config.loader import load_settings
from nexus.config.settings_models import Settings
from nexus.runtime.contract import HOME_ENV
from nexus.runtime.home import (
    CONFIG_FILENAME,
    UPLOAD_SUBDIRS,
    HomeLocation,
    Locator,
    RuntimeHome,
    anchor_path,
    build_runtime_home,
    locate_runtime_home,
    repo_root,
    resolve_parent,
)

# Report order. Within one file tree the deepest directory claims a file
# (the usage ledger sits inside the state directory); equal depths fall back
# to this order, so state claims the captured logs that live beside it.
CATEGORY_ORDER = ("config", "usage", "state", "logs", "cache", "backups", "uploads")
MODELS_CATEGORY = "models"

_READ_CHUNK_BYTES = 1024 * 1024

Status = Literal["move", "in-place", "conflict", "missing"]
Kind = Literal["file", "symlink", "missing"]


class HomePlanError(ValueError):
    """The requested plan is ill-posed or the inventory hit an unplannable file."""


@dataclass(frozen=True)
class PlanEntry:
    """One inventoried path and where a move into the target home puts it."""

    category: str
    status: Status
    kind: Kind
    current: Path
    proposed: Path
    size: Optional[int]
    sha256: Optional[str]
    link_target: Optional[str]
    conflict_with: Optional[Path]

    def as_dict(self) -> Dict[str, Union[str, int, None]]:
        """Return the entry with string paths for JSON output."""
        return {
            "category": self.category,
            "status": self.status,
            "kind": self.kind,
            "current": str(self.current),
            "proposed": str(self.proposed),
            "size": self.size,
            "sha256": self.sha256,
            "link_target": self.link_target,
            "conflict_with": (
                None if self.conflict_with is None else str(self.conflict_with)
            ),
        }


@dataclass(frozen=True)
class ConfigRewrite:
    """A nexus.toml key whose value must change when its files move."""

    key: str
    current: str
    proposed: str

    def as_dict(self) -> Dict[str, str]:
        """Return the rewrite for JSON output."""
        return {"key": self.key, "current": self.current, "proposed": self.proposed}


@dataclass(frozen=True)
class HomePlan:
    """The dry-run inventory of a move from the checkout into a target home."""

    config_locator: Locator
    source: RuntimeHome
    target: RuntimeHome
    entries: Tuple[PlanEntry, ...]
    rewrites: Tuple[ConfigRewrite, ...]

    def status_counts(self) -> Dict[str, int]:
        """Count entries by status, in sorted status order."""
        counts: Dict[str, int] = {}
        for entry in self.entries:
            counts[entry.status] = counts.get(entry.status, 0) + 1
        return dict(sorted(counts.items()))

    def total_bytes(self) -> int:
        """Sum the checksummed bytes of every inventoried file."""
        return sum(entry.size or 0 for entry in self.entries)

    def totals(self) -> Dict[str, object]:
        """Count entries and checksummed bytes, overall and by status."""
        return {
            "entries": len(self.entries),
            "bytes": self.total_bytes(),
            "statuses": self.status_counts(),
        }

    def as_dict(self) -> Dict[str, object]:
        """Return the whole plan for JSON output."""
        return {
            "config_locator": self.config_locator,
            "source": self.source.as_dict(),
            "target": self.target.as_dict(),
            "entries": [entry.as_dict() for entry in self.entries],
            "rewrites": [rewrite.as_dict() for rewrite in self.rewrites],
            "totals": self.totals(),
        }

    def render(self) -> List[str]:
        """Return the plan as human-readable lines."""
        lines = [
            f"source  {self.source.root} (config {self.source.config_path}, "
            f"via {self.config_locator})",
            f"target  {self.target.root}",
        ]
        width = max((len(entry.category) for entry in self.entries), default=0)
        for entry in self.entries:
            detail = (
                f"-> {entry.link_target}"
                if entry.kind == "symlink"
                else (
                    f"{entry.size} {entry.sha256}"
                    if entry.kind == "file"
                    else "(configured, not on disk)"
                )
            )
            if entry.conflict_with not in (None, entry.proposed):
                detail += f"  (blocked by {entry.conflict_with})"
            lines.append(
                f"{entry.status:<9} {entry.category:<{width}}  {entry.current} "
                f"=> {entry.proposed}  {detail}"
            )
        for rewrite in self.rewrites:
            lines.append(
                f"rewrite   {rewrite.key}: {rewrite.current} => {rewrite.proposed}"
            )
        summary = ", ".join(
            f"{count} {status}" for status, count in self.status_counts().items()
        )
        lines.append(
            f"{len(self.entries)} entries, {self.total_bytes()} bytes"
            + (f" ({summary})" if summary else "")
            + ". Dry run: nothing was moved."
        )
        return lines


def _checksum(path: Path) -> Tuple[int, str]:
    """Return the byte count and SHA-256 of one regular file's content."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_READ_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _blocker(proposed: Path, target_root: Path) -> Optional[Path]:
    """Return the existing path that keeps ``proposed`` from being created.

    Walks down from the target home without following links: the first path
    on the way that exists and is not a directory (a file, or a symlink of
    any kind) blocks the destination, and so does ``proposed`` itself if it
    exists. Returns None when the destination is free.
    """
    path = target_root
    for part in proposed.relative_to(target_root).parts[:-1]:
        path = path / part
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(mode):
            return path
    return proposed if os.path.lexists(proposed) else None


def _status(
    current: Path, proposed: Path, target_root: Path
) -> Tuple[Status, Optional[Path]]:
    """Classify a move of ``current`` to ``proposed`` and name any blocker."""
    if current == proposed:
        return "in-place", None
    blocker = _blocker(proposed, target_root)
    if blocker is None:
        return "move", None
    return "conflict", blocker


def _entry(
    category: str, current: Path, proposed: Path, target_root: Path
) -> PlanEntry:
    """Describe one existing path: its checksum, or its link target."""
    status, conflict_with = _status(current, proposed, target_root)
    if current.is_symlink():
        return PlanEntry(
            category=category,
            status=status,
            kind="symlink",
            current=current,
            proposed=proposed,
            size=None,
            sha256=None,
            link_target=os.readlink(current),
            conflict_with=conflict_with,
        )
    mode = current.stat().st_mode
    if not stat.S_ISREG(mode):
        raise HomePlanError(
            f"{current} is neither a regular file, a directory nor a symlink; "
            "the runtime home plan cannot account for it."
        )
    size, sha256 = _checksum(current)
    return PlanEntry(
        category=category,
        status=status,
        kind="file",
        current=current,
        proposed=proposed,
        size=size,
        sha256=sha256,
        link_target=None,
        conflict_with=conflict_with,
    )


def _tree(root: Path) -> Iterator[Path]:
    """Yield every non-directory path under ``root`` in sorted order.

    Symlinks, including symlinked directories, are yielded and never
    followed. A missing root yields nothing.
    """
    if root.is_symlink() or root.is_file():
        yield root
        return
    if not root.is_dir():
        return
    for directory, subdirectories, files in os.walk(root):
        subdirectories.sort()
        base = Path(directory)
        linked = [name for name in subdirectories if (base / name).is_symlink()]
        for name in sorted(files + linked):
            yield base / name


def _model_references(settings: Settings) -> List[Tuple[str, str]]:
    """Return (nexus.toml key, configured path) for every referenced model."""
    references = [
        (f"memnon.models.{name}.local_path", model.local_path)
        for name, model in sorted(settings.memnon.models.items())
    ]
    reranking = settings.memnon.retrieval.cross_encoder_reranking
    references.append(
        ("memnon.retrieval.cross_encoder_reranking.model_path", reranking.model_path)
    )
    return references


def _inside(path: Path, root: Path) -> bool:
    """Whether ``path`` lies under the resolved ``root``.

    The parent is resolved and the last component is not, so a symlinked
    model directory counts as where the link lives, not where it points.
    """
    return resolve_parent(path).is_relative_to(root)


def _aliases(path: Path) -> Tuple[Path, Path]:
    """Return ``path`` as the inventory walks it and as it fully resolves."""
    return resolve_parent(path), Path(os.path.realpath(path))


def _overlap(first: Path, second: Path) -> bool:
    """Whether two paths are one path or nest, directly or through symlinks."""
    return any(
        one.is_relative_to(other) or other.is_relative_to(one)
        for one, other in zip(_aliases(first), _aliases(second))
    )


@dataclass(frozen=True)
class _ModelRoot:
    """One configured model path, the keys naming it, and its destination."""

    current: Path
    proposed: Path
    keys: Tuple[Tuple[str, str], ...]

    @property
    def moves(self) -> bool:
        """Whether the plan moves this model (it lies inside the checkout)."""
        return self.proposed != self.current

    def label(self) -> str:
        """Name the model by its keys and configured path for errors."""
        return f"{', '.join(key for key, _ in self.keys)} ({self.current})"


def _plan_model_roots(
    settings: Settings,
    checkout: Path,
    models_dir: Path,
    owners: List[Tuple[str, Path]],
) -> List[_ModelRoot]:
    """Map each configured model path to its destination, one owner per path.

    A model inside the checkout moves to ``<models_dir>/<name>``; one outside
    it (an external drive, a shared cache) is already separate and stays.
    ``owners`` are the active configuration and the runtime directories the
    plan inventories under their own layout entries.

    Raises:
        HomePlanError: two model paths nest or name one directory, a model
            path is or contains the checkout or overlaps an owner, or two
            models would share a destination.
    """
    keys_by_path: Dict[Path, List[Tuple[str, str]]] = {}
    for key, configured in _model_references(settings):
        keys_by_path.setdefault(anchor_path(checkout, configured), []).append(
            (key, configured)
        )
    roots = [
        _ModelRoot(
            current=current,
            proposed=(
                models_dir / current.name if _inside(current, checkout) else current
            ),
            keys=tuple(keys),
        )
        for current, keys in sorted(keys_by_path.items())
    ]
    for index, root in enumerate(roots):
        if any(checkout.is_relative_to(alias) for alias in _aliases(root.current)):
            raise HomePlanError(
                f"Model path {root.label()} is or contains the checkout "
                f"{checkout}; point it at a directory of its own."
            )
        for owner, path in owners:
            if _overlap(root.current, path):
                raise HomePlanError(
                    f"Model path {root.label()} overlaps {owner} {path}; a "
                    "path cannot be both a model and runtime data, because "
                    "each moves under its own layout entry. Point the key at "
                    "a directory of its own."
                )
        for other in roots[index + 1 :]:
            if _overlap(root.current, other.current):
                raise HomePlanError(
                    f"Model paths {root.label()} and {other.label()} overlap: "
                    "they name one directory or one holds the other, so a "
                    "move would give their files one destination and their "
                    "keys two. Point each key at a directory of its own."
                )
            if root.moves and other.moves and root.proposed == other.proposed:
                raise HomePlanError(
                    f"Models {root.current} and {other.current} would both "
                    f"move to {root.proposed}; give one of them a distinct "
                    "directory name."
                )
            for moving, staying in ((root, other), (other, root)):
                if (
                    moving.moves
                    and not staying.moves
                    and _overlap(moving.proposed, staying.current)
                ):
                    raise HomePlanError(
                        f"Model {moving.label()} would move to "
                        f"{moving.proposed}, which overlaps model "
                        f"{staying.label()} that stays in place; give each "
                        "model a directory of its own."
                    )
    return roots


def _target_root(target: Union[str, Path, None], active: HomeLocation) -> Path:
    """Resolve the target home: an explicit path, else NEXUS_HOME."""
    if target is not None:
        return Path(target).expanduser().resolve()
    if active.locator == "NEXUS_HOME":
        return active.root
    raise HomePlanError(
        f"No target home: pass --to DIR or set {HOME_ENV} to the home to plan."
    )


def _require_directory(target_root: Path) -> None:
    """Refuse a target home that an existing non-directory blocks.

    ``target_root`` is resolved, so its nearest existing path is not a link.
    """
    nearest = target_root
    while not os.path.lexists(nearest):
        nearest = nearest.parent
    if not nearest.is_dir():
        raise HomePlanError(
            f"Target home {target_root} is blocked: {nearest} exists and is not "
            "a directory."
        )


def plan_home_move(
    target: Union[str, Path, None] = None, *, checkout: Optional[Path] = None
) -> HomePlan:
    """Inventory the checkout's runtime data against a target home layout.

    The source is the checkout laid out with the active configuration; the
    target is the same configuration laid out at ``target`` (default:
    ``NEXUS_HOME``). Relative state and usage directories follow the home;
    absolute ones stay where they are and are reported ``in-place``. A model
    directory inside the checkout moves to ``<home>/models/<name>``; one
    configured outside the checkout stays where it is. ``checkout`` names the
    checkout to inventory (default: the one this package runs from).

    Raises:
        HomePlanError: no target; a target that is, sits inside or contains
            the checkout, or that an existing non-directory blocks; model
            paths that overlap each other, the checkout, the active
            configuration or a runtime directory, or that would share a
            destination; or a file that is not regular, a directory or a
            symlink.
        RuntimeHomeError: the locators disagree (see nexus/runtime/home.py).
    """
    active = locate_runtime_home()
    settings = load_settings(active.config_path)
    checkout = (checkout or repo_root()).resolve()
    target_root = _target_root(target, active)
    if target_root.is_relative_to(checkout):
        raise HomePlanError(
            f"Target home {target_root} is the checkout or inside it; a runtime "
            "home must live outside the checkout to separate them."
        )
    if checkout.is_relative_to(target_root):
        raise HomePlanError(
            f"Target home {target_root} contains the checkout {checkout}; a "
            "runtime home must live beside the checkout to separate them."
        )
    _require_directory(target_root)
    # The config entry is the path the locator selected, not its resolution:
    # a symlinked nexus.toml is inventoried as the link.
    source_config = active.selected_config_path
    target_config = target_root / CONFIG_FILENAME
    source = build_runtime_home(
        HomeLocation(checkout, active.config_path, "checkout", source_config),
        settings,
    )
    target_home = build_runtime_home(
        HomeLocation(target_root, target_config.resolve(), "NEXUS_HOME", target_config),
        settings,
    )

    roots = [
        ("usage", source.usage_dir, target_home.usage_dir),
        ("state", source.state_dir, target_home.state_dir),
        ("logs", source.logs_dir, target_home.logs_dir),
        ("cache", source.cache_dir, target_home.cache_dir),
        ("backups", source.backups_dir, target_home.backups_dir),
        *(
            ("uploads", source.uploads_dir / name, target_home.uploads_dir / name)
            for name in UPLOAD_SUBDIRS
        ),
    ]
    roots.sort(key=lambda root: (-len(root[1].parts), CATEGORY_ORDER.index(root[0])))
    owners = [("the active configuration", source_config)] + [
        (f"the {category} directory", current_root)
        for category, current_root, _ in roots
    ]
    # Every model path is checked before anything is checksummed.
    model_roots = _plan_model_roots(settings, checkout, target_home.models_dir, owners)

    claimed: Set[Path] = {source_config}
    entries = [_entry("config", source_config, target_config, target_root)]
    for category, current_root, proposed_root in roots:
        for path in _tree(current_root):
            if path in claimed:
                continue
            claimed.add(path)
            proposed = proposed_root / path.relative_to(current_root)
            entries.append(_entry(category, path, proposed, target_root))

    rewrites: List[ConfigRewrite] = []
    for model in model_roots:
        if not (model.current.exists() or model.current.is_symlink()):
            # Nothing to move, so no key to rewrite; report the gap.
            entries.append(
                PlanEntry(
                    category=MODELS_CATEGORY,
                    status="missing",
                    kind="missing",
                    current=model.current,
                    proposed=model.proposed,
                    size=None,
                    sha256=None,
                    link_target=None,
                    conflict_with=None,
                )
            )
            continue
        for path in _tree(model.current):
            if path in claimed:
                raise HomePlanError(
                    f"{path} lies under two inventoried paths; the overlap "
                    "checks should have refused this configuration."
                )
            claimed.add(path)
            proposed = (
                model.proposed
                if path == model.current
                else model.proposed / path.relative_to(model.current)
            )
            entries.append(_entry(MODELS_CATEGORY, path, proposed, target_root))
        for key, configured in model.keys:
            if anchor_path(target_home.root, configured) != model.proposed:
                rewrites.append(ConfigRewrite(key, configured, str(model.proposed)))

    order = CATEGORY_ORDER + (MODELS_CATEGORY,)
    entries.sort(key=lambda entry: (order.index(entry.category), str(entry.current)))
    rewrites.sort(key=lambda rewrite: rewrite.key)
    return HomePlan(
        config_locator=active.locator,
        source=source,
        target=target_home,
        entries=tuple(entries),
        rewrites=tuple(rewrites),
    )
