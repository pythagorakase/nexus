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
import hashlib
import json
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
        # Keep axis-aligned line segments. A horizontal line has ymax == ymin
        # and a vertical line has xmax == xmin, so a `<=` test on either axis
        # silently discards every straight stroke (frame borders, radial ticks)
        # — catastrophic for line-art sheets. Reject only inverted boxes and
        # true zero-extent points (degenerate on BOTH axes).
        if xmax < xmin or ymax < ymin or (xmax == xmin and ymax == ymin):
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

def find_gutter_midpoints(bboxes: Iterable[BBox], axis: str) -> list[float]:
    """Find midpoints of empty bands along an axis.

    `axis` is 'x' or 'y'. Returns cut coordinates in ascending order. Page
    boundaries are implicit (they define the outer cell limits, not internal
    cuts), so this returns only the *internal* gutter midpoints.
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


SHAPE_TAGS = {
    f"{{{SVG_NS}}}{t}"
    for t in ("path", "rect", "circle", "ellipse", "line", "polyline", "polygon")
}
NON_RENDERING_TAGS = {
    f"{{{SVG_NS}}}{t}"
    for t in ("defs", "clipPath", "mask", "symbol", "pattern", "marker")
}


def _shape_signature(shape: Shape) -> tuple | None:
    """Stable signature for matching svgelements Shape ↔ source XML node.

    Combines reified bbox + element tag + fill + a short hash of the path
    string. The tag and fill, plus the path hash (not just length), defeat
    collisions between identical symmetric ornaments (e.g. four corner
    flourishes with the same bbox and same path-length).
    """
    bb = shape.bbox()
    if bb is None:
        return None
    xmin, ymin, xmax, ymax = bb
    # Mirror collect_shapes: keep zero-area line segments (frame borders, ticks);
    # reject only inverted boxes and true zero-extent points. A `<=` test here
    # would re-introduce the line-dropping bug at the emit/match stage.
    if xmax < xmin or ymax < ymin or (xmax == xmin and ymax == ymin):
        return None
    rounded = (round(xmin, 3), round(ymin, 3), round(xmax, 3), round(ymax, 3))
    try:
        d = shape.d()
    except Exception:
        d = ""
    d_hash = hashlib.sha1(d.encode("utf-8")).hexdigest()[:16] if d else ""
    fill = getattr(shape, "fill", None)
    fill_str = str(fill) if fill is not None else ""
    tag = type(shape).__name__
    return rounded + (tag, fill_str, d_hash)


def prepare_shape_index(
    flat_svg_path: Path,
) -> tuple[SVG, list[ET.Element], list[Shape], dict[ET.Element, ET.Element]]:
    """Parse the flat SVG once, return everything needed to emit cells.

    Returns:
      reified            — svgelements parse, transforms baked into bboxes
      xml_nodes_in_order — every rendering shape-bearing XML node, in doc order
      shapes_in_order    — svgelements Shape walk in the SAME doc order
      parent_map         — child→parent map over the raw XML tree, used to
                           preserve ancestor transforms when cloning leaves
    """
    reified = SVG.parse(str(flat_svg_path), reify=True)
    tree = ET.parse(flat_svg_path)
    root = tree.getroot()

    parent_map: dict[ET.Element, ET.Element] = {}
    xml_nodes_in_order: list[ET.Element] = []

    def walk(node: ET.Element) -> None:
        if node.tag in NON_RENDERING_TAGS:
            return
        if node.tag in SHAPE_TAGS:
            xml_nodes_in_order.append(node)
        for child in node:
            parent_map[child] = node
            walk(child)

    walk(root)

    shapes_in_order: list[Shape] = [
        e for e in reified.elements() if isinstance(e, Shape)
    ]
    if len(xml_nodes_in_order) != len(shapes_in_order):
        raise RuntimeError(
            f"Shape-count mismatch between XML walk "
            f"({len(xml_nodes_in_order)}) and svgelements parse "
            f"({len(shapes_in_order)}); cannot safely map back."
        )
    return reified, xml_nodes_in_order, shapes_in_order, parent_map


def compose_ancestor_transform(
    leaf: ET.Element, parent_map: dict[ET.Element, ET.Element]
) -> str | None:
    """Walk parents → root, concatenating any inherited transform= strings.

    Returned in outer-to-inner order so the composed transform applies in the
    same order SVG rendering does. Returns None when no ancestor carries a
    transform — most pdftocairo output, for example.
    """
    transforms: list[str] = []
    node = parent_map.get(leaf)
    while node is not None:
        t = node.attrib.get("transform")
        if t:
            transforms.append(t.strip())
        node = parent_map.get(node)
    if not transforms:
        return None
    # Outer-most ancestor applies first; we collected inner-to-outer, so reverse
    return " ".join(reversed(transforms))


def emit_cell_svg(
    cell_shapes: list[tuple[Shape, BBox]],
    bbox: BBox,
    out_path: Path,
    padding: float,
    coord_scale: float,
    xml_nodes_in_order: list[ET.Element],
    shapes_in_order: list[Shape],
    parent_map: dict[ET.Element, ET.Element],
) -> int:
    """Write a minimal SVG containing only `cell_shapes`, translated to origin.

    Original `d=` strings are cloned verbatim (lossless). Any ancestor
    `<g transform=...>` chain is composed into a wrapping transform on the
    clone so geometry lands in the same absolute-coord space the bbox was
    computed in.
    """
    keep_sigs: dict[tuple, int] = {}
    for s, _ in cell_shapes:
        sig = _shape_signature(s)
        if sig is None:
            continue
        keep_sigs[sig] = keep_sigs.get(sig, 0) + 1

    keep_xml: list[ET.Element] = []
    for xml_node, shape in zip(xml_nodes_in_order, shapes_in_order):
        sig = _shape_signature(shape)
        if keep_sigs.get(sig, 0) > 0:
            keep_xml.append(xml_node)
            keep_sigs[sig] -= 1

    # Build the new SVG. viewBox + translate values are in the source's
    # viewBox-unit coordinate system (what the cloned path `d=` strings use).
    # svgelements bboxes are in px-normalized space, so we undo that here.
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
    translate_g = ET.SubElement(
        new_root,
        f"{{{SVG_NS}}}g",
        {"transform": f"translate({-pad_xmin} {-pad_ymin})"},
    )

    for xml_node in keep_xml:
        clone = ET.fromstring(ET.tostring(xml_node))
        if "id" in clone.attrib:
            del clone.attrib["id"]
        ancestor_t = compose_ancestor_transform(xml_node, parent_map)
        if ancestor_t:
            wrapper = ET.SubElement(
                translate_g, f"{{{SVG_NS}}}g", {"transform": ancestor_t}
            )
            wrapper.append(clone)
        else:
            translate_g.append(clone)

    ET.ElementTree(new_root).write(
        out_path, encoding="utf-8", xml_declaration=True
    )
    return len(keep_xml)


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
        x_cuts = find_gutter_midpoints(bbs, "x")
        y_cuts = find_gutter_midpoints(bbs, "y")
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

        # Parse the flat SVG once and share the XML / reified walks across all
        # cells — keeps emit_cell_svg's per-call cost O(cell_shapes), not
        # O(total_shapes) × O(cells).
        _, xml_nodes_in_order, shapes_in_order, parent_map = prepare_shape_index(
            flat
        )

        manifest: list[dict] = []
        for (r, c), items in sorted(cells.items()):
            ubox = union_bbox(items)
            out_name = f"{name_prefix}-r{r+1}c{c+1}.svg"
            out_path = output_dir / out_name
            shape_count = emit_cell_svg(
                items, ubox, out_path,
                padding=padding, coord_scale=coord_scale,
                xml_nodes_in_order=xml_nodes_in_order,
                shapes_in_order=shapes_in_order,
                parent_map=parent_map,
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

        # Path-conservation guard. Every renderable shape node pdftocairo/Inkscape
        # emitted must be accounted for — emitted into a cell or dropped as the
        # page background. If the totals don't reconcile, a path was silently
        # lost (the class of bug where a degenerate-bbox filter eats axis-aligned
        # lines). Fail loudly rather than ship a lossy extraction.
        total_nodes = len(xml_nodes_in_order)
        emitted_total = sum(m["shape_count"] for m in manifest)
        if emitted_total + dropped != total_nodes:
            raise RuntimeError(
                f"Path-conservation check failed: flat SVG has {total_nodes} "
                f"renderable shape nodes, but {emitted_total} were emitted into "
                f"cells + {dropped} dropped as background = "
                f"{emitted_total + dropped}. "
                f"{total_nodes - (emitted_total + dropped)} path(s) were lost — "
                f"commonly axis-aligned lines rejected by a degenerate-bbox "
                f"filter (xmax<=xmin / ymax<=ymin)."
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
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
