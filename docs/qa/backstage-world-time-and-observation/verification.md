# Backstage World Time and Observation: Initial Red Evidence

Date: 2026-10-08. **The coordinator accepted the initial reds; product changes and green proof are pending.**
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
`4ae8b8d2` verification base. All normal merge hooks passed. No shared reference
or predecessor worktree changed.

## Recorded Decision and Component Check

The user approved an explicit unavailable observation for a pending draft whose
UUID has no generation-session row, with its explanation and the rest of
Backstage usable. Its exact explanation is
`session <uuid>: no generation session (staged before session binding)`.
This pending analogue is an authorized extension of 802-Q1, not a quotation
from the earlier accepted-chunk ruling. No owner confirmation remains pending.

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

## Remaining Implementation and Proof

After accepted reds, implement the frozen ordered elapsed calculation, required
nullable header, unchanged four-field builder renamed `BackstageTurn`, explicit
five-field endpoint response, narrow `NoGenerationSessionError` catch and exact
schema-3 dictionary. Pending lookup remains parent-filtered and distinguishes a
missing session row explicitly; other failures must propagate. Add only the
inline delta and existing-pattern ECONOMICS section, preserving attention
metadata/dimming and all earlier sections and polling.

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
