---
name: extract-vector-grid
description: Extract each individual design from a multi-design vector sheet (e.g. an Adobe Stock frame/ornament/icon set arranged in a grid on a single artboard) into clean, transparent, tightly-cropped SVGs — losslessly preserving the original vector paths. Use when the user says "extract the frames/designs from this Adobe Stock set / ornament sheet / icon grid", "split this multi-design .ai into separate SVGs", "isolate each frame from this vector pack", or otherwise wants to separate per-design SVGs out of a grid layout. Also fires on `.ai` files that need format detection (.ai is usually PDF or EPS underneath).
---

# Extract Vector Grid

This skill splits a multi-design vector sheet — most commonly an Adobe Illustrator `.ai` file laid out as a grid of N frames / ornaments / icons — into one transparent SVG per design, preserving the original vector paths verbatim.

It bakes in several hard-won failure modes that naïve grid-cutters hit:

1. **`.ai` lies about its format.** Internally most `.ai` files are PDF; some are EPS. Always run `file <input>` first and branch.
2. **`pdftocairo`'s crop flags are silently ignored on `-svg` output.** Convert the whole page, isolate downstream in vector space.
3. **There is usually a page-spanning background shape.** Detect it generically by bbox-area ≈ page area (no fill-color assumption, no assumption a background exists).
4. **Never cut on nominal grid divisions** (`page_width / cols`). Ornaments routinely overhang their cell by a few points — cutting on grid lines amputates corner details. Use projection-profile gutter detection and cut through the **middle of the empty bands**.
5. **`svgelements` normalizes `width="...pt"` to 96-DPI pixels**, but the original path `d=` strings stay in viewBox user-units. The two coordinate systems must be reconciled before emitting per-cell SVGs (a 0.75 factor for any `pt`-declared source).

## When to invoke

- "Extract every frame from this Adobe Stock ornament pack into individual SVGs"
- "Split this multi-icon .ai file into one SVG per icon"
- "Isolate each design from this grid layout"
- Adobe Stock `.ai` purchases that ship as a sheet of N variants

## Bootstrap

The skill ships with a self-contained venv. If `.venv/` is missing (fresh checkout or new machine):

```bash
cd .claude/skills/extract-vector-grid
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Versions are pinned in `requirements.txt` because the coord-scale reconciliation in `extract.py` depends on `svgelements`' specific `pt`→`px` normalization. If you upgrade either package, re-run the validation acceptance test described below.

External dependencies:
- `poppler-utils` (provides `pdftocairo`) — required for PDF-backed `.ai` files
- `inkscape` (optional) — required for EPS-backed `.ai` files

## Usage

```bash
.claude/skills/extract-vector-grid/.venv/bin/python \
  .claude/skills/extract-vector-grid/scripts/extract.py \
  <path/to/sheet.ai> \
  --out <output_dir> \
  --name-prefix AdobeStock-<file#>-<DescriptiveMasterName>
```

Output filenames follow the project's Adobe Stock convention:
`<name-prefix>-r{row}c{col}.svg` (1-indexed).

The script emits a JSON report on stdout with:
- detected page dimensions
- detected rows × cols
- gutter-cut coordinates
- per-cell shape count + bbox

Per-design renaming (e.g. `…-CrescentMoon.svg`) is left to the human because the descriptive name is subjective per design.

## Validation

After extraction, render PNGs against a tinted background to visually verify:

```bash
.claude/skills/extract-vector-grid/.venv/bin/python \
  .claude/skills/extract-vector-grid/scripts/render_check.py \
  <output_dir> \
  --bg "#f4ead8"
```

Check that:
- Exactly N frames were produced (matching the source layout)
- Each frame is complete — borders intact on all four sides
- Symmetric designs *look* symmetric, including corner ornaments

## How it works (one-paragraph mental model)

`file` detects PDF vs EPS vs SVG → `pdftocairo -svg` (or Inkscape) converts the whole page to a flat SVG → `svgelements` parses each shape's bbox with transforms baked in → shapes whose bbox covers ≥90% of the page are dropped as background → empty bands on the X and Y axes (gutters) are detected via projection profiles → cut lines are placed at gutter midpoints (NOT nominal grid divisions) → each shape is bucketed into the cell its bbox center falls in → each cell's shapes get re-emitted as a minimal SVG with the original `d=` strings preserved verbatim, wrapped in a `<g transform="translate(-x -y)">` that moves content to origin, with a viewBox sized to the union bbox plus padding. Coordinates are scaled back from svgelements' px-space into the source's viewBox-unit space.

## Files

- `scripts/extract.py` — the extractor (entry point)
- `scripts/render_check.py` — PNG renderer for visual validation
- `.venv/` — skill-local Python environment (gitignored)

## Validation Evidence

Acceptance test: `AdobeStock-482408992-ArtNouveauFrames.ai` (a 2×5 Art Nouveau frame set, page ≈ 5658 × 3535 pt).

- Detected grid: **2 rows × 5 columns** ✓ (matches source layout)
- Page-spanning background shape detected and dropped: **1**
- All 10 cells emitted with uniform bbox ≈ 1292 × 1851 pt
- Top-left frame (r1c1) renders with the sunburst-dot tucked into the crescent's opening in **all four corners** — the exact regression the prompt called out

Per-cell path counts:

| Cell | Paths | Notes |
|------|------:|-------|
| r1c1 |    42 | Crescent-moon corners; 4-fold symmetric; sunburst-dots intact |
| r1c2 |    17 | Open frame, top + side curls |
| r1c3 |     5 | Compound-path encoding; floral with side dragons |
| r1c4 |    19 | Banner-top frame with intertwined bottom corners |
| r1c5 |    26 | Triple-line ornate corner flourishes |
| r2c1 |   130 | Author broke linework into segments; visually complete |
| r2c2 |     5 | Open frame with deliberate top/bottom asymmetry |
| r2c3 |     1 | Single compound path with `fill-rule:evenodd` — entire ornament |
| r2c4 |    24 | Title-plate top + central medallion bottom |
| r2c5 |     2 | Two compound paths; architectural double-line frame |

**Flags:** none. The 130-vs-1 path-count spread is the result of how the Adobe Stock author organized their compound paths (a workflow choice, not extraction quality). All renders are visually complete and match the source JPEG.

## Known limitations

- Single-page input only. Multi-page PDFs need iteration.
- Grid must have empty horizontal/vertical gutters between cells; pinned/touching layouts will collapse to one giant cell.
- Names are positional (`r1c1`, `r1c2`, …). Semantic names like `…-CrescentMoon` are a human-rename step.
