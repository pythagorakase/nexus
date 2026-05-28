#!/usr/bin/env python3
"""Extract individual designs from a multi-design vector sheet.

Handles Adobe Illustrator (.ai) files that are actually PDF or EPS underneath,
plus raw SVG. Produces one tightly-cropped, transparent SVG per detected design
using gutter-midpoint cutting (not nominal grid math) so overhanging ornament
detail is preserved.

Hard-won failure modes baked in:
  1. `file <input>` first — .ai lies about its format.
  2. pdftocairo's crop flags are silently ignored on -svg output; convert whole
     page and isolate in vector space.
  3. Drop the page-spanning background shape (detected by bbox ≈ page bounds).
  4. Cut through gutter midpoints, not on nominal grid lines, so ornaments that
     overhang their cell are not amputated.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from svgelements import SVG, Shape

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


@dataclass
class BBox:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def w(self) -> float:
        return self.xmax - self.xmin

    @property
    def h(self) -> float:
        return self.ymax - self.ymin

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def cx(self) -> float:
        return 0.5 * (self.xmin + self.xmax)

    @property
    def cy(self) -> float:
        return 0.5 * (self.ymin + self.ymax)


# --------------------------------------------------------------------------- #
# Stage 1: format detection + conversion to flat SVG
# --------------------------------------------------------------------------- #

def detect_format(path: Path) -> str:
    """Return 'pdf', 'eps', or 'svg' based on libmagic output."""
    out = subprocess.run(
        ["file", "--brief", str(path)], capture_output=True, text=True, check=True
    ).stdout.lower()
    if "pdf" in out:
        return "pdf"
    if "postscript" in out or "eps" in out:
        return "eps"
    if "svg" in out or path.suffix.lower() == ".svg":
        return "svg"
    raise RuntimeError(f"Cannot identify vector format from `file`: {out.strip()!r}")


def convert_to_svg(src: Path, dst: Path, fmt: str) -> None:
    """Convert src (pdf/eps/svg) to a flat SVG at dst."""
    if fmt == "svg":
        shutil.copy(src, dst)
        return
    if fmt == "pdf":
        # Copy with a .pdf extension because pdftocairo sniffs on extension.
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        shutil.copy(src, tmp_path)
        try:
            subprocess.run(
                ["pdftocairo", "-svg", str(tmp_path), str(dst)], check=True
            )
        finally:
            tmp_path.unlink(missing_ok=True)
        return
    if fmt == "eps":
        if not shutil.which("inkscape"):
            raise RuntimeError(
                "EPS source requires Inkscape, but `inkscape` is not on PATH."
            )
        subprocess.run(
            [
                "inkscape",
                str(src),
                "--export-type=svg",
                f"--export-filename={dst}",
            ],
            check=True,
        )
        return
    raise RuntimeError(f"Unsupported format: {fmt}")


# --------------------------------------------------------------------------- #
# Stage 2: shape extraction with absolute-coordinate bboxes
# --------------------------------------------------------------------------- #

def collect_shapes(svg_path: Path) -> tuple[list[tuple[Shape, BBox]], BBox]:
    """Return (shapes-with-bboxes, page-bbox).

    Transforms are baked in by svgelements' reify pass, so bboxes are in
    page coordinates regardless of nested <g transform=...> wrappers.
    """
    svg = SVG.parse(str(svg_path), reify=True)
    page = BBox(0.0, 0.0, float(svg.width), float(svg.height))

    shapes: list[tuple[Shape, BBox]] = []
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        bb = element.bbox()
        if bb is None:
            continue
        xmin, ymin, xmax, ymax = bb
        if xmax <= xmin or ymax <= ymin:
            continue
        shapes.append((element, BBox(xmin, ymin, xmax, ymax)))
    return shapes, page


def drop_page_background(
    shapes: list[tuple[Shape, BBox]], page: BBox, coverage: float = 0.9
) -> list[tuple[Shape, BBox]]:
    """Drop shapes whose bbox covers >=coverage of the page area.

    Generic detection — no fill-color assumption, no assumption that a background
    shape exists at all.
    """
    page_area = max(page.area, 1.0)
    return [
        (s, bb) for s, bb in shapes if bb.area / page_area < coverage
    ]


# --------------------------------------------------------------------------- #
# Stage 3: projection-profile gutter detection
# --------------------------------------------------------------------------- #

def find_gutter_midpoints(
    bboxes: Iterable[BBox], axis: str, page_lo: float, page_hi: float
) -> list[float]:
    """Find midpoints of empty bands along an axis.

    `axis` is 'x' or 'y'. Returns cut coordinates in ascending order, excluding
    the page boundary itself (we use boundaries as the outer cell limits).
    """
    if axis == "x":
        intervals = [(bb.xmin, bb.xmax) for bb in bboxes]
    else:
        intervals = [(bb.ymin, bb.ymax) for bb in bboxes]
    if not intervals:
        return []

    intervals.sort()
    # Sweep-merge to find filled bands; gaps between filled bands are gutters.
    merged: list[list[float]] = [list(intervals[0])]
    for lo, hi in intervals[1:]:
        if lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])

    cuts: list[float] = []
    for left, right in zip(merged, merged[1:]):
        gap_lo, gap_hi = left[1], right[0]
        cuts.append(0.5 * (gap_lo + gap_hi))
    return cuts


def assign_to_cells(
    shapes: list[tuple[Shape, BBox]],
    x_cuts: list[float],
    y_cuts: list[float],
) -> dict[tuple[int, int], list[tuple[Shape, BBox]]]:
    """Bucket shapes into (row, col) cells by bbox center."""
    cells: dict[tuple[int, int], list[tuple[Shape, BBox]]] = {}
    for shape, bb in shapes:
        col = sum(1 for c in x_cuts if bb.cx > c)
        row = sum(1 for c in y_cuts if bb.cy > c)
        cells.setdefault((row, col), []).append((shape, bb))
    return cells


def union_bbox(items: list[tuple[Shape, BBox]]) -> BBox:
    xmin = min(bb.xmin for _, bb in items)
    ymin = min(bb.ymin for _, bb in items)
    xmax = max(bb.xmax for _, bb in items)
    ymax = max(bb.ymax for _, bb in items)
    return BBox(xmin, ymin, xmax, ymax)


# --------------------------------------------------------------------------- #
# Stage 4: emit per-cell SVG
# --------------------------------------------------------------------------- #

def read_viewbox_width(svg_path: Path) -> float | None:
    """Return the viewBox width in user-units, or None if no viewBox.

    Path `d=` strings live in viewBox user-units, but svgelements normalizes
    `width="...pt"` to pixels. We need the viewBox width to reconcile the two
    coordinate systems when emitting per-cell SVGs.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()
    vb = root.attrib.get("viewBox") or root.attrib.get(f"{{{SVG_NS}}}viewBox")
    if not vb:
        return None
    parts = vb.split()
    if len(parts) != 4:
        return None
    return float(parts[2])


def emit_cell_svg(
    flat_svg_path: Path,
    cell_shapes: list[tuple[Shape, BBox]],
    bbox: BBox,
    out_path: Path,
    padding: float,
    coord_scale: float,
) -> int:
    """Write a minimal SVG containing only `cell_shapes`, translated to origin.

    Returns the path/shape count emitted. The XML walk and the svgelements
    walk are kept in parallel doc-order so we can map svgelements shapes back
    to their original XML nodes (and clone the original `d=` strings verbatim).
    """
    reified = SVG.parse(str(flat_svg_path), reify=True)

    # Match by stable signature: (rounded bbox, length-of-path-string).
    # Returns None for shapes that would have been filtered upstream so the
    # two parallel walks (svgelements + XML) stay aligned by *raw* doc order.
    def signature(shape: Shape) -> tuple | None:
        bb = shape.bbox()
        if bb is None:
            return None
        xmin, ymin, xmax, ymax = bb
        if xmax <= xmin or ymax <= ymin:
            return None
        rounded = (round(xmin, 3), round(ymin, 3), round(xmax, 3), round(ymax, 3))
        try:
            d = shape.d()
        except Exception:
            d = ""
        return rounded + (len(d),)

    keep_sigs: dict[tuple, int] = {}
    for s, _ in cell_shapes:
        sig = signature(s)
        if sig is None:
            continue
        keep_sigs[sig] = keep_sigs.get(sig, 0) + 1

    # Now walk the XML; for each shape-bearing element, reify just that one and
    # compute its signature; if it's in keep_sigs (counter > 0), keep it.
    tree = ET.parse(flat_svg_path)
    root = tree.getroot()
    # Drop anything that isn't a shape-bearing tag at the leaf, but preserve
    # ancestor <g> structure so transforms (if any survived) still apply.
    shape_tags = {f"{{{SVG_NS}}}{t}" for t in (
        "path", "rect", "circle", "ellipse", "line", "polyline", "polygon"
    )}

    # Walk the reified shapes in doc order in parallel with the XML's
    # shape-tagged elements in doc order. svgelements skips shapes that live
    # inside <defs>, <clipPath>, <mask>, <symbol>, <pattern> (they're not
    # rendered), so the XML walk must skip those subtrees too to keep the
    # parallel iteration aligned.
    non_rendering_tags = {
        f"{{{SVG_NS}}}{t}"
        for t in ("defs", "clipPath", "mask", "symbol", "pattern", "marker")
    }
    all_shape_xml_nodes: list[ET.Element] = []

    def walk(node: ET.Element) -> None:
        if node.tag in non_rendering_tags:
            return
        if node.tag in shape_tags:
            all_shape_xml_nodes.append(node)
        for child in node:
            walk(child)

    walk(root)
    reified_shapes_in_order: list[Shape] = [
        e for e in reified.elements() if isinstance(e, Shape)
    ]
    if len(all_shape_xml_nodes) != len(reified_shapes_in_order):
        raise RuntimeError(
            f"Shape-count mismatch between XML walk "
            f"({len(all_shape_xml_nodes)}) and svgelements parse "
            f"({len(reified_shapes_in_order)}); cannot safely map back."
        )
    keep_xml: set[int] = set()
    for xml_node, shape in zip(all_shape_xml_nodes, reified_shapes_in_order):
        sig = signature(shape)
        if keep_sigs.get(sig, 0) > 0:
            keep_xml.add(id(xml_node))
            keep_sigs[sig] -= 1

    # Build a new SVG with viewBox at the (padded) cell bbox and shapes
    # translated to origin via an outer <g transform="translate(-x, -y)">.
    # All values are scaled into the source SVG's viewBox-unit coordinate
    # system (which is what the cloned path `d=` strings use) — svgelements
    # bboxes come back in px-normalized space, so we undo that here.
    pad_xmin = (bbox.xmin - padding) * coord_scale
    pad_ymin = (bbox.ymin - padding) * coord_scale
    pad_w = (bbox.w + 2 * padding) * coord_scale
    pad_h = (bbox.h + 2 * padding) * coord_scale

    new_root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "viewBox": f"0 0 {pad_w} {pad_h}",
            "width": f"{pad_w}",
            "height": f"{pad_h}",
        },
    )
    g = ET.SubElement(
        new_root,
        f"{{{SVG_NS}}}g",
        {"transform": f"translate({-pad_xmin} {-pad_ymin})"},
    )

    kept = 0
    for xml_node in all_shape_xml_nodes:
        if id(xml_node) in keep_xml:
            # Copy the node (and reset any id to avoid collisions)
            clone = ET.fromstring(ET.tostring(xml_node))
            if "id" in clone.attrib:
                del clone.attrib["id"]
            g.append(clone)
            kept += 1

    ET.ElementTree(new_root).write(
        out_path, encoding="utf-8", xml_declaration=True
    )
    return kept


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def extract(
    input_path: Path,
    output_dir: Path,
    name_prefix: str,
    padding: float,
    bg_coverage: float,
    verbose: bool,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    fmt = detect_format(input_path)
    if verbose:
        print(f"[detect] input format: {fmt}", file=sys.stderr)

    with tempfile.TemporaryDirectory() as td:
        flat = Path(td) / "flat.svg"
        convert_to_svg(input_path, flat, fmt)
        if verbose:
            print(f"[convert] flat svg: {flat}", file=sys.stderr)

        shapes, page = collect_shapes(flat)
        vb_w = read_viewbox_width(flat)
        coord_scale = (vb_w / page.w) if (vb_w and page.w) else 1.0
        if verbose:
            print(
                f"[parse] page={page.w:.1f}x{page.h:.1f} px, "
                f"viewBox-w={vb_w}, coord_scale={coord_scale:.6f}, "
                f"{len(shapes)} shapes",
                file=sys.stderr,
            )

        kept = drop_page_background(shapes, page, coverage=bg_coverage)
        dropped = len(shapes) - len(kept)
        if verbose:
            print(
                f"[bg] dropped {dropped} page-spanning shape(s) "
                f"(coverage threshold {bg_coverage})",
                file=sys.stderr,
            )

        bbs = [bb for _, bb in kept]
        x_cuts = find_gutter_midpoints(bbs, "x", page.xmin, page.xmax)
        y_cuts = find_gutter_midpoints(bbs, "y", page.ymin, page.ymax)
        cols = len(x_cuts) + 1
        rows = len(y_cuts) + 1
        if verbose:
            print(
                f"[grid] detected {rows} rows x {cols} cols",
                file=sys.stderr,
            )
            print(f"[grid] x cuts: {[round(c, 1) for c in x_cuts]}", file=sys.stderr)
            print(f"[grid] y cuts: {[round(c, 1) for c in y_cuts]}", file=sys.stderr)

        cells = assign_to_cells(kept, x_cuts, y_cuts)

        manifest: list[dict] = []
        for (r, c), items in sorted(cells.items()):
            ubox = union_bbox(items)
            out_name = f"{name_prefix}-r{r+1}c{c+1}.svg"
            out_path = output_dir / out_name
            shape_count = emit_cell_svg(
                flat, items, ubox, out_path,
                padding=padding, coord_scale=coord_scale,
            )
            manifest.append(
                {
                    "row": r + 1,
                    "col": c + 1,
                    "file": out_name,
                    "shape_count": shape_count,
                    "bbox_w": round(ubox.w, 2),
                    "bbox_h": round(ubox.h, 2),
                }
            )
            if verbose:
                print(
                    f"[emit] {out_name}  shapes={shape_count}  "
                    f"bbox={ubox.w:.1f}x{ubox.h:.1f}",
                    file=sys.stderr,
                )

        return {
            "input": str(input_path),
            "format": fmt,
            "page": {"w": round(page.w, 2), "h": round(page.h, 2)},
            "rows": rows,
            "cols": cols,
            "x_cuts": [round(c, 2) for c in x_cuts],
            "y_cuts": [round(c, 2) for c in y_cuts],
            "shapes_total": len(shapes),
            "shapes_dropped_as_bg": dropped,
            "cells": manifest,
        }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path, help="Input .ai / .pdf / .eps / .svg file")
    p.add_argument(
        "--out", "-o", type=Path, required=True, help="Output directory"
    )
    p.add_argument(
        "--name-prefix",
        "-n",
        required=True,
        help="Prefix for output filenames, e.g. AdobeStock-482408992-ArtNouveauFrames",
    )
    p.add_argument(
        "--padding", type=float, default=4.0, help="Padding in pt around each cell"
    )
    p.add_argument(
        "--bg-coverage",
        type=float,
        default=0.9,
        help="Drop shapes whose bbox covers >= this fraction of the page",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    report = extract(
        args.input,
        args.out,
        name_prefix=args.name_prefix,
        padding=args.padding,
        bg_coverage=args.bg_coverage,
        verbose=not args.quiet,
    )
    import json

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
