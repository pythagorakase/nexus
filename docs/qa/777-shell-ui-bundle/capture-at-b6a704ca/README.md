# Complete V2 Capture, Failed Acceptance

This is retained failed evidence, not an accepted application receipt. Capture
input was `b6a704caab86c304590785832b665fa98a12ef1c`, tree
`ef6f9396160b343d82b6ac0f996862cd4513a704`, fingerprint
`4b8a9bbd8b880dc12ff8a534e7ef819eaa72fe376f0e28a8a295f9754d976fe7`.
All nine bounded runs used `nice -n 15`, a one-minute load below 24, Chromium
153.0.8010.12 and Playwright 1.63.0. Each completed with all calibration groups
passing and zero HTTP requests/page errors. See [commands](commands),
[assembly log](assemble.log), [input closure](inputs.json), and
[manifest, receipt/image hashes and delta disposition](capture-manifest.json).

| Batch | Captures | Wall seconds |
| --- | ---: | ---: |
| 1 | 15,262 | 375.385 |
| 2 | 15,262 | 389.006 |
| 3 | 15,262 | 390.243 |
| 4 | 15,262 | 389.004 |
| 5 | 15,262 | 387.732 |
| 6 | 15,262 | 383.604 |
| 7 | 15,262 | 382.644 |
| 8 | 15,262 | 393.912 |
| 9 | 3,982 | 368.997 |

Assembly verified 33 unique complete conditions: 27 legacy fine-pointer
conditions plus six new coarse-pointer conditions, over 22 media vectors.
The 126,078 captures include each batch's calibration. The exact unmodified
[receipt](receipt.json) has SHA-256
`7033fa0f402dac6837a9577a677c30142e74112f36f52e5714cfdbe239e0fb5a`.
Its `acceptanceComplete` flag describes complete inventory assembly; the
subsequent strict tests below failed. The 444 calibration PNGs in
[calibration](calibration) are the image pairs referenced by its retained
batch-1 calibration. All original shards remain at the recorded scratch paths;
their hashes are in the manifest.

## Complete Comparison and Hover Correction

The [explicit old/new condition mapping](legacy-condition-map-v2.json) and
[comparator](compare-receipts-v2.py) cover all 101,520 legacy samples, including
shipped, before and every candidate value: 71,952 identical stable records,
13,776 metadata-only changes, and 15,792 painted-metric changes. Every painted
change is at 639px or 760px, where the approved shell layout changes geometry.
All wide painted metrics are exact. Wide records are not all JSON-identical:
corrected background targeting changes key-row child hover metadata; whether
Escape was needed differs; some delete glyph origins differ while their size
and painted metrics remain exact. The manifest classifies these differences;
[every changed sample and field](changed-samples.jsonl) is retained.

The exact committed hover helper passed all [72 browser cases](hover-micro.json)
at 639px fine/coarse, 760px and 1200px. A partial batch-1 diagnostic retained
the original interaction/same-value assertions: two passed, nine deliberately
unselected ([log](shard-interactions.log)). This was not complete acceptance.
The final focused run passed those same checks over the entire inventory.

## Actual Acceptance Failure

[Initial focused acceptance](focused-ui-initial.log): 121 passed, two failed
in 64.88s. The old measurement tables and exception IDs were stale. The three
tables here are the exact evaluator emissions. A temporary external refresh
copied those bytes and derived exceptions from measured rows, preserving all
rules. [The refresh record](manifest-refresh.json) shows no new legacy fine
exceptions: Veil retained 223, removed six, added 52 coarse; Gilded retained
763, removed three, added 172 coarse; Vector retained 1184, removed three,
added 266 coarse. This is not color acceptance.

**The agent's preliminary all-group-pass inference was wrong.** It read
`factorMaxima.shippedMinimum`, which `jointSearch` fills from the selected
candidate assignment, not actual shipped CSS. The initial run stopped at the
Veil manifest mismatch and had not reached later themes. The inference is
withdrawn; [actual measured minima](actual-scalar-audit.json) are authoritative.

[Full UI run](full-ui.log): **606 passed, five failed, two uncaught errors**,
34 files passed/five failed, 59.82s. Four wizard/ContinuePage failures and both
uncaught errors use Framer Motion's legacy `matchMedia(...).addListener`, absent
from the new jsdom fallback. The authorized repair is two no-op legacy listener
methods; it changes the hashed test input and therefore requires fresh capture.

The fifth failure is Gilded/map's strict exact-optimum rule: actual minimum
7.4977986569476665 versus newly available maximum 7.709657692104731. Its
1023px canvas-sea/ring rest/current RGB pair is byte-identical to legacy.
The changed narrow geometry removes a former candidate bottleneck. Replaying
the retained means through unchanged production color math establishes:

| Receipt | Map palette | Minimum |
| --- | --- | ---: |
| Legacy | Existing | 7.4977986569476665 |
| Legacy | Proposed Gilded rest token | 7.284937187310594 |
| V2 | Existing | 7.4977986569476665 |
| V2 | Proposed Gilded rest token | 7.709657692104731 |

The former bottleneck was 639px canvas-sea/ring rest/hovered. The proposed
V2 palette's bottleneck is 1280px sidebar selected/hovered across start/trough
phases. See [exact candidate witnesses](gilded-map-candidate-diagnosis.json).

A complete [chosen-versus-shipped audit](chosen-vs-shipped-audit.json) checks
all 2,673 pair measurements per theme, exposing the later equality assertion
masked by Gilded's failure: Veil has zero differing rows, Gilded 924, Vector
792. Vector's optimum is unchanged but its chosen hovered token differs.
The [raw diagnostic](diagnose-gilded-map.mjs) was executed at the recorded b6a
input with the active V2 receipt; its `git show HEAD` and scratch paths must
be interpreted at that exact execution context, not the later evidence commit.

## Unapproved Two-Token Proposal

The frozen no-new-color scope conflicts with strict optimality under the new
geometry. No palette or acceptance-rule change has been made or approved.
Exactly two existing tokens are proposed; their hues remain unchanged:

| Theme/token | Existing | Proposed |
| --- | --- | --- |
| Gilded `--state-map-rest` | `hsl(30 60% 60%)` | `hsl(30 70% 50%)` |
| Vector `--state-map-hovered` | `hsl(190 90% 40%)` | `hsl(190 80% 40%)` |

[Eight browser screenshots and readbacks](palette-proposal/readings.json)
use scratch-document CSS overrides only, with the same synthetic map,
selection, hover, geometry and animation phase before/after. HTTP is blocked,
requests/errors are zero, and the owned browser closed. This is a visual
proposal, not accepted color proof. The first two attempts stopped before any
reading (collapsed zone; state attribute read on the wrapper instead of its
glyph); their exact scripts/logs and empty readbacks are preserved there.

| Scene | Existing | Proposed |
| --- | --- | --- |
| Gilded 1023px | [Before](palette-proposal/gilded-1023-motion-start-before.png) | [After](palette-proposal/gilded-1023-motion-start-proposed.png) |
| Gilded 1200px | [Before](palette-proposal/gilded-1200-normal-before.png) | [After](palette-proposal/gilded-1200-normal-proposed.png) |
| Vector 1023px | [Before](palette-proposal/vector-1023-motion-start-before.png) | [After](palette-proposal/vector-1023-motion-start-proposed.png) |
| Vector 1200px | [Before](palette-proposal/vector-1200-normal-before.png) | [After](palette-proposal/vector-1200-normal-proposed.png) |

The unaccepted active receipt and external tables were restored to their
previous committed content after exact preservation here. No failed artifact
is presented as the accepted application receipt. Owner disposition, the
minimal jsdom repair, ordinary-UI preflight, a new complete capture and final
acceptance remain outstanding. No owner database, model or service was touched.

Codex — GPT-6
