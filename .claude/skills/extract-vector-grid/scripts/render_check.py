#!/usr/bin/env python3
"""Render extracted SVGs to PNG on a contrasting background for visual review.

Optional convenience script — not required by the skill, but useful during
validation: dumps each SVG in a directory to a same-named PNG with a tinted
background so transparent fills don't disappear into a white viewer.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cairosvg


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("src_dir", type=Path)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--width", type=int, default=600)
    p.add_argument(
        "--bg",
        default="#f4ead8",
        help="CSS color for the rendered background "
        "(default Art Nouveau beige; pick contrasting for your art)",
    )
    args = p.parse_args()

    out_dir = args.out or args.src_dir / "_png_preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    svgs = sorted(args.src_dir.glob("*.svg"))
    if not svgs:
        print(f"No SVGs in {args.src_dir}")
        return 1

    for svg in svgs:
        out = out_dir / (svg.stem + ".png")
        # Wrap the SVG in a tinted background by prepending a <rect>.
        text = svg.read_text(encoding="utf-8")
        # Inject the tint after the opening <svg ...> tag (not the XML prolog).
        idx = text.find("<svg")
        end = text.find(">", idx) + 1
        injected = (
            text[:end]
            + f'<rect x="-100%" y="-100%" width="300%" height="300%" '
            f'fill="{args.bg}"/>'
            + text[end:]
        )
        cairosvg.svg2png(
            bytestring=injected.encode("utf-8"),
            write_to=str(out),
            output_width=args.width,
        )
        print(f"rendered {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
