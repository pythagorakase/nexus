# Backstage World Time and Observation: Tests-Only Checkpoint

Date: 2026-10-08. **Initial red proof and all product changes are pending.**
The frozen UI-B order explicitly requires each new test before implementation.
This checkpoint authors those regressions against unchanged UI-B product code;
no pytest, collection, npm installation, type check, build, PostgreSQL operation,
provider call, gateway startup, screenshot or state-surface regeneration ran.

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

## Initial Red Admission Plan — Not Run

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
