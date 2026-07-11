"""HTTP endpoints for discovering and managing local GGUF models."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import re
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from nexus.api import local_inference
from nexus.config import get_local_models_settings
from nexus.util.gguf_inspect import GgufInfo, inspect_gguf

router = APIRouter(prefix="/api/local-models", tags=["local-models"])

_inspection_cache: dict[tuple[str, int, int], GgufInfo] = {}
_inspection_cache_lock = Lock()
_GENERIC_GGUF_ERROR = "No accessible GGUF model at the requested path."
_SPLIT_GGUF_PATTERN = re.compile(
    r"^(?P<stem>.+)-(?P<part>\d{5})-of-(?P<total>\d{5})\.gguf$",
    re.IGNORECASE,
)


class PathRequest(BaseModel):
    """A filesystem path supplied by a local-model action."""

    model_config = ConfigDict(extra="forbid")

    path: str


def _cached_inspect(path: Path) -> GgufInfo:
    """Inspect once per path/mtime/size tuple; tolerate per-file failures."""
    try:
        stat = path.stat()
    except OSError as exc:
        return GgufInfo(reason=f"Cannot stat GGUF file: {exc}")
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _inspection_cache_lock:
        cached = _inspection_cache.get(key)
    if cached is not None:
        return cached
    try:
        info = inspect_gguf(str(path))
    except Exception as exc:  # one damaged file must not break the status scan
        info = GgufInfo(reason=f"GGUF inspection failed: {exc}")
    with _inspection_cache_lock:
        _inspection_cache[key] = info
    return info


def _verified_path(raw_path: str, status_code: int) -> tuple[Path, GgufInfo]:
    """Resolve and verify an allowed GGUF without exposing filesystem details."""
    try:
        candidate = Path(raw_path).expanduser().resolve()
        if not _is_within(candidate, _allowed_roots()):
            raise HTTPException(status_code=status_code, detail=_GENERIC_GGUF_ERROR)
        if not candidate.is_file() or not _is_activatable_shard(candidate):
            raise HTTPException(status_code=status_code, detail=_GENERIC_GGUF_ERROR)
        info = inspect_gguf(str(candidate))
        if not info.valid:
            raise HTTPException(status_code=status_code, detail=_GENERIC_GGUF_ERROR)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status_code, detail=_GENERIC_GGUF_ERROR
        ) from None
    return candidate, info


def _split_shard(path: Path) -> tuple[str, int, int] | None:
    """Return split stem, part, and total for llama.cpp split filenames."""
    match = _SPLIT_GGUF_PATTERN.match(path.name)
    if match is None:
        return None
    return match.group("stem"), int(match.group("part")), int(match.group("total"))


def _is_activatable_shard(path: Path) -> bool:
    """Accept single-file GGUFs and only the first shard of split sets."""
    split = _split_shard(path)
    return split is None or split[1] == 1


def _model_size(path: Path, roots: tuple[Path, ...]) -> int:
    """Return one file's size or the aggregate size of its split set."""
    split = _split_shard(path)
    if split is None:
        return path.stat().st_size
    stem, _, total = split
    size = 0
    for sibling in path.parent.glob(f"{stem}-*-of-{total:05d}.gguf"):
        resolved = sibling.resolve()
        sibling_split = _split_shard(resolved)
        if (
            sibling_split is not None
            and sibling_split[0] == stem
            and sibling_split[2] == total
            and _is_within(resolved, roots)
            and resolved.is_file()
        ):
            size += resolved.stat().st_size
    return size


def _installed_models(active_path: str | None) -> list[dict[str, Any]]:
    settings = get_local_models_settings()
    root = Path(settings.models_dir)
    roots = _allowed_roots()
    candidates = list(root.rglob("*.gguf")) if root.is_dir() else []
    for raw_path in local_inference.registered_paths():
        candidates.append(Path(raw_path))

    installed: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if (
            resolved in seen
            or not _is_within(resolved, roots)
            or not _is_activatable_shard(resolved)
        ):
            continue
        seen.add(resolved)
        info = _cached_inspect(resolved)
        try:
            size_bytes = _model_size(resolved, roots)
        except OSError:
            size_bytes = 0
        installed.append(
            {
                "path": str(resolved),
                "filename": resolved.name,
                "arch": info.architecture,
                "quant": info.quantization,
                "size_bytes": size_bytes,
                "verified": info.valid,
                "active": str(resolved) == active_path,
            }
        )
    return sorted(installed, key=lambda item: item["path"].lower())


@router.get("/status")
def status() -> dict[str, Any]:
    """Return configured catalog, installed GGUFs, and managed process state."""
    settings = get_local_models_settings()
    try:
        current = local_inference.active()
        active_payload = (
            {
                "gguf_path": current["gguf_path"],
                "ready": current["ready"],
                "failed": current.get("failed", False),
                **({"error": current["error"]} if current.get("error") else {}),
            }
            if current
            else None
        )
        return {
            "models_dir": settings.models_dir,
            "catalog": [entry.model_dump() for entry in settings.catalog],
            "installed": _installed_models(
                current["gguf_path"]
                if current is not None and current.get("failed") is not True
                else None
            ),
            "active": active_payload,
        }
    except local_inference.LocalInferenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/activate")
def activate(request: PathRequest) -> dict[str, Any]:
    """Start loading one verified GGUF in the detached local server."""
    candidate, _ = _verified_path(request.path, status_code=404)
    try:
        current = local_inference.activate(str(candidate))
    except local_inference.LocalInferenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "status": (
            "failed"
            if current.get("failed")
            else "ready" if current["ready"] else "loading"
        ),
        "active": {
            "gguf_path": current["gguf_path"],
            "ready": current["ready"],
            "failed": current.get("failed", False),
        },
    }


@router.post("/deactivate")
def deactivate() -> dict[str, Any]:
    """Stop the manager-owned local server process group."""
    try:
        result = local_inference.deactivate()
    except local_inference.LocalInferenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"active": None, **result}


def _allowed_roots() -> tuple[Path, Path]:
    return (
        Path(get_local_models_settings().models_dir).resolve(),
        Path.home().resolve(),
    )


def _is_within(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


@router.get("/browse")
def browse(directory: str = Query(..., alias="dir")) -> dict[str, Any]:
    """List one allowed directory for the local GGUF file picker."""
    raw_path = Path(directory).expanduser()
    if not raw_path.is_absolute():
        raise HTTPException(status_code=400, detail="Browse directory must be absolute")
    candidate = raw_path.resolve()
    roots = _allowed_roots()
    if not _is_within(candidate, roots):
        raise HTTPException(
            status_code=400, detail="Browse directory is outside allowed roots"
        )
    if not candidate.is_dir():
        raise HTTPException(status_code=400, detail="Browse path is not a directory")

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(candidate.iterdir(), key=lambda item: item.name.lower())
        for child in children:
            resolved = child.resolve()
            if not _is_within(resolved, roots):
                continue
            is_dir = resolved.is_dir()
            is_gguf = resolved.is_file() and resolved.suffix.lower() == ".gguf"
            if not is_dir and not is_gguf:
                continue
            entries.append(
                {
                    "name": child.name,
                    "path": str(resolved),
                    "is_dir": is_dir,
                    "is_gguf": is_gguf,
                    "size_bytes": 0 if is_dir else resolved.stat().st_size,
                }
            )
    except OSError as exc:
        raise HTTPException(
            status_code=400, detail=f"Cannot browse directory: {exc}"
        ) from exc

    parent_path = candidate.parent.resolve()
    parent = str(parent_path) if _is_within(parent_path, roots) else None
    return {"dir": str(candidate), "parent": parent, "entries": entries}


@router.post("/register")
def register(request: PathRequest) -> dict[str, Any]:
    """Verify and persist an external GGUF path."""
    candidate, info = _verified_path(request.path, status_code=400)
    try:
        local_inference.register_path(str(candidate))
    except local_inference.LocalInferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(candidate), "verified": True, "info": asdict(info)}
