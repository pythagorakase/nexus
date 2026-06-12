#!/usr/bin/env python3
"""Regenerate the per-theme PWA app icons with maskable safe-zone padding.

Reads the 1024px circuit-tree masters from the design handoff (untracked,
``design_handoff/project/assets/``), rescales the artwork so its bounding box
fits a centered safe zone (default 78% of the canvas — inside the W3C
maskable safe zone and the macOS squircle crop), pads with the exact
background color sampled from each master, and writes every size the app
serves:

    ui/client/public/icons/<theme>/icon-{512,192,180,32,16}.png
    ui/client/public/favicon.ico  (Veil 32 + 16)

After writing, every 512 is verified against a macOS-style rounded-rect mask
(corner radius 22.37% of the canvas): the script fails loudly if any artwork
pixel falls outside the mask. Pass ``--preview-dir`` to also write masked
preview composites for eyeballing.

Dependencies: Pillow, numpy.

Usage:
    python scripts/generate_app_icons.py [--masters DIR] [--safe-frac 0.78] \
        [--preview-dir /tmp/icon_previews]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MASTERS = Path("/Users/pythagor/nexus/design_handoff/project/assets")
ICONS_OUT = REPO_ROOT / "ui" / "client" / "public" / "icons"
FAVICON_OUT = REPO_ROOT / "ui" / "client" / "public" / "favicon.ico"

# Theme -> master filename. The unprefixed master is the Gilded livery.
MASTERS = {
    "veil": "icon-veil-source.png",
    "gilded": "icon-source.png",
    "vector": "icon-vector-source.png",
}

SIZES = (512, 192, 180, 32, 16)

# Pixels whose summed RGB distance from the background exceeds this are
# treated as artwork (the masters have hard art edges; the bbox is stable
# for thresholds 24-60).
ART_THRESHOLD = 40

# macOS app-icon rounded-rect corner radius as a fraction of the canvas
# (Apple's squircle is ~22.37%; a plain rounded rect with the same radius
# cuts slightly deeper into the corners, so it is the conservative check).
MACOS_CORNER_FRAC = 0.2237


def sample_background(rgb: np.ndarray) -> np.ndarray:
    """Median color of the 8px border ring — the master's true background."""
    ring = np.concatenate(
        [
            rgb[:8].reshape(-1, 3),
            rgb[-8:].reshape(-1, 3),
            rgb[:, :8].reshape(-1, 3),
            rgb[:, -8:].reshape(-1, 3),
        ]
    )
    return np.median(ring, axis=0)


def art_bbox(rgb: np.ndarray, bg: np.ndarray) -> tuple[int, int, int, int]:
    """Bounding box (x0, y0, x1, y1 inclusive) of pixels that differ from bg."""
    mask = np.abs(rgb.astype(int) - bg).sum(axis=2) > ART_THRESHOLD
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise ValueError("No artwork pixels found above threshold")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def compose_padded(master: Image.Image, safe_frac: float) -> Image.Image:
    """Scale the master so its artwork bbox fits a centered safe zone.

    Returns a canvas the same size as the master, filled with the sampled
    background color, with the scaled artwork bbox centered on it.
    """
    master_rgb = master.convert("RGB")
    rgb = np.asarray(master_rgb)
    side = master.width
    if master.height != side:
        raise ValueError(f"Master is not square: {master.size}")

    bg = sample_background(rgb)
    x0, y0, x1, y1 = art_bbox(rgb, bg)
    bbox_w, bbox_h = x1 - x0 + 1, y1 - y0 + 1

    scale = safe_frac * side / max(bbox_w, bbox_h)
    scaled = master_rgb.resize(
        (round(side * scale), round(side * scale)), Image.LANCZOS
    )

    # Re-detect the bbox on the scaled image (resampling shifts edges by a
    # fraction of a pixel) and center it on the output canvas.
    scaled_rgb = np.asarray(scaled)
    sx0, sy0, sx1, sy1 = art_bbox(scaled_rgb, bg)
    cx, cy = (sx0 + sx1) / 2, (sy0 + sy1) / 2

    canvas = Image.new("RGB", (side, side), tuple(int(c) for c in bg))
    canvas.paste(scaled, (round(side / 2 - cx), round(side / 2 - cy)))
    return canvas


def macos_mask(size: int) -> Image.Image:
    """White-on-black rounded-rect mask approximating the macOS icon crop."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    radius = MACOS_CORNER_FRAC * size
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def verify_no_art_lost(icon: Image.Image, theme: str) -> None:
    """Fail loudly if any artwork pixel falls outside the macOS-style mask."""
    rgb = np.asarray(icon.convert("RGB"))
    bg = sample_background(rgb)
    art = np.abs(rgb.astype(int) - bg).sum(axis=2) > ART_THRESHOLD
    outside = np.asarray(macos_mask(icon.width)) == 0
    lost = int((art & outside).sum())
    if lost:
        raise SystemExit(
            f"{theme}: {lost} artwork pixels outside the macOS mask "
            f"at {icon.width}px — increase padding (lower --safe-frac)"
        )
    print(f"  {theme} {icon.width}px: 0 artwork pixels lost to the macOS mask")


def write_masked_preview(icon: Image.Image, dest: Path) -> None:
    """Composite the icon under the rounded-rect mask for visual inspection."""
    preview = Image.new("RGBA", icon.size, (255, 255, 255, 255))
    preview.paste(icon.convert("RGBA"), (0, 0), macos_mask(icon.width))
    preview.save(dest)


def write_favicon(frames: dict[int, Image.Image]) -> None:
    """Write favicon.ico from the dedicated 32 + 16 frames and verify it.

    Pillow (>= 9.1) fills each entry in ``sizes`` with an exact-size match
    from ``[base] + append_images`` before falling back to downsampling the
    base, so both directory entries below come from the dedicated padded
    frames. The post-write check fails loudly if a Pillow behavior change
    ever substitutes a downsampled frame or alters the frame count.
    """
    frames[32].save(
        FAVICON_OUT,
        format="ICO",
        sizes=[(32, 32), (16, 16)],
        append_images=[frames[16]],
    )

    data = FAVICON_OUT.read_bytes()
    count = int.from_bytes(data[4:6], "little")
    if count != 2:
        raise SystemExit(f"favicon.ico has {count} frames, expected exactly 2")
    for size in (32, 16):
        ico = Image.open(FAVICON_OUT)
        ico.size = (size, size)
        if np.asarray(ico.convert("RGB")).tobytes() != (
            np.asarray(frames[size].convert("RGB")).tobytes()
        ):
            raise SystemExit(
                f"favicon.ico {size}px frame differs from the dedicated "
                f"padded frame — check Pillow ICO size-matching behavior"
            )
    print(f"favicon.ico written from Veil 32+16 (verified) -> {FAVICON_OUT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--masters",
        type=Path,
        default=DEFAULT_MASTERS,
        help="Directory containing the design-handoff icon masters",
    )
    parser.add_argument(
        "--safe-frac",
        type=float,
        default=0.78,
        help="Artwork bbox target as a fraction of the canvas (default 0.78)",
    )
    parser.add_argument(
        "--preview-dir",
        type=Path,
        default=None,
        help="If set, write masked 512px previews here for eyeballing",
    )
    args = parser.parse_args()

    if not args.masters.is_dir():
        raise SystemExit(
            f"Masters directory not found: {args.masters}\n"
            "The icon masters live in the untracked design handoff "
            "(design_handoff/project/assets/ in the main checkout). "
            "Pass --masters to point at your copy."
        )

    favicon_frames: dict[int, Image.Image] = {}

    for theme, master_name in MASTERS.items():
        master_path = args.masters / master_name
        master = Image.open(master_path)
        composed = compose_padded(master, args.safe_frac)
        print(f"{theme}: composed from {master_path.name} ({master.width}px)")

        out_dir = ICONS_OUT / theme
        out_dir.mkdir(parents=True, exist_ok=True)
        for size in SIZES:
            resized = composed.resize((size, size), Image.LANCZOS)
            resized.save(out_dir / f"icon-{size}.png")
            if size == 512:
                verify_no_art_lost(resized, theme)
                if args.preview_dir:
                    args.preview_dir.mkdir(parents=True, exist_ok=True)
                    write_masked_preview(
                        resized, args.preview_dir / f"{theme}-512-masked.png"
                    )
            if theme == "veil" and size in (32, 16):
                favicon_frames[size] = resized

    write_favicon(favicon_frames)


if __name__ == "__main__":
    main()
