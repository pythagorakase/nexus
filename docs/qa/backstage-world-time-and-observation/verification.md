# Backstage World Time and Observation: Source Checkpoint

Date: 2026-10-08. **The coordinator accepted the initial reds; implementation is authored.** The green proof ran on the integrated wave-B tree on 2026-10-13; see "Integrated-Tree Proof (2026-10-13)" at the end. The sections between here and there are the historical 2026-10-08 checkpoint.
The frozen UI-B order explicitly requires each new test before implementation.
The tests-only checkpoint authored those regressions against unchanged UI-B product
code. Its source preparation ran no tests. The later coordinator execution below
records actual initial failures before any UI-B product change; no green, type
check, build, screenshot or state-surface regeneration is claimed.

The product baseline is merge `28e7070bfaa48e77866f0a11ebce23ca9ec7970f`:
784-S2 `bf053542a1007b7fea768c13a06b768136df4aa8` plus frozen 777 source
`149704d16fa126b8ac9d142a22bf51b42a669552`. The only merge conflict was the
responsive-shell decision's source list; the union retains the layout, CSS and
`useNarrowShell` sources, unchanged ruling/status/quotation and the shared
`4ae8b8d2` verification base (historical; the assembly has since moved the
stamps to `f073b371`). All normal merge hooks passed. No shared reference
or predecessor worktree changed.

## Recorded Decision and Component Check

The unbound-pending branch (UI-B item 5) reads a pending draft whose UUID has
no generation-session row as an explicit unavailable observation, with its
explanation and the rest of Backstage usable. Its exact explanation is
`session <uuid>: no generation session (staged before session binding)`.
This pending analogue is a coordinator mechanism extension of 802-Q1, not a
quotation from the accepted-chunk ruling. It is pending the owner's
confirmation; the coordinator asks on #802 at landing. No recorded owner
approval exists in the repository or on #802.

Before authoring the UI tests, an independent delegated source review checked
the official [Collapsible documentation](https://ui.shadcn.com/docs/components/radix/collapsible)
and the existing vendored `collapsible.tsx` and `BackstageDrawer.SectionHeader`.
The official component provides controlled root/trigger/content behavior; the
vendored module aliases Radix primitives. The drawer already provides the
compact label, summary and toggle required here, so the ordered fourth section
will reuse it. The official typography URL now resolves to
[Typeset](https://ui.shadcn.com/docs/typeset); plain inline text satisfies the
fixed header ruling without a Badge, Typeset dependency, installation or new
chrome. This source review used no app/browser process or execution proof.

## Authored Regression Scope

Four new PostgreSQL test functions use the existing Backstage template-clone
fixtures, with only the ordered separate `qa640_uib_turn` clone for the real
TEST turn:

- Elapsed clocks require `[null, 60, 3600, 3600]` for playable chunks 2–5 and
  compare every non-null result to SQL's canonical previous-playable clock
  difference. The synthetic prologue cannot become the first turn's parent.
- Missing prior clock uses the ordered local replica-role transaction on the
  disposable clone, requires the precise 500 error, always rolls back and
  disposes the registered SQLAlchemy engine, then checks the restored endpoint.
- Legacy accepted and unbound pending observations require their distinct exact
  envelopes and explanations; an earlier selected parent requires pending null.
  Correspondence, writes and Orrery rows must remain present.
- The real TEST turn establishes private runtime config before the provider
  fixture, keeps the current 816 provider-database route, requests port zero
  only inside `gateway_lane`, and uses actual CLI continue/inspect-turn and HTTP
  approve calls. Pending session P is compared with the entire CLI schema-3
  dictionary after removing only `read_at`; both TEST seats must be present.
  The latest accepted session is checked against SQL. After the owned gateway
  and workers stop, accepted chunk C is compared with CLI inspection again,
  pending must be null, and elapsed seconds must match its parent's SQL clock.

The shared Backstage fixture now returns its already-created provisional UUID,
and the existing exact header assertion gains the required elapsed field.
All existing 784 attention assertions remain. The three authored/changed UI
behaviors cover first-turn unavailable, full accepted/pending observations with
provenance and no duplicate accepted summary, and the approved unbound pending
explanation with collapse/reopen and other sections still usable. Eight signed
formatter examples include zero, sub-minute, hour/day boundaries and negative
time. The existing layout open-render test gains the elapsed suffix and exact
observation strings. These are source inventories, not collected or passed
test counts.

The 777 announcer mocks, rail behavior and mounted MapViewProvider are retained.
This frozen 777 source still seeds `SETTINGS_QUERY_KEY`; the later 809 UI-config
contract must be merged normally and its `UI_CONFIG_KEY` seed preserved before
final proof. No UI-B product, CSS, telemetry, CLI, shared fixture or migration
file is edited in this tests-only checkpoint.

## Historical Initial Red Admission Plan

The coordinator owns the single heavy slot. Before any product edit, request
admission for these four nodes on the committed tests-only head:

```sh
PYTHONPATH="$PWD" nice -n 15 "$PY" -m pytest -q -p tests.dbname_audit \
  tests/test_api/test_backstage_endpoints_pg.py::test_backstage_header_elapsed_world_time \
  tests/test_api/test_backstage_endpoints_pg.py::test_backstage_header_missing_world_time_is_500 \
  tests/test_api/test_backstage_endpoints_pg.py::test_economics_legacy_and_unbound_pending_are_unavailable \
  tests/test_api/test_backstage_endpoints_pg.py::test_economics_matches_inspect_turn_for_a_test_turn
```

Use the shared interpreter `/Users/pythagor/nexus/.venv/bin/python`, exact
worktree import proof, `NEXUS_RUN_POSTGRES=1`, load at most 24, bounded serial
pieces and cleared inherited libpq, routing/runtime/provider/template,
pytest-selection/plugin and live/secret opt-ins. Gateway URL/port and slot are
unset at admission; only the admitted test may set its private port-zero lane.
Require all final secret-store, receipt and owner-target guard summaries.
Expected initial failures are absent `elapsed_seconds`, no missing-clock
exception, and absent `economics` in each economics test. Inspect every failure:
fixture setup, provider, schema or cleanup errors are not intended red evidence.

After an admitted local `npm ci`, the required UI red command is:

```sh
nice -n 15 npm --prefix ui test -- NexusLayout BackstageDrawer
```

It must expose the absent elapsed/economics renderings and formatter export
while retaining unrelated 784/777 coverage. Record exact identities and tails;
do not infer outcomes from the authored assertions. Product remains unchanged
until the coordinator accepts both red results. A schema-3 parity comparison
crossing UTC midnight may be rerun once only with evidence of that boundary;
job, usage, provenance or other fields are never dropped to force equality.

## Actual Initial Reds and Harness Failures

The coordinator ran all initial proof at unchanged tests-only HEAD
`7557f00c7278d74e203c585d0092436db4f15934`, tree
`98e20d9f013579c9f6a6d6189e80a61c2912c618`, with `origin/main` pinned to
`f073b3711a3bd0273943c9defad85913452fd00b`.

- [Python log](initial-red/python-initial-red/python-red.txt): **4 failed**,
  9 warnings, 24.47 seconds. The exact reasons are missing `elapsed_seconds`,
  no `BackstagePayloadError` for the missing prior clock, and missing `economics`
  in both economics tests. All three final guards passed and both read-only
  clone checks returned `[]`. No skip or setup error was accepted.
- [First UI attempt](initial-red/ui-npm-failed-attempt/npm-ci.txt): npm stopped
  before tests because the runner reused `/dev/null` as both user and global
  config. This remains a failed harness attempt. The coordinator corrected only
  the private runner to create two distinct empty npmrc files.
- [UI follow-up log](initial-red/ui-initial-red/ui-red.txt): npm ci passed;
  Vitest recorded **12 failed, 8 passed** in 2.57 seconds. The failures are the
  absent formatter, elapsed suffix, ECONOMICS section and pending observation.
  All existing attention/layout/announcer cases passed. The frozen `NexusLayout`
  filter also selects three `NexusLayout.announcer.test.tsx` cases, omitted from
  the runner's two-suite whitelist, so its raw result deliberately remains
  `failed-review-required` despite the intended test outcomes.

The [coordinator adjudication](initial-red/ui-initial-red/coordinator-adjudication.json)
records all actual outcomes, hashes, the whitelist omission and clean source.
It authorizes product implementation after inspecting the complete existing
reports; no test rerun or assertion change was used to hide the harness errors.
The [source manifest](initial-red/source-manifest.json) hashes the copied raw
logs, JUnit/JSON reports and original runner snapshots. Temporary fixture logs
remain in the named private coordinator evidence directory; caches, temporary
configs and installed node modules are intentionally not repository artifacts.
The owner-connection audit retains the documented subprocess/driver limits;
its three guard summaries are not a universal OS or child-process audit.

## Authored Implementation — Green Proof Pending

The accepted raw reds were committed first in `1c8b92fb`. The subsequent source
change touches five product files. `backstage.py` calculates the elapsed seconds
from the previous playable committed clock, gives the first turn null, and
refuses either missing clock when a previous turn exists. Its existing builder
returns the four-stream `BackstageTurn`; the endpoint separately returns the
explicit five-field model with economics. The same resolved slot URL feeds the
existing SQLAlchemy builder and the closed psycopg2 observation connection.

Only the ruled legacy accepted-chunk `NoGenerationSessionError` becomes an
unavailable read. Pending lookup filters on the selected parent and checks the
staged session row explicitly. The authorized unbound-pending explanation names
the staged UUID. Other exceptions propagate; the full schema-3 observation is
returned verbatim. Observation reads retain `inspect_turn`'s read-only snapshot
behavior. No telemetry, CLI, shared fixture or relationship-reader code changed.

The drawer adds only the signed elapsed suffix and fourth ECONOMICS section.
It reuses SectionHeader, row and history styles, retains provenance/unknown/zero
values, and marks a pending observation by the ordered dashed inset/opacity.
Existing three sections, polling, attention metadata/dimming, 777 shell behavior
and the test assertions remain unchanged. There is no new migration, setting,
provider call, owner write or service action in this source work.

Black left both changed Python files unchanged (see `source-black.txt`). This
is formatting evidence, not runtime/import, lint, type or green test proof.
`canonical-source-closure.json` records the source-only canonical review:
0054's rail ruling is unchanged; current merge base and its stamp were both
`4ae8b8d2` at that checkpoint (historical: the wave-B assembly has since moved
the canonical documents' `verified_commit` stamps, 0054 included, to
`f073b371`). Final predecessor/main merging still requires renewed closure and
freshness verification. `pending-focused-selectors.json` lists the required
focused scopes, including the announcer suite selected by the frozen UI filter.

Root and an independent peer reviewed the five-file product diff against
`1c8b92fb` and found no source blocker. The peer review's output was not
retained in the repository, so its diff hash is not cited here. The review covered required fields, exact clock refusal, the builder/route
split, the narrow exception, transaction boundaries, session/parent correlation,
verbatim observations and preserved 784/777 behavior. This is source review;
neither review imported the application or ran tests. The 0054 review read its
unchanged bottom-rail ruling at this branch's actual `4ae8b8d2` merge base and
does not claim review against a future final main (historical; the assembly
has since moved 0054's stamp to `f073b371`, re-verified on 2026-10-13 below).

## Remaining Proof (Historical, 2026-10-08)

Then perform the frozen focused PostgreSQL selection (Backstage endpoints,
attempt manifests, turn observation, slot-routed entrypoints, card identity and
connection lifecycle), module import-cycle proof, static baseline comparisons,
exception/reachability/document checks, UI focused tests/type/design-preview
checks/build, and the three owner-safe synthetic visual captures. No current
fleet survey is claimed; October 7 counts are historical. Parent owns whole-tree
validation and any owner operations.

After landed 777/809/824 and all required source merges, reverify canonical
source closure (0054 now declares the CSS), preserve all decision quotations,
and regenerate the actual combined state-surface fingerprint in bounded
batches. The post-777 expectation is 22 vectors/33 conditions; the Backstage
fixture is unmounted, so moved measurements require a STOP report. Never copy
a receipt between different source trees. Final full UI proof, owner UI rebuild
and scheduled gateway restart remain later landing work. No migration is added;
149/150/151 keep their existing owners.

Codex — GPT-6

## Integrated-Tree Proof (2026-10-13)

Fixer: Claude Opus 5.5, worktree `fix-ui-b`, branch `claude/waveb-fix-ui-b`, cut
from integration head `a563203a` (origin/main `f073b371` plus the wave-B lanes,
the 777 shell and nine lane fixes). Raw logs live in
[`integrated-proof-2026-10-13/`](integrated-proof-2026-10-13/). `<scratch>` is
the session scratchpad subdirectory `fix-waveb-r3-UI-B`; `$PY` is
`/Users/pythagor/nexus/.venv/bin/python`. Every command ran from the worktree
root with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. The
one-minute load before each PostgreSQL run was between 13.6 and 21.0 (below 24),
so no wait was needed; each log's first line records it (the first file's
reading, 14.32 at 17:54, printed to the terminal).

### Fixes Made on This Tree

- `7b4a347e`: `ui/.design-sync/ds-provider.tsx` answers `/api/config/ui` with
  `Promise.resolve(json({ announcer: { hold_ms: 5000 } }))`, as every other GET
  branch does. `TopBar.test.tsx` asserts the announcer is empty after the
  second hold, before the second "Generation started".
- `25758c48`: `test_economics_matches_inspect_turn_for_a_test_turn` reads each
  parity pair (endpoint, then `inspect-turn`) through `_same_utc_day_reads`,
  which rereads both once when the two `read_at` values fall on different UTC
  dates. `ledger_days_read` stays in the comparison; only `read_at` is removed,
  as before. The same commit clears this lane's new mypy diagnostics: the
  `requests` import carries `# type: ignore[import-untyped]` (no stub package is
  installed; the convention of `tests/test_api/test_genesis_resume_live.py:33`
  and `test_set_designer_failure.py:19`; the gateway tests use `requests`, no
  typed client) and the tomlkit assignment carries `# type: ignore[index]` (the
  convention of the same file's `test_backstage_gate_both_arms`). The tomlkit
  diagnostic the 784-S2 fixer reported at `:1068` is this assignment; on this
  tree it sat at `:986`.
- `fc7c5a3c`: Chicago title case for the three assembly-evidence headings.
- `220772a2`: the screenshot below showed the `correspondence_compaction`
  queue name painting over its row copy (the shared kind column is 68px). Inside
  `.nexus-backstage-economics` the kind column now has `width: auto;
  min-width: 68px`. Before the fix the readback measured the queue name's text
  ending at x=245.6 while its copy began at x=172
  ([before](integrated-proof-2026-10-13/screenshot-readback-before-kind-fix.txt));
  after it, no row overlaps
  ([after](integrated-proof-2026-10-13/screenshot-readback.json)).

### Import Cycle (fc7c5a3c)

```text
$ PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/fix-ui-b/nexus/__init__.py
$ PYTHONPATH=$PWD $PY -c 'import nexus.agents.orrery.backstage' ; echo "exit=$?"
exit=0
```

### Focused PostgreSQL Set (fc7c5a3c)

Each file ran alone, in order, as
`NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit <file>`.

```text
tests/test_api/test_backstage_endpoints_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa640_778s6a_backstage_*, qa640_778s6a_empty_*, qa640_uib_turn_*
dbname audit: owner targets: none
14 passed, 9 warnings in 26.46s

tests/test_api/test_attempt_manifest_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
5 passed, 9 warnings in 41.53s

tests/test_turn_observation.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
43 passed in 1.48s

tests/test_slot_routed_entrypoints.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
35 passed in 34.12s

tests/test_orrery/test_card_identity.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
9 passed, 2 skipped, 2 warnings in 11.66s

tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
1 passed in 30.07s
```

The Backstage file has 14 test functions and 14 passed, so the four UI-B tests
ran to completion; `test_economics_matches_inspect_turn_for_a_test_turn` ran the
real TEST turn on `qa640_uib_turn_*` through the CLI schema-3 parity, the
approve POST and the post-acceptance assertions, with no skip. The two
card-identity skips are the one `@pytest.mark.requires_corpus` test
(`tests/test_orrery/test_card_identity.py:123`, parametrized twice), which
needs `NEXUS_RUN_CORPUS=1`. Afterwards `pg_database` held no `qa640_uib%` or
`qa640_778s6a%` database. The 777 order's Python set also ran
(`tests/test_api/test_ui_config.py tests/test_config tests/test_api/test_route_capabilities.py tests/test_api/test_preferences.py tests/test_api/test_settings_endpoints.py`):
`156 passed, 7 warnings in 16.09s`, guard line and `owner targets: none`
present ([log](integrated-proof-2026-10-13/pg-777-set.txt)). The whole-tree
PostgreSQL gate is the coordinator's step.

### Offline Splits (fc7c5a3c)

Each split was collected once and run in file-list pieces (each under ten
minutes), with `NEXUS_RUN_POSTGRES` unset, as
`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider $(cat <scratch>/offline-part-N.txt)`.

```text
tests --ignore=tests/test_api --ignore=tests/test_orrery: 3872 tests collected
  part 0: 739 passed, 165 skipped, 7 warnings in 118.60s
  part 1: 874 passed, 162 skipped, 7 warnings in 212.91s
  part 2: 778 passed, 161 skipped, 8 warnings in 200.63s
  part 3: 806 passed, 187 skipped, 7 warnings in 94.43s
  total:  3197 passed, 675 skipped, 0 failed

tests/test_api tests/test_orrery: 3441 tests collected
  part 0: 633 passed, 349 skipped, 7 warnings in 20.43s
  part 1: 1 failed, 719 passed, 858 skipped, 7 warnings in 7.59s
  part 2: 560 passed, 321 skipped, 7 warnings in 15.20s
  total:  1912 passed, 1528 skipped, 1 failed
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
E   AssertionError: Regex pattern did not match.
E    Regex: 'without birth-role policies.*ate'
E    Input: "1 validation error for OrreryEpistemicsSettings\nclaim_event_types\n  Value error, claim_event_types contains event types emitted by background branches: ['ate'] [type=value_error, ...]"
```

The one failure is not this lane's: neither file changed here. `ate` became a
background-branch event type through 784-S2's attention metadata (`9641f184`),
so the background-branch check in
`OrreryEpistemicsSettings._validate_claim_event_types`
(`nexus/config/settings_models.py:2330-2370`) now fires before the
missing-policy check the test expects. It is reported to the coordinator, not
fixed here. `tests/test_reachability.py` and `tests/test_doc_front_matter.py`
ran in split one and again at `220772a2`:
`120 passed, 5 warnings in 16.72s` ([log](integrated-proof-2026-10-13/doc-reach.txt)).
`docs/decisions/0054-responsive-shell.md` declares `nexus-layout.css`; its
`verified_commit` is `f073b371`, the merge base, and its rail ruling is
untouched by the economics-only CSS rule of `220772a2`.

### Static Comparisons (fc7c5a3c Against origin/main f073b371)

The origin/main side ran in a `git archive origin/main nexus tests scripts pyproject.toml .flake8`
extraction under `<scratch>/mainsrc` (full import context).

```text
== black --check (branch fc7c5a3c)
3 files would be left unchanged.
== flake8 (branch)
nexus/agents/orrery/backstage.py:650:89: E501 line too long (91 > 88 characters)
== flake8 (origin/main)
nexus/agents/orrery/backstage.py:547:89: E501 line too long (91 > 88 characters)
== mypy --explicit-package-bases (branch): Found 7 errors in 1 file (checked 3 source files)
== mypy --explicit-package-bases (origin/main): Found 7 errors in 1 file (checked 3 source files)
== $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

No new diagnostics. The E501 is the same pre-existing SQL line (`git blame`:
`261005d3a`, 2026-09-24). The seven mypy errors are the same seven messages on
both sides at shifted lines (`backstage.py` 280/310/345/590/601 on main,
378/408/443/693/704 here), all on lines this lane did not write; before
`25758c48` the branch had three more in the test file (`:16` requests stubs,
`:986` twice). Full outputs:
[black/flake8](integrated-proof-2026-10-13/static-black-flake8.txt),
[mypy/dispositions](integrated-proof-2026-10-13/static-mypy-dispositions.txt).

### UI Proof

```text
$ nice -n 15 npm --prefix ui ci          (fc7c5a3c)   exit=0
$ nice -n 15 npm --prefix ui test -- NexusLayout BackstageDrawer TopBar MapPane shell-accessibility
  (fc7c5a3c)  Test Files  6 passed (6)   Tests  54 passed (54)
  (220772a2 content, run just before that commit)  Test Files  6 passed (6)   Tests  54 passed (54)
$ nice -n 15 npm --prefix ui test        (220772a2; first run at fc7c5a3c identical)
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 40 passed (41)
      Tests  632 passed (632)
$ nice -n 15 npm --prefix ui run check   (fc7c5a3c and 220772a2)
> tsc && npm run check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
exit=0, 0 "error TS" lines
$ nice -n 15 npm --prefix ui run build   (fc7c5a3c and 220772a2)   exit=0
```

The only full-suite failure is the expected stale state-surface receipt; the
regeneration and the green full `npm --prefix ui test` after it are the
coordinator's step. The full suite includes every file that the global
`ui/client/src/tests/setup.ts` shim affects (40 of 41 files green). The branch
type check reports zero diagnostics, so no origin/main comparison can show a
new one; the main-side check was not rerun. Red for the hold-clear assertion:
with `TopBar.tsx`'s clear effect planted to arm only for serial 1
(`|| serial > 1`), `npm --prefix ui test -- TopBar` failed at the new line,
`TopBar.test.tsx:422:27 expect(announcer()).toBeEmptyDOMElement()`,
`Tests 1 failed | 17 passed (18)`; the file was restored from a copy and
`git diff --quiet -- ui/client/src/components/nexus/TopBar.tsx` passed
([log](integrated-proof-2026-10-13/ui-topbar-plant-red.txt)).

### Screenshots and Visual-Minimalism Audit (220772a2)

`nice -n 15 node <scratch>/shots/shoot.mjs $PWD/ui <scratch>/shots/out`
([script](integrated-proof-2026-10-13/screenshot-proof.mjs)) bundles a scratch
copy of `ui/scripts/state-surfaces/fixture.tsx` (its whole
[diff](integrated-proof-2026-10-13/fixture-backstage.diff): Backstage health
true, developer mode on, and an in-page `GET /api/dev/backstage/4/turn` answer;
`fixture.tsx` itself is unchanged) with the production CSS of this tree's
`npm --prefix ui run build`. It mounts the real `NexusLayout` in Veil at
1200x900 (device scale 2, dark, reduced motion, network aborted), opens the
drawer with the backtick key, and captures the Vitest payloads: read A accepted
with read B pending, and the legacy-accepted plus unbound-pending unavailable
state. Page errors: none in either state.

- [Observed with pending](integrated-proof-2026-10-13/backstage-observed-with-pending-1200x900.png)
  ([drawer](integrated-proof-2026-10-13/backstage-observed-with-pending-drawer.png)):
  header `slot 04 · t.17 · +7 min`; ECONOMICS summary
  `critical 2,000/1,600 · background unknown/unknown · wall 11.1s · choices ready 11.1s`;
  pending block border `1px dashed rgba(230, 115, 77, 0.5)`, opacity 0.7.
- [Unavailable](integrated-proof-2026-10-13/backstage-unavailable-1200x900.png)
  ([drawer](integrated-proof-2026-10-13/backstage-unavailable-drawer.png)):
  header `slot 04 · t.17 · +1 h`; ECONOMICS summary `unavailable`; the two
  detail lines.

Audit against CLAUDE.md "UI Design: Visual Minimalism", per new element:
- Elapsed delta: unlabeled text appended to the existing header line after one
  `·`; it adds no label, icon or chrome, and the first turn shows nothing.
- ECONOMICS section: one label matching the drawer's other section labels, on
  the existing `SectionHeader`; its summary line is data, not prose, and the
  collapsed state keeps only that line.
- Accepted rows: reuse the write-row and kind styles; the seat is the only
  per-row label, and no copy repeats the section summary.
- Pending block: marked only by the dashed accent rule and dimming; no copy
  names it.
- Read foot: reuses the history style; `read <instant>` and the ledger days are
  data.
- Unavailable state: one detail line per read, stating the reason once.
- No internal module name appears in the new copy. The drawer renders its copy
  in the menu font's capitals, as its three existing sections already do; the
  provenance tokens (`attempt_manifest`, `provider_usage_ledger`) are ledger
  names shown as data in this developer-only surface, as the order requires.
The kind-column overlap the first capture showed is fixed in `220772a2`.

### #1102 and Landing Notes

#1102 is not fully fixed (ruled): natural Tab auto-scroll of the settings list
still dismisses the exceeds-RAM row tooltip through Radix's ancestor-scroll
close; the landed trace keeps its stationary-viewport precondition, and the PR
line reads `Refs #1102`, not `Closes`. The controlled-tooltip fix is a
follow-up the coordinator files on #1102; see the 777 evidence
(`docs/qa/777-shell-ui-bundle/verification.md`).

Coordinator's steps, not run here: the whole-tree PostgreSQL gate; the
state-surface regeneration (`npm --prefix ui run resolve-state-surfaces`) and the
green full `npm --prefix ui test` after it; fleet migrations (none in this
lane); the owner's gateway restart and UI rebuild; asking the owner on #802 to
confirm the unbound-pending branch.
