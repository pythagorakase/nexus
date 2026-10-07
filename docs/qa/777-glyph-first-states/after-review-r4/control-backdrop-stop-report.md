# After the Fourth Independent Review and the Panel: Control-Backdrop STOP-REPORT

Date: 2026-10-05. Resumed head: adeb5a6bb0d47ab23fc7543e186df680191064f2.
Reachable-inventory commit: a2d163dc. Branch: claude/777-glyph-first-states.
PR #1099 remains open. Accepted product fixes in afbb2756 remain unchanged.

**STOP:** the second clarification's exact pixel-difference mask does not
isolate the stroked SVG foreground in the real optional API-key row.
`visibility:hidden` changes background pixels as well as glyph pixels. The
mode selects background; the per-group search then reports a false key maximum
of zero for every theme. This is a new measurement premise failure, rather
than another unreachable interaction or a slow gate.

## Reproduction and Captures

The real NexusLayout, KeysSection, ModelSection and MapPane mount with the
production Vite build's emitted CSS. Captures use Chromium 153.0.8010.12,
Playwright 1.63.0 (browser revision 1243), file://, HTTP(S) aborted, DPR 4,
1200×900 default, dark scheme and reduced motion. Finite animations finish
before sampling; infinite animation variants pause at declared phases.
No provider, gateway, secret store or real data source is used.

The production row has `opacity:.5` at rest (nexus-layout.css:2143).
Native hover or focus-within restores opacity 1. The diagnostic keeps both
pseudos false, with zero running animations and devicePixelRatio 4. It captures
the same 12×12 CSS-pixel SVG bounding box as 48×48 device pixels. An injected
style hides only that SVG and its descendants, exactly as required.

All three alternating painted/hidden repetitions agree, for absent and present
glyphs in all three themes. Veil's absent capture has 1,683 background pixels
[10,15,24]. The hidden control paints all 2,304 pixels [11,16,25]. The specified
mask contains every pixel and selects [10,15,24], with a misleading 73.05% mode.
Present also selects [10,15,24], despite 395 actual stroke interior pixels
[115,106,84]. Gilded shifts [13,13,13] to [14,14,14]. Vector's scanlines produce
multiple backdrop modes, but both glyphs still select [6,12,12]. Background
drift has a larger area than the stroke.

| Theme | Absent stroke interior | Present stroke interior | Literal hidden-control mode, both states |
| --- | --- | --- | --- |
| Veil | [83,78,65] | [115,106,84] | [10,15,24] |
| Gilded | [58,52,36] | [114,105,83] | [13,13,13] |
| Vector | [31,56,58] | [51,98,102] | [6,12,12] |

Four causal diagnostic variants distinguish this from a capture-code mistake:

- Injecting an unused custom property changes zero pixels. Another screenshot,
  or merely adding a style/attribute, does not produce the drift.
- Prescribed visibility:hidden reproduces the background shift.
- Transparent fill/stroke with visibility retained keeps background unchanged
  and selects the distinct interiors above. Veil masks become 621/678 pixels,
  with modes 359/621 and 395/678.
- Temporarily making the optional row opaque, solely through a diagnostic
  injected style, prevents background drift under visibility:hidden. This
  implicates opacity compositing/raster rounding when the SVG stops painting.
  It does not authorize changing product opacity or using those captures.

Exact changed RGB pairs, all repeated histograms, pseudo/animation readbacks,
dimensions, computed strokes and diagnostic outcomes are retained in
[control-diagnostic.json](control-backdrop/control-diagnostic.json) and
[control-causality.json](control-backdrop/control-causality.json). Replay scripts,
representative original PNGs and their hashes are beside them. The full optional
keys screenshot and Veil absent painted/hidden pair were visually inspected:
the ring is visible; the hidden control is uniformly background. No tolerance,
shape mask or replacement control was silently introduced into acceptance.
An independent Pillow decode using the shared Python interpreter reproduced
all six backdrop modes and mask sizes (independent-png-check.json). The first
attempt with system python3 lacked PIL; it was rerun with the existing shared
venv. No package was installed and no Python product file was changed.

Raising the mode floor cannot fix this: Veil/Gilded background modes exceed 70%.
A fixed 2% trial floor completed the inventory (minimum mode fraction 3.4598%).
Earlier fixed 8% and 5% trials rejected real Vector rings. Those floors and
named failures are trials, not proof that changed pixels belong to the glyph.

## Reachable Inventory Implemented

Each sample records real native actions/Tab counts, matched pseudos and state
attributes, verifies DPR 4 and checks relevant animations settled.

- Remove hovered from the six sidebar contexts: rest, row-hover and
  selected-current, each fill/ring. Rest/current/selected remain in the row at
  rest and hovered; canvas hovered remains. The accepted
  [sidebar capture](sidebar-hover-context-failure.png) and
  [readback](sidebar-hover-context-failure.json) show real row hover clearing
  canvas hover: actual rest, row :hover true, pin :hover false. This follows
  the coordinator's canvas-only ruling, without inventing another action.
- Remove optional-absent from key/required/{rest,hover,focus-visible}; the
  real absent row is optional. Remove required-missing from
  key/optional/{rest,hover,focus-visible}; the real missing row is required.
  [Key readbacks](control-backdrop/key-reachability.json), with required/optional
  full-shell PNGs beside them, show the fixed requiredness classes applied by
  the production KeysSection to fixture records.
- Drop optional-absent/required-missing from the pair list: no shared
  requiredness context. Other pairs use only shared reachable contexts.
  Removed contexts/pairs are neither exceptions nor zero measurements.

The inventory now has 70 surface-state samples per phase per theme/condition,
69 shared-context pair comparisons and 13 base state pairs. Canvas sea/land,
sidebar, delete row/button hover and Tab focus-visible, required/optional key
rows, and memory normal/over remain covered.

## Full Capture and Rejected Search

Three bounded foreground batches completed baseline, shipped and candidate
captures across three themes and 18 CSS-derived conditions: **64,008 renders**
(128,016 clipped screenshots), **1269.987 seconds** summed capture wall time.
Each command completed below its 589-second bound and was awaited before more
work. Zero HTTP(S) requests and page errors occurred. Nine media preludes yielded
default, motion start/trough, and both sides of declared width boundaries.
The hash covered 2,095 transitive esbuild inputs, recursive styles, Tailwind's
complete client scan, configs, scripts, lockfile and browser versions.

Captured source fingerprint:
`f8ebb445ed2a41072d3d9661fb41c41c1fbb899486029837609ed33c569325bb`.
[capture-inputs.json](control-backdrop/capture-inputs.json) retains all input
paths/hashes. [capture-manifest.json](control-backdrop/capture-manifest.json)
retains raw scratch shard hashes, conditions, counts and timing.

The public assembler initially rejected complete theme sets because its sorted
theme string had the wrong order. A provisional manual assembly verified
identical current fingerprints/media, unique complete conditions and all three
themes, so the group search could diagnose the captures. The preserved draft
fixes this typo and writes compact combined JSON. It also stops injecting the
shipped root token inline: shipped samples must measure the real media cascade.
Those later corrections make the old shards stale; final regeneration has not
been rerun. The assembler bug is not the protocol blocker.

The search ran each group independently with Amendment-4 threshold/tie-break
and wrote all three group reports before assertions against stale tables/old
shades. These are **rejected diagnostic results**, not approved maxima or
exceptions:

| Theme | Memory maximum | Delete maximum | Map maximum | Key maximum (invalid) |
| --- | ---: | ---: | ---: | ---: |
| Veil | 48.28249625545695 | 14.897964380235265 | 10.337703127397388 | 0 |
| Gilded | 43.17542131118454 | 11.912261560702335 | 9.589052412343841 | 0 |
| Vector | 41.81549016617153 | 23.190181957030468 | 5.703309230373589 | 0 |

Assignments/coverage are retained in explicitly rejected
`*-provisional-joint.json`. No assignment was applied to product CSS; no
Amendment-4 exception, table or swatch is certified. The temporary combined
receipt was marked acceptanceComplete=false and saved in scratch, then the
checked receipt was restored byte-for-byte. It remains stale and correctly
blocks acceptance. No rejected receipt is committed as an acceptance artifact.

## Gates, Label/Halo Proof and Disposition

[commands.md](control-backdrop/commands.md) gives exact commands and verbatim
tails, including regeneration counts/timing. Its JSON companion records cwd,
exit and command wall time. Capture successes are not acceptance passes.

- Product regression command: 18 passed (StateGlyphs, MapPane, shell accessibility).
- Type/design-sync check and production build: passed.
- Owner-target guard: 80 passed; dbname audit recorded zero targets.
- Provisional state-shades: 6 passed, 2 failed against stale tables/old shades;
  its zero key maxima exposed this measurement problem.
- Required focused command after restoring the receipt: 15 passed; one suite
  rejected stale input before running state-shades tests.
- Plants, final all-UI gate, both complete offline suites and separate
  reachability were not executed on this resumed stop. No prior/partial gate
  is represented as a complete current gate. No suite is blocked by time.

Accepted prior product-proof.json remains: Gilded/Vector selected labels have
zero changed pixels; Veil's selected label has the 815-pixel mandatory anchor
correction and paints [184,61,122] exactly. All six halo-only comparisons remain
pixel-identical, with global shadows unchanged. These are retained selected-label
and halo captures, not newly completed proof for every reachable label state.
Accepted geometry, pointer handling, label mapping, halo and timer tests were
not changed.

No paid call, app/gateway service, owner service, database write, Python product
change, nexus.toml edit, migration, main-checkout edit or other-worktree edit
occurred. No rewrite, stash, rebase or PR merge. An earlier origin/main merge
reported Already up to date. No final merge/push/PR-body update is claimed while
acceptance is blocked.

`_common_codex.md:14` requires: “if honest attempts cannot satisfy a rule or a
gate, STOP and write a stop-report (what you tried, exact errors, your diagnosis).”
Its Codex-specific notes require a stop-report for a false premise rather than
improvisation. The second clarification says the hidden-control icon mask “is
the stroked path”; these captures prove otherwise for the optional row.

Coordinator question: may an SVG control retain visibility and suppress
fill/stroke paint, preserving the opacity-composited backdrop as this diagnostic
does? If so, specify treatment of own shadows/filters and media overrides for
every SVG surface and candidate. Alternatively, specify another foreground-mask
rule that rejects these backdrop pixels. No product opacity change is proposed.
All captures/search/plants/acceptance evidence then need regeneration. The
asynchronous ruling request remains unanswered.

Codex, GPT-6.
