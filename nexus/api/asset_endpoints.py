"""Character portrait and place image endpoints, ported from Express.

Image files live under ``ui/client/public/`` (``character_portraits/<id>/``
and ``place_images/<id>/``) so the Vite dev server can serve them straight
from its public dir; the FastAPI gateway mounts the same directories as
static routes for production parity (see ``nexus/api/static_ui.py``).
Database rows live in ``assets.character_images`` / ``assets.place_images``.

Wire-format contract: identical to the retired Express layer — camelCase
image rows, ``{"success": true, ...}`` envelopes, 400 for invalid file
types, 413 for oversized files.

Upload limits come from nexus.toml ``[api.uploads]``.
"""

from __future__ import annotations

import functools
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, File, HTTPException, UploadFile

from nexus.api.db_pool import get_connection
from nexus.api.reader_endpoints import resolve_dbname

logger = logging.getLogger("nexus.api.asset_endpoints")

router = APIRouter(tags=["assets"])

# Runtime upload root: ui/client/public (repo-layout-derived, same files the
# Vite dev server mirrors at /).
REPO_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = REPO_ROOT / "ui" / "client" / "public"

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


@functools.lru_cache(maxsize=None)
def get_upload_limits() -> Tuple[int, int]:
    """Read (max_file_size_bytes, max_files_per_request) from nexus.toml."""
    from nexus.config import load_settings

    settings = load_settings()
    if settings.api is None or settings.api.uploads is None:
        raise RuntimeError(
            "nexus.toml is missing the [api.uploads] section; "
            "max_file_size_mb and max_files_per_request are required"
        )
    uploads = settings.api.uploads
    return uploads.max_file_size_mb * 1024 * 1024, uploads.max_files_per_request


def _image_row_payload(row: Dict[str, Any], owner_key: str) -> Dict[str, Any]:
    """Map an assets image row to the legacy camelCase wire shape."""
    owner_column = "character_id" if owner_key == "characterId" else "place_id"
    return {
        "id": row["id"],
        owner_key: row[owner_column],
        "filePath": row["file_path"],
        "isMain": row["is_main"],
        "displayOrder": row["display_order"],
        "uploadedAt": row["uploaded_at"],
    }


def _sanitize_filename(original: str) -> str:
    """Build a safe stored filename: timestamp prefix + sanitized base + ext."""
    ext = Path(original).suffix.lower()
    base = Path(original).stem
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", base)[:50]
    return f"{int(time.time() * 1000)}_{sanitized}{ext}"


def _validate_upload(upload: UploadFile, max_bytes: int) -> None:
    """Reject disallowed types (400) and oversized files (413)."""
    ext = Path(upload.filename or "").suffix.lower()
    mime = (upload.content_type or "").lower()
    if mime not in ALLOWED_MIME_TYPES or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid file type. Only PNG and JPEG images are allowed. "
                f"Got: {upload.content_type}"
            ),
        )
    if upload.size is not None and upload.size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {max_bytes // (1024 * 1024)}MB.",
        )


def _fetch_images(
    dbname: str, table: str, owner_column: str, owner_id: int
) -> List[Dict[str, Any]]:
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, {owner_column}, file_path, is_main, display_order,
                       uploaded_at
                FROM {table}
                WHERE {owner_column} = %s
                ORDER BY display_order
                """,
                (owner_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def _insert_image(
    dbname: str,
    table: str,
    owner_column: str,
    owner_id: int,
    file_path: str,
    is_main: int,
    display_order: int,
) -> Dict[str, Any]:
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {table} ({owner_column}, file_path, is_main,
                                     display_order)
                VALUES (%s, %s, %s, %s)
                RETURNING id, {owner_column}, file_path, is_main,
                          display_order, uploaded_at
                """,
                (owner_id, file_path, is_main, display_order),
            )
            return dict(cur.fetchone())


def _set_main_image(
    dbname: str, table: str, owner_column: str, owner_id: int, image_id: int
) -> None:
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {table} SET is_main = 0 WHERE {owner_column} = %s",
                (owner_id,),
            )
            cur.execute(
                f"UPDATE {table} SET is_main = 1 WHERE id = %s",
                (image_id,),
            )


def _delete_image_row(dbname: str, table: str, image_id: int) -> None:
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {table} WHERE id = %s", (image_id,))


async def _handle_upload(
    dbname: str,
    table: str,
    owner_column: str,
    owner_key: str,
    upload_subdir: str,
    owner_id: int,
    images: List[UploadFile],
) -> Dict[str, Any]:
    """Shared upload flow for character portraits and place images."""
    max_bytes, max_files = get_upload_limits()
    if not images:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(images) > max_files:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum is {max_files} per upload.",
        )
    for upload in images:
        _validate_upload(upload, max_bytes)

    owner_dir = UPLOAD_ROOT / upload_subdir / str(owner_id)
    owner_dir.mkdir(parents=True, exist_ok=True)

    # Current max display order, read from the same slot the rows are
    # written to (consulting the wrong database used to mis-flag a slot's
    # first portrait as non-main).
    existing = _fetch_images(dbname, table, owner_column, owner_id)
    max_order = max((row["display_order"] for row in existing), default=-1)

    uploaded: List[Dict[str, Any]] = []
    for upload in images:
        filename = _sanitize_filename(upload.filename or "upload.png")
        dest_path = owner_dir / filename
        contents = await upload.read()
        if len(contents) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    "File too large. Maximum size is "
                    f"{max_bytes // (1024 * 1024)}MB."
                ),
            )
        dest_path.write_bytes(contents)

        relative_path = f"{upload_subdir}/{owner_id}/{filename}"
        is_main = 1 if not existing and not uploaded else 0
        max_order += 1
        try:
            row = _insert_image(
                dbname, table, owner_column, owner_id, relative_path, is_main, max_order
            )
        except Exception:
            # Don't leave an orphaned file behind when the row insert fails;
            # the error still propagates to the client.
            dest_path.unlink(missing_ok=True)
            raise
        uploaded.append(_image_row_payload(row, owner_key))

    return {"success": True, "images": uploaded}


def _delete_image(
    dbname: str, table: str, owner_column: str, owner_id: int, image_id: int
) -> Dict[str, Any]:
    """Shared delete flow: remove the file (best effort), then the row."""
    images = _fetch_images(dbname, table, owner_column, owner_id)
    image = next((row for row in images if row["id"] == image_id), None)
    if image:
        file_path = UPLOAD_ROOT / image["file_path"]
        try:
            file_path.unlink()
        except OSError as exc:
            logger.warning("Could not delete image file %s: %s", file_path, exc)
    _delete_image_row(dbname, table, image_id)
    return {"success": True}


# ---------------------------------------------------------------------------
# Character images
# ---------------------------------------------------------------------------


@router.get("/api/characters/{character_id}/images")
async def get_character_images(
    character_id: int, slot: Optional[int] = None
) -> List[Dict[str, Any]]:
    """All images for a character, ordered by display order."""
    dbname = resolve_dbname(slot)
    rows = _fetch_images(
        dbname, "assets.character_images", "character_id", character_id
    )
    return [_image_row_payload(row, "characterId") for row in rows]


@router.post("/api/characters/{character_id}/images")
async def upload_character_images(
    character_id: int,
    images: List[UploadFile] = File(...),
    slot: Optional[int] = None,
) -> Dict[str, Any]:
    """Upload portrait files for a character (multipart field: images)."""
    dbname = resolve_dbname(slot)
    return await _handle_upload(
        dbname,
        "assets.character_images",
        "character_id",
        "characterId",
        "character_portraits",
        character_id,
        images,
    )


@router.put("/api/characters/{character_id}/images/{image_id}/main")
async def set_main_character_image(
    character_id: int, image_id: int, slot: Optional[int] = None
) -> Dict[str, Any]:
    """Mark one image as the character's main portrait."""
    dbname = resolve_dbname(slot)
    _set_main_image(
        dbname, "assets.character_images", "character_id", character_id, image_id
    )
    return {"success": True}


@router.delete("/api/characters/{character_id}/images/{image_id}")
async def delete_character_image(
    character_id: int, image_id: int, slot: Optional[int] = None
) -> Dict[str, Any]:
    """Delete a character image (file and row)."""
    dbname = resolve_dbname(slot)
    return _delete_image(
        dbname, "assets.character_images", "character_id", character_id, image_id
    )


# ---------------------------------------------------------------------------
# Place images
# ---------------------------------------------------------------------------


@router.get("/api/places/{place_id}/images")
async def get_place_images(
    place_id: int, slot: Optional[int] = None
) -> List[Dict[str, Any]]:
    """All images for a place, ordered by display order."""
    dbname = resolve_dbname(slot)
    rows = _fetch_images(dbname, "assets.place_images", "place_id", place_id)
    return [_image_row_payload(row, "placeId") for row in rows]


@router.post("/api/places/{place_id}/images")
async def upload_place_images(
    place_id: int,
    images: List[UploadFile] = File(...),
    slot: Optional[int] = None,
) -> Dict[str, Any]:
    """Upload image files for a place (multipart field: images)."""
    dbname = resolve_dbname(slot)
    return await _handle_upload(
        dbname,
        "assets.place_images",
        "place_id",
        "placeId",
        "place_images",
        place_id,
        images,
    )


@router.put("/api/places/{place_id}/images/{image_id}/main")
async def set_main_place_image(
    place_id: int, image_id: int, slot: Optional[int] = None
) -> Dict[str, Any]:
    """Mark one image as the place's main image."""
    dbname = resolve_dbname(slot)
    _set_main_image(dbname, "assets.place_images", "place_id", place_id, image_id)
    return {"success": True}


@router.delete("/api/places/{place_id}/images/{image_id}")
async def delete_place_image(
    place_id: int, image_id: int, slot: Optional[int] = None
) -> Dict[str, Any]:
    """Delete a place image (file and row)."""
    dbname = resolve_dbname(slot)
    return _delete_image(dbname, "assets.place_images", "place_id", place_id, image_id)
