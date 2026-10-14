# Shell UI Continuation Verification

Work order: 777-UI (777-S1b, S3, S4, then #1102). The isolated managed
worktree starts at `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8` on branch
`codex/777-shell-ui-bundle`. This evidence is in progress; only completed
checks below are claimed.

## Source and Component Review

The live #777 owner ruling and recorded Q6/Q7/Q8 decisions still match the
frozen order. #1102 remains open. The original defects remain in the base:
the announcer repeats a durable failure already sent through the toast and
never clears its text; map view state belongs to the unmounted pane; the
760px CSS keeps the side rail; Radix receives the row's internal blur.

Before adding UI elements, reviewed the official shadcn
[Navigation Menu](https://ui.shadcn.com/docs/components/radix/navigation-menu),
[Tabs](https://ui.shadcn.com/docs/components/radix/tabs),
[Drawer](https://ui.shadcn.com/docs/components/radix/drawer), and
[Sheet](https://ui.shadcn.com/docs/components/radix/sheet) pages and the vendored
components. Navigation Menu supplies flyout navigation; Tabs introduces a
tablist and panel contract. Drawer and Sheet supply overlays; the vendored
mobile Sidebar also uses Sheet. The recorded solution preserves the existing
LeftRail's buttons and labels and changes its placement and styling. None of
these components fits that change, so no new navigation element is required.

## Initial Red Proof

The shared Python import resolves inside this worktree. Commands use
`nice -n 15`; the one-minute load before the initial run was below 4.
`npm --prefix ui ci` completed and installed the lockfile's dependencies in
this worktree ([log](npm-ci.txt)). No dependency upgrade is included.

New tests were written before S1b product changes:

```text
nice -n 15 npm --prefix ui test -- TopBar NexusLayout.announcer
Tests  3 failed | 18 passed (21)
```

The [UI red log](s1b-ui-red.txt) demonstrates the duplicate durable-failure
announcement, a toasted failure that still speaks, and the message remaining
after the configured hold.

```text
env -u NEXUS_RUN_LIVE_LLM -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL \
  -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 \
  /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit \
  tests/test_config/test_ui_settings.py tests/test_api/test_ui_config.py
3 failed, 7 warnings in 0.69s
```

The [Python red log](s1b-python-red.txt) fails on the absent announcer settings,
route module, and route capability. Guard summary: secret store active with
`nexus-api` and disposable keychain denied; checkout and user receipts untouched;
zero database targets and no owner targets. The reported unaudited C-level
replication class is the documented audit limitation.

## Completed Behavioral Proof

The first remaining-slice run distinguished missing primitive imports from the
tooltip behavior: the context/hook modules were not yet present, while the
real tooltip test failed immediately after the synthetic internal `focusOut`.
See [missing-primitives log](primitives-missing-red.txt).

After adding the context primitive but before moving state or wrapping the
layout, the [S3 behavioral red](s3-behavioral-red.txt) showed the viewBox
resetting from the retained zoom to the default canvas, and the layout lacking
its required map owner. The narrow DOM-order assertion was also red. One
source-edit helper then refused an incorrect import anchor before changing any
file; an accidentally chained test repeated the same red result, preserved in
[its separate log](s3-repeat-red-after-edit-refusal.txt).

After the S3 wiring, all map tests and mounted-owner checks passed, with only
the still-unimplemented narrow order failing
([S3 green/S4 red](s3-green-s4-red.txt)). The hook primitive then allowed the
[S4 CSS red](s4-css-red.txt) to demonstrate both missing responsive rules.
S1b/S3/S4 passed all 42 tests before the tooltip component changed
([log](s1b-s3-s4-ui-green.txt)).

After the ordered tooltip blur fix:

```text
nice -n 15 npm --prefix ui test -- TopBar NexusLayout MapPane LocalModelRows \
  shell-accessibility StateGlyphs RightLedger ReturnRecapCard NarrativePane
Test Files  12 passed (12)
Tests  137 passed (137)
```

[Focused UI output](focused-ui-green.txt) includes all existing map geometry,
reader draft, glyph, recap, and ledger consumers. The same three new Python
tests then passed: **3 passed, 7 warnings in 2.36s**; active secret guard,
untouched receipt roots, and zero database/owner targets
([Python green](s1b-python-green.txt)).

## Source Freshness

Reverified AGENTS and the turn-flow document: the added display route, setting,
and toast-reporting field do not change turn orchestration or acceptance.
Reverified decision records 0008, 0009, 0010, 0024, 0034, 0051, 0052, and
0054. The clock, token accounting, seat choice, storage, correspondence, time
lens, and map rulings remain intact; the bottom rail implements the recorded
shell ruling. Only these ten `verified_commit` values move to the merge base.
Every decision quotation, status, and body stays unchanged. Record 0054 adds
exactly `NexusLayout.tsx` and `hooks/useNarrowShell.ts` to its source list:
these now own the responsive rail's DOM placement and breakpoint alongside
the existing CSS. No other decision source list changes.

## Broader Python and Static Proof

The load before this run was 4.35 and the import again resolved to this
worktree's `nexus/__init__.py`.

```text
env -u NEXUS_RUN_LIVE_LLM -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL \
  -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 \
  /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit \
  tests/test_api/test_ui_config.py tests/test_config \
  tests/test_api/test_route_capabilities.py tests/test_api/test_preferences.py \
  tests/test_api/test_settings_endpoints.py tests/test_orrery/test_card_identity.py \
  tests/test_connection_lifecycle.py tests/test_reachability.py \
  tests/test_doc_front_matter.py
286 passed, 2 skipped, 7 warnings in 72.38s (0:01:12)
```

The [full output](broad-python.txt) confirms active secret-store isolation,
untouched checkout/user receipt roots, and no owner database targets. The
two skips are the corpus-only synchronous/asynchronous card exposure cases;
all ordinary PostgreSQL cases ran, including the disposable two-cluster
connection lifecycle. The audit names `save_04` only on its two registered
disposable servers, not on the owner server.

Black checks all six changed Python files without changes. Flake8 has 53
pre-existing diagnostics, and mypy has nine on unchanged lines of
`narrative.py` and `settings_models.py`; neither reports a diagnostic on an
added file or changed line. The commands select these files:

```text
nexus/api/narrative.py nexus/api/route_capabilities.py
nexus/api/ui_config_endpoints.py nexus/config/settings_models.py
tests/test_api/test_ui_config.py tests/test_config/test_ui_settings.py
```

Each uses `PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m`
followed by `black --check`, `flake8`, or `mypy --explicit-package-bases`.
The [comparison](static-comparison.txt) matches diagnostic path, exact source
line, and text against main. Logs: [Black](black.txt),
[branch flake8](flake8.txt), [main flake8](flake8-main.txt),
[branch mypy](mypy-branch-full-context.txt), [main mypy](mypy-main.txt).
The comparison reports zero new diagnostics. Main's archived full source
context also reports 275 unrelated imported-module diagnostics. An initial
partial archive lacked that context and is preserved separately as
[non-comparable output](mypy-main-incomplete-context.txt); it was replaced
by the full `nexus`, `scripts`, and `tests` archive. Branch mypy was repeated
with `--no-incremental`, again yielding the same nine diagnostics.

`nice -n 15 /Users/pythagor/nexus/.venv/bin/python -S
scripts/check_exception_dispositions.py --baseline-base-ref origin/main`
passes ([output](exception-dispositions.txt)).

The [initial TypeScript check](ui-check-initial.txt) caught one new test-only
inference error: an expression-bodied `act` returned `setQueryData`'s value.
The test now uses an explicit `CurrentPlace[]` update inside a void block;
the production code did not need repair.

## Type, Build, and Rendered Mobile Proof

Both `nice -n 15 npm --prefix ui run check` and the identical command on the
archived `origin/main` UI pass with no TypeScript or design-preview diagnostics
([branch](ui-check.txt), [main](ui-check-main.txt)). The baseline had its own
lockfile installation ([log](npm-ci-main.txt)); no dependency directory was
shared. `nice -n 15 npm --prefix ui run build` passes in 2.65 seconds, including
PWA generation ([log](ui-build.txt)). Existing dependency age, eval, and large
chunk warnings remain unchanged in scope.

The [scratch mobile script](mobile-proof.mjs) runs Chromium against the trace's
production fixture, at 390×844 with touch and mobile emulation. It verifies
the viewport meta before capturing: `innerWidth=390`, `innerHeight=844`, and
the narrow/coarse media query is true. Both navigation boxes are
`x=0, y=796, width=390, height=48, bottom=844`, and both follow `main` in the DOM.
Focusing a `.key-row input` changes navigation display to `none`; blur returns
it to `flex`. No key was entered or submitted. No HTTP request or page error
occurred. See [readbacks](narrow-readback.json), [output](mobile-proof.txt),
[map accessibility tree](narrow-map-accessibility.txt), and
[settings accessibility tree](narrow-settings-accessibility.txt).

![Map at 390×844](narrow-map.png)

![Settings at 390×844](narrow-settings.png)

The settings screenshot visibly clips its inner content. Its governing layout
is unchanged from `4ae8b8d2`: `SettingsPane.tsx` is byte-identical, as are the
`.settings-pane-v2` `240px 1fr` grid, `.set-rail`, and `.set-scroller` rules
(the latter retains 48px horizontal padding), with no narrow settings override.
This proof establishes the ordered shell rail behavior; it does not claim
that all settings content is usable at this width. No extra settings redesign
is included.

## Tooltip Trace Precondition Correction

The literal first trace failed: **0/50 row open, 50/50 trash open, 50/50 outside
closed**, with zero HTTP requests and page errors
([output](trace-initial.txt), [per-run readings](tooltip-focus-trace-initial.json)).
It is retained as failed evidence, not replaced by the later run.

A separate [observational diagnostic](trace-diagnostic.mjs) captured this
actual event order while the row remained focused:

```text
268.8ms: row receives focus
272.0ms: row data-state changes to instant-open
276.7ms: containing .set-scroller scrolls from 523px to 527px
278.5ms: row data-state changes to closed
```

The [full event trace](trace-scroll-diagnostic.json) and
[tail](trace-scroll-diagnostic.txt) distinguish this from internal blur.
Radix Tooltip's existing capture-phase ancestor scroll handler calls
`onClose`; natural Tab auto-scroll reaches that handler. The ordered internal
blur change does not override Escape or scroll dismissal.

The coordinator approved a bounded test precondition correction: while the
immediately preceding family toggle is focused, scroll the row fully into
view and settle its actual scroll position, then continue with real Tab and
the original three single-read assertions. The trace records the precondition
geometry and focus for every run, and verifies that the scroller position at
row and trash readings still equals the settled precondition. It never polls
for an expected tooltip state
and does not change product behavior. Its scope is focus transitions in a
stationary viewport; natural Tab auto-scroll remains a dismissal. The resolver
README now states that limitation explicitly.

The first implementation of that precondition used Playwright's
`scrollIntoViewIfNeeded`, but failed the strict full-visibility assertion before
any completed reading. Its [aborted log](trace-precondition-initial.txt) and
[empty reading set](tooltip-trace-precondition-initial.json) remain preserved.
The final runner uses explicit native instant center-scroll, still while the
preceding toggle owns focus, then verifies two stable scroll frames and bounds.

```text
STATE_SURFACES_SCRATCH=<scratch>/trace-stationary-green-v2 nice -n 15 \
  node ui/scripts/state-surfaces/tooltip-focus-trace.mjs
Tooltip focus trace: 50/50 row open; 50/50 trash open; 50/50 outside closed
```

The [passing trace](trace-green.txt) and [all 50 readings](tooltip-focus-trace.json)
include identical precondition/row/trash scroll positions, zero page errors,
and zero HTTP requests. No expected tooltip state is polled.

Removing only the new internal `onBlur` handler and running the same trace
also produced **50/50, 50/50, 50/50**, exit zero
([output](trace-red.txt), [readings](tooltip-focus-trace-control.json)). This
browser control is therefore **not discriminating** in this run. The separate
`focusOut(row, { relatedTarget: trash })` component test is the discriminating
regression: its original pre-fix failure is in
[the initial log](primitives-missing-red.txt). The component was restored
byte-for-byte, verified by matching SHA-256 values
([restoration receipt](trace-control-restoration.json)).

After restoration and the test-only type repair:

```text
nice -n 15 npm --prefix ui test -- MapPane LocalModelRows
Test Files  2 passed (2)
Tests  25 passed (25)
```

See [restored focused output](restored-ui-green.txt). The original full focused
137-test pass remains above; this rerun covers both the repaired test and the
restored control subject.

## Historical Pause Checkpoint

The coordinator's assembled core gate at `849eeef4` stopped with 3,685 passes,
52 skips, 30 warnings and one failure in 1840.34 seconds. All three guard
summaries passed; the API and Orrery pieces were not started. The sole
prompt-lint failure was the new endpoint's developer docstring beginning “Return
only,” which the existing embedded-prompt heuristic rejects. The docstring now
says “Serve the player client's explicitly allowlisted display tunables.”
No runtime statement, lint rule or exemption changed. The bounded follow-up:

```text
env -u NEXUS_RUN_LIVE_LLM -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL \
  -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 \
  /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit \
  tests/test_prompt_lint.py tests/test_api/test_ui_config.py
24 passed, 7 warnings in 12.63s
```

The [output](prompt-lint-endpoint-fix.txt) confirms active secret isolation,
untouched receipt roots, zero database targets and no owner targets. The
combined gate was incomplete at this checkpoint. At the user's packing-up request, no new
capture, build or full suite was started; the prepared capture plan remains
pending.

The new configuration key is `[ui.announcer].hold_ms`, shipped as 5000 and
required, strict, and bounded to 1000–60000. The player route returns only its
explicitly allowlisted announcer object. The reachability baseline adds exactly
one sorted path, `nexus/api/ui_config_endpoints.py`.

At that checkpoint, the complete bounded state-surface regeneration and full UI suite remained.
The coordinator owns the
combined full gate and PR publication; no push or PR is claimed here.

## Resumed Gate and Capture Checkpoint

After the user resumed the campaign, the coordinator's serial PostgreSQL gate
passed at `2cc9a5fcff76e0c643ca41490eb2508b870b4850`, tree
`3804225e54624e7739c6f6d143cc00b804892a3b`, including this lane's input
`149704d16fa126b8ac9d142a22bf51b42a669552`: 7,056 passed, 72 skipped,
41 warnings, with all three guard summaries clean. This is coordinator-run
Python evidence, recorded at the immutable
[gate verification](https://github.com/pythagorakase/nexus/blob/bf229051e3d046b76ab8d18b34e9ee054a03bbf6/docs/qa/resume-wave-a-2026-10-08/verification.md).
It does not replace the UI acceptance proof.

All nine bounded captures at that source completed and assembled, but the
strict UI run found a narrow key-row hover targeting failure: 119 passed,
four failed. The [preserved capture checkpoint](capture-at-149704d1/README.md)
contains the exact LFS receipt, all logs, 27-condition legacy comparison,
108-case interaction diagnosis, and bounded browser geometry/hit-test proof.
The failed receipt is not the accepted application receipt. Historical PNG
fixtures were hydrated from their already-present local LFS objects.

The approved harness correction moves the pointer to verified empty key-row
background and fails on absent geometry or an incorrect hover readback.
No product source, strict assertion, threshold, palette or media evaluator
changes. At that checkpoint, the tooling change required a new complete capture,
comparison, focused acceptance and full UI run, and the coordinator temporarily
owned the heavy slot for the next lane's initial red proof.

## V2 Capture and Current Acceptance Stop

The complete second pass at `b6a704caab86c304590785832b665fa98a12ef1c`
assembled 126,078 captures across all 33 conditions at fingerprint
`4b8a9bbd8b880dc12ff8a534e7ef819eaa72fe376f0e28a8a295f9754d976fe7`.
Every calibration passed, with zero network requests or browser errors.
All 101,520 legacy samples were compared: 71,952 identical stable records,
13,776 metadata-only changes and 15,792 painted changes, all at narrow widths.
Wide painted metrics are exact; hover/dismissal metadata and some delete
origins differ. The [complete retained checkpoint](capture-at-b6a704ca/README.md)
names every changed sample and preserves the receipt, calibration images,
logs, table refresh, diagnostics and before/after proposal images.

Full UI acceptance failed: **606 passed, five failed, two uncaught errors**.
Four wizard failures expose missing legacy listeners in the new jsdom
`matchMedia` fallback. The other failure is a genuine strict-optimality
conflict: Gilded's unchanged actual map minimum remains 7.4977986569476665,
while the changed narrow layout makes 7.709657692104731 attainable in the
existing candidate domain. A later chosen-versus-shipped check also requires
a different Vector hovered token. The preliminary inference that all scalar
bounds passed mistakenly relied on selected-assignment metadata; that claim
is withdrawn and the actual measured audit is retained.

Historical at `c8a72061` (superseded by the Palette Disposition section
below): exactly two existing color-token changes were proposed through
scratch-only browser previews. Authorization was then pending, and the
product palette, evaluator, thresholds and input closure rules were unchanged
at that commit. The failed active receipt/tables were restored after exact
evidence preservation. Final capture, full UI acceptance, main merge,
freshness and final Python-source provenance were then pending, and the
branch was not publication-ready.

The [minimal legacy-listener repair](matchmedia-legacy-repair/README.md) is now
committed and verified at `772dd499ed5cd00e5ceb5c2577efa428eb8866f8`:
all four previously affected UI files passed, 77 tests in 5.17s, with no uncaught
errors. Its new fingerprint changes only `client/src/tests/setup.ts`; no old
capture is reused. At `3258c5b3` the palette decision and remaining acceptance
work above were still pending; the coordinator's commit `7eb9a10c` later
applied the palette (see Palette Disposition below), and the acceptance work
remains the coordinator's step on the final wave-B UI union.

Codex — GPT-6

## Palette Disposition (Coordinator, 2026-10-09)

The coordinator's commit `7eb9a10c` applied exactly the two token moves that
the V2 joint search chose, and no other color change:

| Theme/token | Before | Shipped since `7eb9a10c` |
| --- | --- | --- |
| Gilded `--state-map-rest` | `hsl(30 60% 60%)` | `hsl(30 70% 50%)` |
| Vector `--state-map-hovered` | `hsl(190 90% 40%)` | `hsl(190 80% 40%)` |

Both hues are unchanged; only saturation and lightness move inside each hue
family. Veil is untouched. The shipped values are
`ui/client/src/index.css:684` and `:831`; they equal the V2 joint assignments
at [gilded-joint.json:26](capture-at-b6a704ca/gilded-joint.json) and
[vector-joint.json:29](capture-at-b6a704ca/vector-joint.json). The Gilded map
group's V2 search choice reaches minimum `7.709657692104731`, against
`7.4977986569476665` for the previous palette
([gilded-map-candidate-diagnosis.json](capture-at-b6a704ca/gilded-map-candidate-diagnosis.json),
entry `receipt: v2`, `palette: new_search_choice`).

Authorization: the #1099 rule is unchanged. The strict exact-optimum assertion
(`ui/client/src/state-shades.test.ts:578-580` on this tree: a reachable group
must reach 15, an unreachable group must equal the search's best, and the
shipped minimum must equal the selected assignment's) and the assignment
equality at `:583` require the shipped palette to be the search's choice. The
coordinator recorded that decision on #777:
<https://github.com/pythagorakase/nexus/issues/777#issuecomment-6076985289>
(2026-10-09 03:05 CDT). No separate owner ruling is cited. The
"Unapproved Two-Token Proposal" section of
[capture-at-b6a704ca/README.md](capture-at-b6a704ca/README.md) and the
stale-palette passages above are historical records of the state before
`7eb9a10c`.

The two shipped values have not yet been painted as shipped CSS in any receipt.
Their only measured support is the V2 candidate samples captured at
`b6a704ca`. The committed browser-resolved receipt
(`ui/client/src/state-surfaces.resolved.json`, LFS oid `70925b79…`) is
intentionally stale until the single regeneration on the final wave-B UI union.
That regeneration and its acceptance run are the measured proof. Its refresh of
the three joint tables, `theme-exceptions.json` and
`docs/qa/777-glyph-first-states/amendment-2/state-tokens.md` is part of the same
step. That reference still lists the old values at `:19` and `:34`. The full
capture, the state-shades acceptance and the full `npm --prefix ui test` with
state-shades green are the coordinator's step.

## Integrated-Tree Proof (2026-10-13)

Every command below ran on `a563203a` (the integration head with nine lane
fixes merged; its `ui/` tree is byte-identical to `7eb9a10c`:
`git diff --stat 7eb9a10c a563203a -- ui/` is empty). This fix's uncommitted
edits were present: the README wording, the heading case, the parameterized
hover script and this file. None is a vitest, build or state-surface input
(`ui/scripts/state-surfaces/inputs.mjs` hashes `.mjs`, `.tsx` and `.css` under
`scripts/state-surfaces/`, not its README). Every test, build and Chromium
command ran under `nice -n 15`. The one-minute load read 2.86 to 10.26 before
each run and never reached 24, so no wait loop was needed. `<scratch>` is
`scratchpad/fix-waveb-r3-777-capture` of the session scratchpad. The Python
import resolved to this worktree's `nexus/__init__.py`.

The canonical documents' `verified_commit` stamps were moved to `f073b371` by
the assembly. The Source Freshness section above describes the lane's original
move from `4ae8b8d2`.

### Dependencies and Focused UI Tests

```text
nice -n 15 npm --prefix ui ci            # exit 0
nice -n 15 npm --prefix ui test -- TopBar NexusLayout MapPane LocalModelRows \
  shell-accessibility StateGlyphs RightLedger ReturnRecapCard NarrativePane
 Test Files  12 passed (12)
      Tests  137 passed (137)
```

### Full UI Suite (State-Shades Stale by Design)

```text
nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 40 passed (41)
      Tests  632 passed (632)
```

The sole failure is the expected stale receipt. This lane's `index.css`,
`tests/setup.ts` and `resolve-state-surfaces.mjs` changes, and other wave-B
UI lanes, are in the hashed closure. Regeneration is the coordinator's step.
`npm --prefix ui run resolve-state-surfaces` was not run.

### Type Check and Build

```text
nice -n 15 npm --prefix ui run check     # exit 0: tsc, then check:design-sync (tsc -p .design-sync/tsconfig.previews.json), no diagnostics
nice -n 15 npm --prefix ui run build     # exit 0
PWA v1.0.3
mode      generateSW
precache  22 entries (2322.18 KiB)
```

The branch check reports no diagnostics, so the comparison with `origin/main`
cannot show a new one. The `origin/main` check was not rerun.

### Tooltip Focus Trace and Its Plant

```text
STATE_SURFACES_SCRATCH=<scratch>/trace nice -n 15 \
  node ui/scripts/state-surfaces/tooltip-focus-trace.mjs     # exit 0
Tooltip focus trace: 50/50 row open; 50/50 trash open; 50/50 outside closed
```

Plant: the item 16 `onBlur` handler was deleted from
`ui/client/src/components/nexus/LocalModelRows.tsx` (lines 370-376, seven
lines). Then:

```text
nice -n 15 npm --prefix ui test -- LocalModelRows           # exit 1
   × exceeds-RAM tooltip > stays open as focus moves from the row to its trash button 56ms
 Test Files  1 failed (1)
      Tests  1 failed | 19 passed (20)
STATE_SURFACES_SCRATCH=<scratch>/trace-plant nice -n 15 \
  node ui/scripts/state-surfaces/tooltip-focus-trace.mjs     # exit 0
Tooltip focus trace: 50/50 row open; 50/50 trash open; 50/50 outside closed
git checkout -- ui/client/src/components/nexus/LocalModelRows.tsx
git diff --quiet -- ui/client/src/components/nexus/LocalModelRows.tsx && echo restored-diff-quiet
restored-diff-quiet
shasum -a 256 ui/client/src/components/nexus/LocalModelRows.tsx
c99c3df1f8ffab69bb021229992699ba2b5ea5f824a52b8a889a3a3d94cac799   (identical before the plant)
nice -n 15 npm --prefix ui test -- LocalModelRows           # exit 0
 Test Files  1 passed (1)
      Tests  20 passed (20)
```

As at `4ae8b8d2`, the browser trace does not discriminate: it reaches 50/50/50
with the plant in place. The `focusOut` vitest case does discriminate.

### Trace README Passage

`ui/scripts/state-surfaces/README.md` keeps the stationary-viewport
precondition that the coordinator ratified, in place of item 17's ordered
wording. Checked against
`ui/scripts/state-surfaces/tooltip-focus-trace.mjs` and the scroll diagnostic
above, the passage was accurate on these points:

- The trace scrolls the row into view and waits for scrolling to settle while
  the preceding toggle has focus.
- It asserts that the scroller position at the row and trash readings equals
  that precondition.
- It takes one reading per focus position and never polls.

One point was only implied: "not persistence through natural Tab auto-scroll"
did not say what happens under auto-scroll. The passage now says that the
trace proves focus transitions in a stationary viewport only, and that natural
Tab auto-scroll is ancestor scrolling and so still dismisses the tooltip. The
passage has no heading. The file's only H1, "Painted Core-Mean Oracle", is
already in Chicago title case.

### Narrow-Width Proof

The lane's `mobile-proof.mjs` hard-codes a Codex worktree. A scratch copy
takes the root, the output directory and the fixture as arguments, and
changes nothing else
([script](integrated-proof/mobile-proof-integrated.mjs)). It ran on the trace's
fixture, which carries the viewport meta:

```text
nice -n 15 node <scratch>/mobile/mobile-proof-integrated.mjs <worktree> \
  <scratch>/mobile <scratch>/trace/fixture.html             # exit 0
390x844 coarse/mobile: map and settings bottom rail, DOM order, focus hiding and blur restoration passed
```

The readback shows `innerWidth` 390 with the narrow coarse query true. Both
navigation boxes are `x=0, y=796, width=390, height=48, bottom=844` and follow
`main`. Display is `none` while a key input has focus and `flex` after blur,
with zero errors and zero requests
([readback](integrated-proof/narrow-readback.json)).

The map screenshot is byte-identical to the lane's `narrow-map.png` (LFS oid
`bbac9a16…`). The settings screenshot
([integrated](integrated-proof/narrow-settings.png)) differs from the lane's
copy only in the clipped settings scroller's inner scroll offset. The rail,
its readback and both accessibility trees are identical.

### Key-Row Hover Helper (Parameterized, with Planted Refusals)

[key-hover-micro-v2.mjs](capture-at-b6a704ca/key-hover-micro-v2.mjs) now takes
its repository root from `argv[2]`, defaulting to its own checkout, and its
output directory from `STATE_SURFACES_SCRATCH`. It builds the fixture with
`fixtureBuild` and the production Vite CSS, as `tooltip-focus-trace.mjs`
does. It drives both of the helper's throw branches with planted cases: a
full-viewport overlay, and a page whose mouse move lands on the sampled glyph.

```text
STATE_SURFACES_SCRATCH=<scratch>/hover-micro nice -n 15 \
  node docs/qa/777-shell-ui-bundle/capture-at-b6a704ca/key-hover-micro-v2.mjs   # exit 0
72/72 production-helper row hover cases passed: 639 fine/coarse, 760 fine, 1200 fine; 3 themes; 2 needs; 3 states.
Old center hit hovered the SVG in 36/72 cases; corrected point in 0/72. Network 0; page errors 0.
Planted 639/coarse/full-cover-overlay: refused: Measurement failure [data-testid="key-row-present"]: no visible empty row background for hover
Planted 639/coarse/hovered-glyph-readback: refused: Measurement failure [data-testid="key-row-present"]: row background hover mismatch {"point":{"x":242,"y":409.171875},"hitIsRow":true,"rowHover":true,"glyphHover":true,"controlHover":false}
Planted 1200/fine/full-cover-overlay: refused: Measurement failure [data-testid="key-row-present"]: no visible empty row background for hover
Planted 1200/fine/hovered-glyph-readback: refused: Measurement failure [data-testid="key-row-present"]: row background hover mismatch {"point":{"x":379,"y":456.9375},"hitIsRow":true,"rowHover":true,"glyphHover":true,"controlHover":false}
```

The helper hash `c1480b36…` equals the one recorded at `b6a704ca`
([log](integrated-proof/hover-micro.txt),
[readings and refusals](integrated-proof/hover-micro.json)). The script exits
non-zero if a planted case is accepted.

### Python

```text
env -u NEXUS_RUN_LIVE_LLM -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL \
  -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 \
  /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit \
  tests/test_api/test_ui_config.py tests/test_config \
  tests/test_api/test_route_capabilities.py tests/test_api/test_preferences.py \
  tests/test_api/test_settings_endpoints.py tests/test_orrery/test_card_identity.py \
  tests/test_connection_lifecycle.py tests/test_reachability.py \
  tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 7 targets: postgres, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_offline_gate_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:52060 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:52061 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:52060 (psycopg2), save_04@local:52061 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
286 passed, 2 skipped, 7 warnings in 73.53s (0:01:13)
```

The offline suites ran as three sequential pieces, each under
the ten-minute bound, with the same `env -u ...` prefix, without
`NEXUS_RUN_POSTGRES`, and with `-p tests.dbname_audit`. Every tail shows
`secret-store guard: active; nexus-api: denied` and `owner targets: none`.
Skips are the PostgreSQL cases, which the focused set above runs:

```text
... pytest -q -p tests.dbname_audit tests --ignore=tests/test_api --ignore=tests/test_orrery
3197 passed, 677 skipped, 8 warnings in 594.34s (0:09:54)
... pytest -q -p tests.dbname_audit tests/test_api
549 passed, 339 skipped, 7 warnings in 30.93s
... pytest -q -p tests.dbname_audit tests/test_orrery
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
1 failed, 1363 passed, 1189 skipped, 2 warnings in 12.35s
```

That one failure is outside this lane. Its tail:
`Regex: 'without birth-role policies.*ate'` against
`Value error, claim_event_types contains event types emitted by background
branches: ['ate']`. The background-branch validator now fires before the
birth-role message that the test matches. The 809 and 784 lanes' evidence
already records it
(`docs/qa/809-typed-readers/verification.md:349`). It is reported to the
coordinator and not fixed here.

Static checks on the six Python files that the lane changed:

```text
PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black --check \
  nexus/api/narrative.py nexus/api/route_capabilities.py nexus/api/ui_config_endpoints.py \
  nexus/config/settings_models.py tests/test_api/test_ui_config.py tests/test_config/test_ui_settings.py
6 files would be left unchanged.
... -m flake8 <same six files>                       # 52 diagnostics
... -m mypy --explicit-package-bases <same six files>
Found 9 errors in 2 files (checked 6 source files)
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

With line numbers ignored, the flake8 set equals the lane's
[flake8 log](flake8.txt) minus one: an unused
`recover_active_slot_choice` import in `narrative.py` that another lane
removed. The nine mypy diagnostics are the same path-and-message set as the
lane's [branch mypy](mypy-branch-full-context.txt). There are no new
diagnostics.

### Coordinator's Steps

- State-surface regeneration on the final wave-B UI union, the three joint
  tables, `theme-exceptions.json` and `state-tokens.md`.
- The full `npm --prefix ui test` with state-shades green.
- The whole-tree PostgreSQL gate.
- Fleet migrations (none in this lane).
- The ruling post on #777 (the decision comment above already exists).

## Integrated-Tree Status (2026-10-13)

Recorded by the UI-B+777-shell fixer (Claude Opus 5.5) on branch
`claude/waveb-fix-ui-b`, cut from integration head `a563203a`. Raw logs and
commands are in `docs/qa/backstage-world-time-and-observation/verification.md`,
"Integrated-Tree Proof (2026-10-13)".

**#1102 is not fully fixed.** With item 16's `onBlur` in place, a keyboard user
who Tabs onto the exceeds-RAM row while the settings list must scroll to reveal
it still loses the tooltip: the Tab auto-scroll fires Radix's ancestor-scroll
close. The landed trace keeps its stationary-viewport precondition (the row is
scrolled into view before tabbing), as ruled, so it does not exercise that
case, and in the browser it reads 50/50/50 with or without item 16 (the
`focusOut` Vitest case is the discriminating test). The PR line reads
`Refs #1102`, not `Closes #1102`. Making the row tooltip controlled from
focus-within (ignoring Radix's scroll close while focus stays in the row) is a
follow-up the coordinator files on #1102. The README passage differs from item
17's ordered text; its wording is for the coordinator to confirm.

Fixes on this tree: `ui/.design-sync/ds-provider.tsx` now answers
`/api/config/ui` with a promise like every other GET stub (`7b4a347e`), and
the TopBar hold test asserts the region is empty after the second hold before
the second "Generation started" (`7b4a347e`; with the clear planted to arm only
once, the test fails at `TopBar.test.tsx:422`).

The global `ui/client/src/tests/setup.ts` shim is covered by a whole-suite run,
not the 12-file selection: `nice -n 15 npm --prefix ui test` at `220772a2`
gave `Test Files 1 failed | 40 passed (41)`, `Tests 632 passed (632)`; the one
failure is `src/state-shades.test.ts` "Stale browser-resolved state surfaces",
expected until the coordinator regenerates the receipt. The regeneration and
the green full suite after it are the coordinator's step. The 777 Python set
(`tests/test_api/test_ui_config.py tests/test_config tests/test_api/test_route_capabilities.py tests/test_api/test_preferences.py tests/test_api/test_settings_endpoints.py`,
`NEXUS_RUN_POSTGRES=1`, `-p tests.dbname_audit`) passed on `fc7c5a3c`:
`156 passed, 7 warnings in 16.09s`, with the secret-store guard line and
`dbname audit: owner targets: none`. This evidence cites the
`4ae8b8d2` merge base above as historical; the assembly has since moved the
canonical documents' `verified_commit` stamps to `f073b371`.

## Regeneration on the Wave-B UI Union (Coordinator, 2026-10-13)

Run from `.claude/worktrees/ui-union` (branch `claude/wave-b-ui-union`: the wave-B integration head plus 777-KBD, 961-HOME, 824-S1 and 809-S3b) with `scratchpad/waveb/regenerate_state_surfaces.sh`: nine serial `nice -n 15` batches covering the 33 conditions (22 vectors; the 27 fine-pointer renders plus six coarse), each with its own `STATE_SURFACES_SCRATCH` and shard, then `--assemble`. Input fingerprint `c7df4f2cb3e82dd9aaad312acb3321900a3b4dee7625108faaa530b48e43dfcf`; module graph 2,099 inputs; file:// origin with the network aborted; zero requests and zero page errors in every batch (`regeneration-ui-union-2026-10-13/driver.log`, `assemble.log`).

Acceptance (`npm --prefix ui test -- --run state-shades`): the two recorded-table checks failed first because the recorded joint tables and `theme-exceptions.json` still described the 27-condition inventory (2,187 measured rows and 229/766/1187 exceptions against 2,673 rows now); the tables were refreshed through the test's own `STATE_SHADES_EVIDENCE_DIR` emission and the exceptions re-derived from the measured shortfalls (275/792/1266). With those refreshed, `state-shades.test.ts` and `media-state-shades.test.ts` pass: 106 tests (`regeneration-ui-union-2026-10-13/acceptance-tail.txt`).

The exhaustive search confirms the palette disposition of `7eb9a10c`: every group's shipped minimum equals the group optimum or clears 15 ΔE where reachable.

| Theme | Group | Optimum | Shipped minimum | Feasible assignments | Changed tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| Veil | memory | 48.2821 | 28.7231 | 270 | 0 |
| Veil | delete | 14.6295 | 14.6295 | 0 | 2 |
| Veil | map | 6.0138 | 6.0138 | 0 | 3 |
| Veil | key | 18.4458 | 17.2666 | 1930 | 2 |
| Gilded | memory | 43.1757 | 33.2117 | 150 | 1 |
| Gilded | delete | 12.1386 | 12.1386 | 0 | 2 |
| Gilded | map | 7.7097 | 7.7097 | 0 | 4 |
| Gilded | key | 16.2573 | 16.1506 | 22 | 3 |
| Vector | memory | 41.8156 | 39.0728 | 36 | 1 |
| Vector | delete | 23.2089 | 15.9700 | 156 | 0 |
| Vector | map | 5.9002 | 5.9002 | 0 | 3 |
| Vector | key | 11.4681 | 11.4681 | 0 | 3 |
