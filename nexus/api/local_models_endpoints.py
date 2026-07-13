"""HTTP endpoints for discovering and managing local GGUF models."""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
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


class PathRequest(BaseModel):
    """A filesystem path supplied by a local-model action."""

    model_config = ConfigDict(extra="forbid")

    path: str


class DownloadRequest(BaseModel):
    """A curated catalog family and quantization selection."""

    model_config = ConfigDict(extra="forbid")

    family: str
    quant: str


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
    return local_inference.split_shard(path)


def _is_activatable_shard(path: Path) -> bool:
    """Accept single-file GGUFs and only the first shard of split sets."""
    split = _split_shard(path)
    return split is None or split[1] == 1


def _model_size(path: Path, roots: tuple[Path, ...]) -> int:
    """Return one file's size or the aggregate size of its split set."""
    return sum(shard.stat().st_size for shard in local_inference.shard_set(path, roots))


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


def _system_ram_gb() -> float:
    """Total physical memory in GiB — the unit catalog min_ram_gb is quoted in.

    Live process telemetry cannot drive the client's memory meter: with
    ``-ngl 999`` llama-server's weights are mmap'd clean pages wired into
    Metal buffers, invisible to both RSS and phys_footprint (measured: a
    21.8 GB model reports 2 GB RSS). The client instead compares static
    catalog sizes against this total.
    """
    return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)


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
            # Resolved so the client's models_dir/subdir/filename string join
            # equals installed[].path, which is Path.resolve()'d — a symlinked
            # models_dir would otherwise break the catalog↔installed join.
            "models_dir": str(Path(settings.models_dir).expanduser().resolve()),
            "system_ram_gb": _system_ram_gb(),
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


def _catalog_files(filename: str) -> list[str]:
    """Expand a catalog filename to its complete ordered split set."""
    split = _split_shard(Path(filename))
    if split is None:
        return [filename]
    stem, _, total = split
    return [f"{stem}-{part:05d}-of-{total:05d}.gguf" for part in range(1, total + 1)]


@router.post("/download")
def download(request: DownloadRequest) -> dict[str, Any]:
    """Start downloading one curated catalog quantization."""
    settings = get_local_models_settings()
    entry = next(
        (
            item
            for item in settings.catalog
            if item.family == request.family and item.quant == request.quant
        ),
        None,
    )
    if entry is None:
        raise HTTPException(
            status_code=404, detail="Local model catalog entry not found"
        )

    local_dir = (Path(settings.models_dir) / entry.subdir).resolve()
    if not _is_within(local_dir, _allowed_roots()):
        raise HTTPException(
            status_code=400, detail="Catalog model directory is outside allowed roots"
        )
    files = _catalog_files(entry.filename)
    targets = [local_dir / filename for filename in files]
    # Catalog size_gb values are decimal gigabytes (matching HF's listed
    # sizes); multiplying by 1024**3 overstated totals ~7% and capped a
    # completed download's reported progress at ~0.93 (verified live).
    total_bytes = round(entry.size_gb * 1000**3)
    if (
        all(target.is_file() for target in targets)
        and inspect_gguf(str(targets[0])).valid
    ):
        return {
            "status": "already_installed",
            "family": entry.family,
            "quant": entry.quant,
            "files": files,
            "local_dir": str(local_dir),
            "total_bytes": total_bytes,
        }
    try:
        local_inference.start_download(
            family=entry.family,
            quant=entry.quant,
            repo_id=entry.hf_repo,
            local_dir=str(local_dir),
            files=files,
            total_bytes=total_bytes,
        )
    except local_inference.LocalInferenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    current = local_inference.download_status()
    if current is None:
        raise local_inference.LocalInferenceError(
            "Download worker state disappeared immediately after start"
        )
    return {"status": "started", **current}


@router.get("/download")
def download_status() -> dict[str, Any]:
    """Return the current detached download state, or idle."""
    return local_inference.download_status() or {"state": "idle"}


@router.post("/download/cancel")
def cancel_download() -> dict[str, Any]:
    """Cancel the current detached local-model download."""
    return local_inference.cancel_download()


@router.post("/delete")
def delete_model(request: PathRequest) -> dict[str, Any]:
    """Delete one verified inactive GGUF model or its full shard set."""
    candidate, _ = _verified_path(request.path, status_code=404)
    try:
        result = local_inference.delete_model(str(candidate))
    except local_inference.LocalInferenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "deleted", **result}


def _allowed_roots() -> tuple[Path, Path]:
    return local_inference._allowed_roots()


def _is_within(path: Path, roots: tuple[Path, ...]) -> bool:
    return local_inference._is_within(path, roots)


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
