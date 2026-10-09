# Captured Inventory With Failed Interaction Acceptance

Source: `149704d16fa126b8ac9d142a22bf51b42a669552`; unchanged UI input closure
from implementation `3a146419ef535850f7cab28beb540ef74d32783d`.
Input SHA-256: `e69f417601220083703cf197f442b44969eebede7debeafa8dffcd4516b0d68f`.

This is preserved failed-acceptance evidence. The exact [receipt](receipt.json)
has complete capture coverage (`proof.acceptanceComplete` is the generator's
coverage marker), but did **not** pass the strict interaction test. It is not
the final accepted receipt and cannot be reused after the harness correction.

## Capture and Comparison

Nine serial `nice -n 15` batches captured all 33 conditions with identical
fingerprints and all three fixed calibrations passing. Each command stayed
within its 589-second bound, with zero network requests and page errors.

| Batch | Conditions | Captures | Wall Seconds | Pre-Run Load |
| --- | ---: | ---: | ---: | ---: |
| 1 | 4 | 15,262 | 386.353 | 4.63 |
| 2 | 4 | 15,262 | 393.314 | 6.22 |
| 3 | 4 | 15,262 | 387.116 | 5.50 |
| 4 | 4 | 15,262 | 397.446 | 3.54 |
| 5 | 4 | 15,262 | 386.799 | 6.08 |
| 6 | 4 | 15,262 | 387.045 | 5.54 |
| 7 | 4 | 15,262 | 398.497 | 7.90 |
| 8 | 4 | 15,262 | 387.834 | 7.73 |
| 9 | 1 | 3,982 | 369.590 | 7.64 |

The [assembly log](assemble.log) records 126,078 captures, 33 conditions,
2,098 module-graph inputs, Chromium 153.0.8010.12 and Playwright 1.63.0.
The wall-time sum is 3493.993 seconds; it is not a single unbounded command.
Exact per-batch logs are adjacent. The default calibration is repeated in each
batch, so the capture count includes those repeated calibration samples.

The independently source-reviewed [comparator](compare-receipts.py) and
[mapping](legacy-condition-map.json) establish a bijection over all 27 legacy
conditions by viewport, motion and phase, plus six explicitly new coarse
conditions. They compare all shipped, before and candidate samples in all
themes. Stable tooltip settlement semantics are included; only elapsed timing,
DOM signature hashes, action prose and capture filenames are excluded.

The [summary](comparison-summary.json) records 101,520 compared samples:
78,714 identical, 7,014 with metadata-only changes, and 15,792 with changed
painted metrics. Every painted-metric change is in the two intended narrow
bands, at 639px or 760px. All wide painted metrics are exactly identical.
The 834 wide metadata changes comprise 494 focus-tooltip `escapePressed`
differences and 340 delete-control box changes. These are recorded individually
in [changed-samples.jsonl](changed-samples.jsonl); no wide color drift is hidden
by an aggregate tolerance. Interpretation of narrow samples remains part of
the final accepted pass.

## Initial Acceptance Failure

```bash
STATE_SHADES_EVIDENCE_DIR="$PWD/docs/qa/777-shell-ui-bundle/state-surfaces" \
  nice -n 15 npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
```

The [complete failed output](focused-ui-initial.log) reports:

```text
Test Files  1 failed | 3 passed (4)
Tests  4 failed | 119 passed (123)
Duration  48.87s
```

Two failures are stale joint-table/exception manifests after renamed fine IDs
and added coarse coverage. The three newly emitted joint tables are preserved
here, without replacing the prior accepted tables. The gradient test failed
because its two historical PNGs were LFS pointers in this checkout. Both exact
objects already existed locally and were hydrated with `git lfs checkout`;
there was no download, image modification or accepted-content change. Their
SHA-256 IDs are `30d25584b9f3cc138e48fbbbf7ce45953283a35b6de06da87b9d56aa73240f7d`
and `e806f16bde235d6279812a0c8d391a9f2bd17ba91dc444da170e6dc4361468b3`.

The fourth failure is real: `painted_mask_means_are_linear_and_interactions_are_real_and_settled`
requires the sampled SVG not to be hovered in a row-hover context. The
[receipt diagnostic](interaction-failure.json) names 108 shipped cases:
required/optional key hover at 639px, all three themes, fine/coarse pointers,
and reduce/start/trough phases. The initial suspicion of a trash-row collision
was wrong; [that empty scan](row-hover-failure.json) is retained explicitly.

## Browser Diagnosis and Approved Correction

The [bounded diagnostic](key-hover-diagnostic.mjs), [output](key-hover-diagnostic.log)
and [readbacks](key-hover-diagnostic.json) used the already built production
fixture with the same device scale and local-only transport. At 639px, both
fine and coarse inputs have a key row at `(240, 326.421875, 245, 52.5)` and its
SVG at `(352, 346.671875, 12, 12)`. Default row hover moves to `(362, 352)`;
`elementFromPoint` returns the SVG. The row and SVG are hovered; all controls
are unhovered. This is the actual failing state.

A natural mouse move to the empty row background `(242, 352.421875)` gives
`hitIsRow: true`, row hover true, SVG hover false and all controls unhovered.
At 760px, default center hover instead hits the input; a background point
`(248, 352.328125)` has the same clean row-only readback. Screenshots show the
probed background-point state. All diagnostic requests/errors are zero.

`SettingsPane.tsx`, `.settings-pane-v2`, `.set-scroller`, `.key-row` and
`.key-status` styles are unchanged from `4ae8b8d2`; the CSS diff changes only
the ordered shell rail layout. The wider narrow content shifts the key row's
center onto the glyph; this is a harness targeting issue exposed by that
layout change, not a reason to weaken the interaction assertion or redesign
Settings.

The coordinator approved targeting a verified visible background point for
key-row hover with a real mouse move, then refusing unless the hit is the row,
the row is hovered, and neither SVG nor controls are hovered. Strict tests,
color thresholds, static signatures, palette and media inventory stay intact.
That tooling edit changes the input fingerprint: all 33 conditions must be
captured again. No sample from this receipt is transplanted into the new proof.

Codex — GPT-6
