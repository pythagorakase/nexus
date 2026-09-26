"""Read-only, checksummed dry run of moving runtime data into a home (#820).

``plan_home_move`` inventories every file the checkout holds for the runtime:
the active configuration, the state directory (pidfiles, captured logs,
player preferences, local-model state, the usage ledger), the cache and
backup directories, uploaded images, and the model directories nexus.toml
references. For each it reports the size, SHA-256, current path and the path
the file would take in the target home, plus the nexus.toml keys a move would
have to rewrite. It opens files for reading only and creates nothing; moving
anything is a later #820 slice.
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


def _status(current: Path, proposed: Path) -> Status:
    """Classify a move of ``current`` to ``proposed``."""
    if current == proposed:
        return "in-place"
    if proposed.exists() or proposed.is_symlink():
        return "conflict"
    return "move"


def _entry(category: str, current: Path, proposed: Path) -> PlanEntry:
    """Describe one existing path: its checksum, or its link target."""
    if current.is_symlink():
        return PlanEntry(
            category=category,
            status=_status(current, proposed),
            kind="symlink",
            current=current,
            proposed=proposed,
            size=None,
            sha256=None,
            link_target=os.readlink(current),
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
        status=_status(current, proposed),
        kind="file",
        current=current,
        proposed=proposed,
        size=size,
        sha256=sha256,
        link_target=None,
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
    references.extend(
        (
            f"memnon.retrieval.cross_encoder_reranking.candidates.{name}.local_path",
            candidate.local_path,
        )
        for name, candidate in sorted(reranking.candidates.items())
    )
    return references


def _inside(path: Path, root: Path) -> bool:
    """Whether ``path`` lies under the resolved ``root``.

    The parent is resolved and the last component is not, so a symlinked
    model directory counts as where the link lives, not where it points.
    """
    return (Path(os.path.realpath(path.parent)) / path.name).is_relative_to(root)


def _target_root(target: Union[str, Path, None], active: HomeLocation) -> Path:
    """Resolve the target home: an explicit path, else NEXUS_HOME."""
    if target is not None:
        return Path(target).expanduser().resolve()
    if active.locator == "NEXUS_HOME":
        return active.root
    raise HomePlanError(
        f"No target home: pass --to DIR or set {HOME_ENV} to the home to plan."
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
        HomePlanError: no target, a target that is, sits inside or contains
            the checkout, two model directories that would land on one path,
            or a file that is not regular, a directory or a symlink.
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
    if target_root.exists() and not target_root.is_dir():
        raise HomePlanError(f"Target home {target_root} exists and is not a directory.")
    source = build_runtime_home(
        HomeLocation(checkout, active.config_path, "checkout"), settings
    )
    target_home = build_runtime_home(
        HomeLocation(
            target_root, (target_root / CONFIG_FILENAME).resolve(), "NEXUS_HOME"
        ),
        settings,
    )

    claimed: Set[Path] = set()
    entries: List[PlanEntry] = []

    claimed.add(source.config_path)
    entries.append(_entry("config", source.config_path, target_home.config_path))

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
    for category, current_root, proposed_root in roots:
        for path in _tree(current_root):
            if path in claimed:
                continue
            claimed.add(path)
            proposed = proposed_root / path.relative_to(current_root)
            entries.append(_entry(category, path, proposed))

    rewrites: List[ConfigRewrite] = []
    keys_by_path: Dict[Path, List[Tuple[str, str]]] = {}
    for key, configured in _model_references(settings):
        current = anchor_path(checkout, configured)
        keys_by_path.setdefault(current, []).append((key, configured))
    landing: Dict[Path, Path] = {}
    for current in sorted(keys_by_path):
        # A model outside the checkout (an external drive, a shared cache) is
        # already separate from it and stays where it is configured.
        if not _inside(current, checkout):
            proposed_root = current
        else:
            proposed_root = target_home.models_dir / current.name
            if proposed_root in landing:
                raise HomePlanError(
                    f"Models {landing[proposed_root]} and {current} would both "
                    f"move to {proposed_root}; give one of them a distinct "
                    "directory name."
                )
            landing[proposed_root] = current
        if current.exists() or current.is_symlink():
            for path in _tree(current):
                if path in claimed:
                    continue
                claimed.add(path)
                proposed = (
                    proposed_root
                    if path == current
                    else proposed_root / path.relative_to(current)
                )
                entries.append(_entry(MODELS_CATEGORY, path, proposed))
        else:
            # Nothing to move, so no key to rewrite; report the gap.
            entries.append(
                PlanEntry(
                    category=MODELS_CATEGORY,
                    status="missing",
                    kind="missing",
                    current=current,
                    proposed=proposed_root,
                    size=None,
                    sha256=None,
                    link_target=None,
                )
            )
            continue
        for key, configured in keys_by_path[current]:
            if anchor_path(target_home.root, configured) != proposed_root:
                rewrites.append(ConfigRewrite(key, configured, str(proposed_root)))

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
