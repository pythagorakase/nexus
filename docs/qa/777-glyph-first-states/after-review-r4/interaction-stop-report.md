# STOP-REPORT: Real Sidebar Hover Clears the Hovered Map State

Date: 2026-10-05. Resumed source head: 419edceb02cf775a4633535269970a468c38ab98.
Branch: claude/777-glyph-first-states; PR #1099 remains open.

**STOP:** the inherited map/sidebar hover context requires a hovered glyph
while the pointer is on its sidebar row. The ordinary production action
sequence clears that glyph state. A fresh acceptance receipt, maxima or
exceptions cannot honestly be produced for that Cartesian inventory with
real hover held during capture.

## What Was Tried and Measured

The draft mounts actual NexusLayout, MapPane, KeysSection, ModelSection and
SectionRail; the production Vite config emits its CSS to order scratch.
No fixture stylesheet reverses production imports. The browser is Chromium
153.0.8010.12, Playwright 1.63.0, 1200×900, dark, reduced motion, DPR 4,
file:// with HTTP(S) aborted. It uses native pointer actions and keyboard Tab,
awaits finite browser animations and makes painted/control visibility:hidden
captures. Each foreground mask records its size and eight leading RGB modes.

The compact replay samples shipped and historical pigments without candidate
enumeration: map only, default condition, Veil only. It completed **60** sample
pairs (120 clipped screenshots) before this named interaction failure:

```text
Incomplete painted probe: renders=60; wall=14.029s; acceptanceComplete=false
Error: Measurement failure default/Veil/map/sidebar/hover/fill/hovered: real action produced rest, expected hovered; {"pin":false,"row":true}
```

Action: select Place 1 through the real row button, close the production
place dialog, hover the real canvas pin 3, then hover its real sidebar row.
The first action produces the hovered diamond. Moving to the row causes the
canvas pin's pointerleave handler to clear hoveredId. The row matches :hover;
the pin does not. The glyph is the rest circle. The full DPR-4 screenshot was
visually inspected: Place 3's row wash is visible, but both markers are rest.

Production evidence: MapPane.tsx:541–545 gives current/selected priority then
reads hoveredId; :606–608 defines the sidebar row's click handler with no
pointer-enter handler; :738–742 sets hoveredId on canvas entry and clears it
on exit. The inherited oracle at 419edceb synthetically dispatches pointerover
before row hover, rather than maintaining a real pin hover. Its snapshots are
not proof that this ordinary native action combination is reachable.
This finding is specifically about the prescribed non-dragging hover sequence;
no claim is made about untested dragging, multiple pointers or captured-pointer
states. Those would require a distinct declared interaction context.

Artifacts: sidebar-hover-context-failure.json and its inspected PNG;
interaction-incomplete.json holds all 60 mask samples, conditions, graph-derived
fingerprint, zero page errors and zero HTTP(S) requests. It is explicitly
acceptanceComplete=false. The capture predates documentation-only changes and
the added incomplete-receipt guard; its own path hashes identify its inputs.
No partial probe replaces the checked acceptance JSON.

## Preserved Work, Not a Completed Oracle

The implementation draft replaces chains/compositing with actual painted RGB,
adds the esbuild metafile and recursive CSS/Tailwind scan fingerprint, independent
per-group search, full normalized global declarations, label/halo isolation,
real settings fixtures, a media inventory and a nine-plant script. These remain
incomplete: no full candidate receipt, complete media-condition validation,
plant results, regenerated tables/swatches, maxima, shipped assignments or
Amendment-4 exceptions are claimed. Compound media coverage and bounded plant
stages still need finishing. The trial foreground floor is 8%; a 40% trial
rejected the verified key's own-shadow mask (mode 423/2304 = 18.36%). The complete
inventory has not validated the 8% floor. Empty or weaker masks are named errors.
The stale guard runs in a clean Node process to avoid jsdom/esbuild typed-array
realm mismatch; the required focused command correctly fails on the stale
receipt. Product regressions and type checks pass separately.

The retained accepted label/halo evidence is product-proof.json: Gilded/Vector
selected labels have zero changed pixels; Veil's selected label has the labeled
815-pixel mandatory anchor correction and paints [184,61,122] (#b83d7a). Halo-only
comparisons remain 6/6 pixel-identical with computed shadows unchanged. These are
retained earlier comparisons, not newly completed all-label proof. The accepted
product files and afbb2756 were left unchanged.

The owner-target gate passes with zero recorded targets. The API/Orrery offline
suite and first root shard pass; the other offline shards and separate
reachability gate were not run after this stop. No full offline gate is claimed.
No full npm test/build acceptance gate, plants or fresh oracle passes are claimed.
No paid call, gateway/app service, owner service or database write occurred.
No product Python, nexus.toml, migration, main-checkout or other-worktree edits.

## Disposition and Coordinator Question

_common_codex.md:14 says: “if honest attempts cannot satisfy a rule or a gate,
STOP and write a stop-report (what you tried, exact errors, your diagnosis).”
The order also says retain every context “as now” and requires native hover.
Faking hoveredId, dispatching a synthetic event or silently deleting required
comparisons would manufacture evidence. An asynchronous question requested a
ruling; no answer was received before this report. A preselected option is not
approval.

May the inventory contain only physically reachable state/action combinations,
explicitly record the unavailable hovered × sidebar-row-hover combination,
and omit its pair comparisons in that context while retaining hovered pairs in
canvas and sidebar-with-pin-hover contexts? Alternatively, name another exact
production action sequence and its context (including dragging/pointer capture
if intended). No product behavior change is proposed or authorized.

Useful draft work and evidence are committed locally. No origin/main merge,
push or PR body update is claimed: release gates remain unfinished. The old
419edceb and accepted afbb2756 remain ancestors; no rewrite, stash or PR merge.

## Exact Commands and Verbatim Tails

All commands ran from the named worktree. Long commands used scratch/run.mjs
with a 589-second bound and were awaited to completion. The command JSON
records arguments, exit code, signal, wall time and verbatim tails.

Import provenance:

```text
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/nexus/__init__.py
```

Bootstrap: npm --prefix ui ci completed (959 added, 960 audited, 34 reported
vulnerabilities); no dependency or lockfile changes. Its full tail was not
retained by the initial tool invocation; it is not fabricated here.

### owner-target (exit 0)

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_owner_target_guard.py
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
........................................................................ [ 90%]
........                                                                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
80 passed in 2.65s

```

### offline-api-orrery (exit 0)

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
ssssssssssssssssssssssssssssssssss...................................... [  2%]
.......sss....ssssssssssssssssssssssss.................................. [  5%]
................................ssss.................................... [  8%]
................ssssssssss.......ssssssssssssss...s..................... [ 10%]
...........................sssssssssssssssss.......sssssssssss...sssssss [ 13%]
sss...............ssssssssssssssssssss...............sss.....ssssssssss. [ 16%]
...........ss..sssssssssssssssssss...................................... [ 18%]
....ssssssssss......s...........................sss...ssssssssssssssssss [ 21%]
ssssss........ss..............ssssssss.................................. [ 24%]
.............................................................sssssss.... [ 26%]
................ssss...ss.........................................ssssss [ 29%]
sssssssssss.........s............................s...................... [ 32%]
.....................................................sssssssssss........ [ 34%]
...........ss..................sss.......................sssss.......... [ 37%]
..........sssssss..........ss.........ssss.ss...ssss...................s [ 40%]
ssssssssssssssssssssssssssssssssssssss.......sssssssssssssssssssssssssss [ 42%]
ssssssssss.....ssssssss..............sssssssssssssssssss................ [ 45%]
..sssssssssssssssss...............................................ss.... [ 48%]
............ssss....sssssssssssss........ssssssssss..s................ss [ 50%]
sssssssssss...s......................................................... [ 53%]
........................................................................ [ 56%]
..........................sssssssss.................................s... [ 58%]
.......................ssssssssssssssssssssssssssssssssssssssssssss..... [ 61%]
...................................................................sssss [ 64%]
sssssssssssssssssssssssssssssssssssssssss....................s.......... [ 67%]
..............sssssssssssssssssssssssssss..s.........sss...........ssss. [ 69%]
.......................sss.....ssssssssssssssssssssss......sssss..s..... [ 72%]
..............ssssssssssssssssssssssssssssssssssssssssssssss............ [ 75%]
........................................................................ [ 77%]
......................ssssssss.......................................... [ 80%]
...........................................s.................sssss...s.. [ 83%]
............................................sssssssssssssssssssssssss... [ 85%]
.....................................................sssssssssssss.s.... [ 88%]
..s...................s....sssssssssssssssssssss.......ss............... [ 91%]
ssss......................................ss....sssssssssss............. [ 93%]
........................................................................ [ 96%]
sssssssssss........................sssssssssssssss.............sssss.... [ 99%]
......s.ssssssssssssss                                                   [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1865 passed, 821 skipped, 7 warnings in 42.40s

```

### offline-root-1 (exit 0)

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_backfill_review_packet.py tests/test_bootstrap_episode_pg.py tests/test_character_identity.py tests/test_character_name_reveals.py tests/test_character_name_reveals_pg.py tests/test_character_relationship_id_types_pg.py tests/test_character_tag_manifest.py tests/test_chunk_lifecycle_columns_migration_pg.py tests/test_cli.py tests/test_cli_choice_http.py tests/test_cli_contract.py tests/test_cli_generation_http.py tests/test_cli_inspect_pg.py tests/test_cli_model_selection.py tests/test_cli_session_wait.py tests/test_cli_wizard_confirmation.py tests/test_clock_face.py tests/test_commit_choice_presence_pg.py tests/test_commit_chronology.py tests/test_commit_handler_sync.py tests/test_connection_lifecycle.py tests/test_correspondence.py tests/test_correspondence_live.py tests/test_database_contract.py tests/test_db_converters.py
........s......................................sssssss...ssss........... [ 13%]
........................................................................ [ 27%]
........................................................................ [ 41%]
........................................................................ [ 55%]
................................................................s....... [ 69%]
..........................................................ssssssssss.... [ 83%]
...............s....s........................s......................ss.. [ 97%]
..............                                                           [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
490 passed, 28 skipped, 5 warnings in 245.70s (0:04:05)

```

### check-final (exit 0)

```text
npm --prefix ui run check

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json


```

### product-tests-final (exit 0)

```text
npm --prefix ui test -- StateGlyphs MapPane shell-accessibility

> nexus-ui@1.0.0 test
> vitest run StateGlyphs MapPane shell-accessibility


 RUN  v2.1.9 /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ src/shell-accessibility.test.ts (9 tests) 53ms
 ✓ src/components/nexus/MapPane.test.tsx (3 tests) 112ms
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 408ms

 Test Files  3 passed (3)
      Tests  18 passed (18)
   Start at  13:36:38
   Duration  1.03s (transform 220ms, setup 78ms, collect 573ms, tests 573ms, environment 506ms, prepare 87ms)


```

### focused-stop-final (exit 1)

```text
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility

> nexus-ui@1.0.0 test
> vitest run state-shades StateGlyphs shell-accessibility


 RUN  v2.1.9 /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ src/shell-accessibility.test.ts (9 tests) 55ms
 ❯ src/state-shades.test.ts (0 test)
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 454ms

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:160:9
    158|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    159| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    160|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    161| if (receipt.proof.acceptanceComplete !== true)
    162|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed | 2 passed (3)
      Tests  15 passed (15)
   Start at  13:37:13
   Duration  1.17s (transform 230ms, setup 89ms, collect 382ms, tests 509ms, environment 511ms, prepare 141ms)


```

### map-context-final (exit 1)

```text
STATE_SURFACES_SCRATCH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/capture STATE_SURFACES_OUTPUT=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/capture/probe.json STATE_SURFACES_PROBE=1 STATE_SURFACES_GROUP=map STATE_SURFACES_CONDITION=default STATE_SURFACES_THEME=Veil npm --prefix ui run resolve-state-surfaces

> nexus-ui@1.0.0 resolve-state-surfaces
> node scripts/resolve-state-surfaces.mjs

[33mThe CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.[39m
[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
Browserslist: browsers data (caniuse-lite) is 12 months old. Please run:
  npx update-browserslist-db@latest
  Why you should do it regularly: https://github.com/browserslist/update-db#readme
node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js (9:18): Use of eval in "node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js" is strongly discouraged as it poses security risks and may cause issues with minification.
Resolving default/Veil…
Incomplete painted probe: renders=60; wall=14.029s; acceptanceComplete=false
file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:145
            throw new Error(`Measurement failure ${failure.label}: real action produced ${actual}, expected ${state}; ${JSON.stringify(failure.hovered)}`);
                  ^

Error: Measurement failure default/Veil/map/sidebar/hover/fill/hovered: real action produced rest, expected hovered; {"pin":false,"row":true}
    at captureValues (file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:145:19)
    at async file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:226:11

Node.js v24.3.0

```

### Final type and syntax verification

```text
npm --prefix ui run check

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json


```

Node --check passed for resolve-state-surfaces.mjs and each state-surfaces/*.mjs
helper (domain, inputs, media, plants, png); git diff --check passed. Both
checks produced no output and exited 0. No browser/paid/provider work occurs.

Codex, GPT-6.
