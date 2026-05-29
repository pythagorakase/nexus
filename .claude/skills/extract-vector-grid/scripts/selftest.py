"""Self-contained regression test for extract-vector-grid.

Guards the degenerate-bbox bug: axis-aligned line segments (a horizontal line
has ymax == ymin; a vertical line has xmax == xmin) must NOT be discarded.
This is the failure that silently dropped 64 strokes from the Art Deco set —
most of a line-art frame is straight lines, so a `<=` bbox test annihilates it.

Run with the skill's venv (no pytest dependency):

    .venv/bin/python scripts/selftest.py

Exits 0 on pass; raises AssertionError (non-zero) on regression.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import (  # noqa: E402
    collect_shapes,
    drop_page_background,
    find_gutter_midpoints,
    assign_to_cells,
    extract,
)

# Two frames built ENTIRELY from axis-aligned line segments (4 borders each),
# side by side with an empty vertical gutter at x≈200, on a page-spanning
# background rect. A correct extractor keeps all 8 lines and finds 2 cells.
SYNTH_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="400pt" height="200pt" viewBox="0 0 400 200">
  <rect x="0" y="0" width="400" height="200" fill="black"/>
  <path d="M 20 20 L 180 20"   fill="none" stroke="gold"/>
  <path d="M 20 180 L 180 180" fill="none" stroke="gold"/>
  <path d="M 20 20 L 20 180"   fill="none" stroke="gold"/>
  <path d="M 180 20 L 180 180" fill="none" stroke="gold"/>
  <path d="M 220 20 L 380 20"   fill="none" stroke="gold"/>
  <path d="M 220 180 L 380 180" fill="none" stroke="gold"/>
  <path d="M 220 20 L 220 180"   fill="none" stroke="gold"/>
  <path d="M 380 20 L 380 180" fill="none" stroke="gold"/>
</svg>
"""


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        svg = Path(td) / "synth.svg"
        svg.write_text(SYNTH_SVG)

        shapes, page = collect_shapes(svg)
        kept = drop_page_background(shapes, page, coverage=0.9)
        bboxes = [bb for _, bb in kept]
        x_cuts = find_gutter_midpoints(bboxes, "x")
        y_cuts = find_gutter_midpoints(bboxes, "y")
        cells = assign_to_cells(kept, x_cuts, y_cuts)
        emitted = sum(len(v) for v in cells.values())

    # The regression dropped every line: collect_shapes would return only the
    # background rect, kept would be empty, and no cells would form.
    assert len(kept) == 8, (
        f"expected 8 axis-aligned line segments after background drop, "
        f"got {len(kept)} — straight strokes are being discarded "
        f"(degenerate-bbox regression)."
    )
    assert len(x_cuts) == 1, f"expected 1 vertical gutter, got {len(x_cuts)}: {x_cuts}"
    assert (
        len(y_cuts) == 0
    ), f"expected no horizontal gutter, got {len(y_cuts)}: {y_cuts}"
    assert len(cells) == 2, f"expected 2 cells, got {len(cells)}"
    assert emitted == 8, f"expected all 8 lines bucketed into cells, got {emitted}"
    print("PASS: 8 axis-aligned line segments preserved across 2 cells")

    # End-to-end through extract(): the low-level path above bypasses
    # _shape_signature (the emit-stage filter) and the path-conservation guard.
    # Running extract() exercises both — it raises if the guard trips.
    with tempfile.TemporaryDirectory() as td:
        svg = Path(td) / "synth.svg"
        svg.write_text(SYNTH_SVG)
        report = extract(
            svg,
            Path(td) / "out",
            name_prefix="selftest",
            padding=8.0,
            bg_coverage=0.9,
            verbose=False,
        )
    assert (
        len(report["cells"]) == 2
    ), f"extract() found {len(report['cells'])} cells, expected 2"
    e2e = sum(c["shape_count"] for c in report["cells"])
    assert e2e == 8, f"extract() emitted {e2e} line segments, expected 8"
    print("PASS: extract() end-to-end emitted 8 segments; conservation guard satisfied")


if __name__ == "__main__":
    main()
