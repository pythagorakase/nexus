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

## Scope and Pending Proof

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
combined gate is still incomplete. At the user's packing-up request, no new
capture, build or full suite was started; the prepared capture plan remains
pending.

The new configuration key is `[ui.announcer].hold_ms`, shipped as 5000 and
required, strict, and bounded to 1000–60000. The player route returns only its
explicitly allowlisted announcer object. The reachability baseline adds exactly
one sorted path, `nexus/api/ui_config_endpoints.py`.

Remaining: the complete bounded state-surface regeneration and full UI suite.
The coordinator owns the
combined full gate and PR publication; no push or PR is claimed here.

Codex — GPT-6
