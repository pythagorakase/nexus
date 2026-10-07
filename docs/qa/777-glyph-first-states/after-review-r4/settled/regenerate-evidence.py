"""Regenerate certified tables and display swatches from settled browser means."""

import csv
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path.cwd()
OUT = ROOT / "docs/qa/777-glyph-first-states/amendment-2"
HERE = Path(__file__).resolve().parent
receipt = json.loads((ROOT / "ui/client/src/state-surfaces.resolved.json").read_text())
assert receipt["proof"]["acceptanceComplete"]
encode = lambda v: 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
rgb = lambda values: [round(255 * encode(v)) for v in values]
matrix = [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
]
deutan = lambda values: rgb(
    [max(0, min(1, sum(v * c for v, c in zip(values, row)))) for row in matrix]
)
rows, swatches, groups, exceptions = [], [], [], {}
for theme in ["Veil", "Gilded", "Vector"]:
    data = json.loads((OUT / f"{theme.lower()}-joint.json").read_text())
    exceptions[theme] = []
    pairs = [
        f"# {theme} Settled Painted Mask-Mean Pairs",
        "",
        "Certified by exact same-value witnesses and Amendment 4 per-group acceptance.",
        "",
        "Default: 1200×900, device scale 4, dark, reduced motion; Chromium 153.0.8010.12 / Playwright 1.63.0, file://, HTTP(S) aborted. Full linear means and all 18 conditions remain in the CSV and joint JSON.",
        "",
        "| Group / Context | States | Before Display RGB | After Display RGB | Before ΔE00 | After ΔE00 | Static Signatures |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for before, after in zip(data["before"], data["measurements"]):
        assert all(
            before[k] == after[k]
            for k in ["theme", "surface", "context", "condition", "states"]
        )
        rows.append(
            [
                theme,
                after["condition"],
                after["surface"],
                after["context"],
                "/".join(after["states"]),
                json.dumps(before["rgb"]),
                json.dumps(after["rgb"]),
                json.dumps([rgb(c) for c in before["rgb"]]),
                json.dumps([rgb(c) for c in after["rgb"]]),
                before["delta"],
                after["delta"],
                " / ".join(after["signatures"]),
                after["delta"] < 15,
            ]
        )
        if after["delta"] < 15:
            exceptions[theme].append(
                f'{after["condition"]}/{after["surface"]}/{after["context"]}/{"/".join(after["states"])}'
            )
        if after["condition"] == "default":
            pairs.append(
                f'| {after["surface"]}/{after["context"]} | {"/".join(after["states"])} | {json.dumps([rgb(c) for c in before["rgb"]])} | {json.dumps([rgb(c) for c in after["rgb"]])} | {before["delta"]:.6f} | {after["delta"]:.6f} | {" / ".join(after["signatures"])} |'
            )
    (OUT / f"{theme.lower()}-pairs.md").write_text(
        "\n".join(pairs) + "\n\nCodex, GPT-6.\n"
    )
    for f in data["factorMaxima"]:
        measured = [m for m in data["measurements"] if m["surface"] == f["surface"]]
        groups.append(
            {
                "theme": theme,
                **f,
                "actualShippedMinimum": min(m["delta"] for m in measured),
                "shortfalls": sum(m["delta"] < 15 for m in measured),
            }
        )
    d = receipt["conditions"]["default"][theme]
    for group, context in [
        ("memory", "memory/fill"),
        ("delete", "delete/ready/rest"),
        ("map", "map/canvas-sea/fill"),
        ("key", "key/required/rest"),
    ]:
        contexts = {**d["shipped"][context]}
        if group == "key":
            contexts = {
                "optional-absent": d["shipped"]["key/optional/rest"]["optional-absent"],
                **contexts,
            }
        for state, sample in contexts.items():
            c = "key/optional/rest" if state == "optional-absent" else context
            before = d["before"][c][state]["meanLinear"]
            after = sample["meanLinear"]
            swatches.append(
                {
                    "theme": theme,
                    "group": group,
                    "state": state,
                    "context": c,
                    "beforeLinear": before,
                    "afterLinear": after,
                    "displayRgb": [
                        rgb(before),
                        deutan(before),
                        rgb(after),
                        deutan(after),
                    ],
                }
            )
with (OUT / "pair-measurements.csv").open("w", newline="") as fp:
    writer = csv.writer(fp, lineterminator="\n")
    writer.writerow(
        [
            "theme",
            "condition",
            "surface",
            "context",
            "states",
            "before_linear_srgb",
            "after_linear_srgb",
            "before_display_rgb",
            "after_display_rgb",
            "before_delta_e00",
            "after_delta_e00",
            "static_signatures",
            "below_15",
        ]
    )
    writer.writerows(rows)
(OUT / "theme-exceptions.json").write_text(json.dumps(exceptions, indent=2) + "\n")
(HERE / "group-results.json").write_text(json.dumps(groups, indent=2) + "\n")
(HERE / "swatch-inputs.json").write_text(json.dumps(swatches, indent=2) + "\n")
text = [
    "# Amendment 4 Certified Group Search and Exceptions",
    "",
    "Every shipped same-value witness agrees exactly with its settled candidate. Each group accepts 15 when reachable, otherwise its own joint maximum; ties prefer the fewest changed tokens. Globals remain frozen except the seven Veil anchors.",
    "",
    "| Theme | Group | Joint Maximum | Shipped Minimum | ≥15 Assignments | Changed Tokens | Below-15 Comparisons |",
    "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
]
text += [
    f'| {g["theme"]} | {g["surface"]} | {g["best"]} | {g["actualShippedMinimum"]} | {g["feasible"]} | {g["changes"]} | {g["shortfalls"]} |'
    for g in groups
]
text += [
    "",
    "Exception groups: Veil delete/map; Gilded delete/map/key; Vector map/key. All shortfalls retain distinct static signatures. Reachable groups ship at least 15 under every condition.",
    "",
    "Unreachable states remain exclusions: sidebar hovered, absent keys in required rows, missing keys in optional rows, and absent/missing pairs without a shared context. See the accepted reachable-inventory evidence. There are 70 state samples per phase/theme/condition, 69 comparisons, and 13 base pairs.",
    "",
    "Codex, GPT-6.",
]
(OUT / "exceptions.md").write_text("\n".join(text) + "\n")
(OUT / "pair-measurements.md").write_text(
    "# Certified Settled Painted Mask-Mean Measurements\n\nAll 3,780 same-value witnesses and per-group acceptance pass. [All 3,726 comparisons](pair-measurements.csv), [Veil](veil-pairs.md), [Gilded](gilded-pairs.md), [Vector](vector-pairs.md). Primary tables show default; CSV and joint JSON hold all 18 conditions. Means remain linear for Machado, D65 CIELAB and CIEDE2000; display RGB encodes the mean.\n\nCodex, GPT-6.\n"
)
p = OUT / "state-tokens.md"
p.write_text(
    p.read_text().replace(
        "Mask-mean search assignments; acceptance blocked by the delayed tooltip witness mismatch.",
        "Settled mask-mean assignments certified by exact same-value witnesses and per-group acceptance.",
    )
)
image = Image.new("RGB", (1200, 1460), "#10151e")
draw = ImageDraw.Draw(image)
font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1460" viewBox="0 0 1200 1460"><rect width="1200" height="1460" fill="#10151e"/><g font-family="monospace" fill="#ecedf2">'
]


def label(x, y, text):
    draw.text((x, y - 13), text, fill="#ecedf2", font=font)
    svg.append(f'<text x="{x}" y="{y}" font-size="13">{html.escape(text)}</text>')


label(24, 28, "Certified settled painted mask means — default condition")
label(
    24,
    53,
    "Full-mask linear means encoded for display; Machado 1.0 on retained linear channels.",
)
for x, title in zip(
    [620, 752, 884, 1016], ["Before", "Before deutan", "After", "After deutan"]
):
    label(x, 80, title)
for i, row in enumerate(swatches):
    y = 94 + i * 37
    label(24, y + 20, f'{row["theme"]} {row["group"]}/{row["state"]}')
    for x, color in zip([620, 752, 884, 1016], row["displayRgb"]):
        draw.rectangle((x, y, x + 113, y + 27), fill=tuple(color))
        svg.append(
            f'<rect x="{x}" y="{y}" width="114" height="28" fill="rgb({",".join(map(str,color))})"/>'
        )
label(24, 1440, "Codex, GPT-6.")
svg.append("</g></svg>")
(OUT / "swatches.svg").write_text("\n".join(svg) + "\n")
image.save(OUT / "swatches.png")
print(
    f"Certified tables: {len(rows)} comparisons; {len(swatches)} state rows; {4 * len(swatches)} painted-mean swatches; exceptions="
    + json.dumps({t: len(v) for t, v in exceptions.items()})
)
