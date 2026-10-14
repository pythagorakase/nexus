# Attention Class Verification

Status: implementation authored by Codex (lane range `c8abc33f..71f2b4f9`);
review fixes and the ordered proof ran on the integrated wave-B tree on
2026-10-13 (see "Integrated-Tree Proof (2026-10-13)"). Green: the focused
offline and PostgreSQL sets, three red controls, config validation, catalog
no-diff, Black, flake8/mypy (no new diagnostics), exception dispositions,
UI check, the drawer tests and the UI build. Coordinator's steps: the
state-surface regeneration (so `state-shades.test.ts` is stale as expected)
and the whole-tree PostgreSQL gate.

## Scope and Decisions

The frozen order is `temp/orders_2026_10_07/784-S2.md`, with its shared rules
and `coord/world-time-attention-refresh.md`. Source preparation was explicitly
advanced while the coordinator owns the shared gate. The lane was authored
on main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`; the wave-B assembly
carries it onto main `f073b3711a3bd0273943c9defad85913452fd00b`, and the
integrated-tree proof below ran there.

Live #784 was read on 2026-10-08. The [mechanism decisions](https://github.com/pythagorakase/nexus/issues/784#issuecomment-5922753528)
keep branch attention separate from template drive band and insert-status
`promotable`. The [Sequence 41 ruling](https://github.com/pythagorakase/nexus/issues/784#issuecomment-6043523766)
includes mundane activity plus sleep/eat/drink, while first meetings and
routine project continuations stay meaningful. The critical-need runtime
hatch remains 784-S3b. No built-in deviation or urgent roster is authored.
The earlier [S1 grammar measurement](https://github.com/pythagorakase/nexus/issues/784#issuecomment-5926233048)
is historical evidence, not a fresh measurement by this branch.

## Implementation and Source Review

- `substrate.py` adds the server-only enum and branch fields. New branches
  default to meaningful and no deviation. Template construction refuses
  background crisis bands, project milestones, relationship effects and
  status effects, and refuses deviation outside background. The extracted
  milestone predicate preserves the exact prior keys, Mapping check and
  truthiness test used by `configure_project_magnitudes`.
- `settings_models.py` checks configured claim events against both event
  fields emitted by background branches, after vocabulary validation and
  before birth-role policy validation. The existing `known_event_types()`
  already lazily imports `BUILTIN_TEMPLATES`; the new lazy reads follow that
  established dependency path. No top-level settings load is added.
- `templates.py` explicitly authors the 35 background and 29 meaningful pins
  below. Other branch fields and predicates are unchanged. The landed #785
  charted-place and timed-route fields, predicates, and catalog prose remain.
- Catalog markers are ordered preemptive, non-meaningful class, deviation,
  not-promotable. Audit and explanation emit the authored metadata; coverage
  includes chosen and per-branch classes. A failed explanation gate reports
  null attention and initializes its unchosen branch explicitly.
- Backstage looks up `(template_id, branch_label)` and leaves unknown labels
  null. Its optional TypeScript field and `data-attention` attribute feed one
  `.55` opacity rule. There is no new visible label, element, icon or hue.
- Pure tests cover the authoring refusals, defaults, exact roster, claim
  refusal order, catalog markers, audit payload and chosen/unchosen trace.
  Existing coverage fixtures receive the new required metadata. The
  card-identity class assertion requires corpus opt-in and skips in the
  ordinary PostgreSQL proof (its two parametrized cases are the two skips
  below); that skip cannot establish class wiring. Two template-clone
  endpoint tests do. `test_payload_reports_known_branch_attention` covers the
  legacy pressure-join path: it persists two resolutions with pressure rows
  and requires background and meaningful values. Its stroll pressure row is a
  join fixture; no background branch writes a scene pressure at runtime.
  `test_snapshot_reports_background_attention_without_pressure_row` (added in
  review) covers the path live turns take: it writes a live-shaped
  `narrative_chunks.orrery_proposal` snapshot (built with
  `OrreryResolutionDraft` and `OrreryTickProposal.to_dict()`) holding stroll
  "Pace the near ground" and no pressure row, and requires `background` in
  both rows and inventory. Both restore the chunk in `finally`. The existing
  unknown fixture label still requires null. The new drawer test exercises
  rendered row attributes without printing the class.

Known limit (order item 11's `None` rule): a legacy chunk with no
`orrery_proposal` snapshot takes its `branch_label` only from
`orrery_scene_pressures`. No background branch has a scene-pressure stub, so
real background resolutions on such chunks read `branch_label` and
`attention` as `None` and are not dimmed. Only snapshot-bearing turns show
the class for background rows.

No change routes, exposes, commits, escalates or seeds on attention. The
resolution type, resolver, events, worker, cards, model wire schemas, grammar
probe, `nexus.toml`, migrations and exception baseline are unchanged. No
policy, condition, tunable, prompt, persisted column or paid operation is
added. The later slices retain their original responsibilities.

## Authored Background Roster

The table was extracted from the authored source. At runtime,
`test_attention_roster_matches_ruling` requires exactly this set and passed
on `4c066cba` (red control B below proves it fails when one pin is dropped). Each listed branch has an
explicit `AttentionClass.BACKGROUND` keyword. Total: 35.

| Template | Branch |
| --- | --- |
| `sleep` | Collapse into deferred sleep |
| `sleep` | Sleep at home |
| `sleep` | Sleep in safe lodgings |
| `sleep` | Sleep rough in cover or transit |
| `drink` | Drink desperately, whatever is available |
| `drink` | Drink in a public room |
| `drink` | Drink from a public or wild source |
| `drink` | Drink routinely from what is at hand |
| `eat` | Eat ravenously, whatever is available |
| `eat` | Eat at home with household |
| `eat` | Eat at home alone |
| `eat` | Eat in a public dining place |
| `eat` | Forage or hunt from the country |
| `eat` | Eat from rations or what was packed |
| `eat` | Find something and eat it |
| `train` | Drill the fighting forms |
| `train` | Condition the body |
| `train` | Sharpen the finer skill |
| `train` | Keep the edge from dulling |
| `run_errands` | Make the market run |
| `run_errands` | Scrounge for what the day needs |
| `run_errands` | Provision the household |
| `run_errands` | Knock out the small obligations |
| `stroll` | Walk under open sky |
| `stroll` | Walk the familiar streets |
| `stroll` | Take the night air |
| `stroll` | Pace the near ground |
| `upkeep` | Maintain the working tools |
| `upkeep` | Mend and ready the kit |
| `upkeep` | Set the home in order |
| `upkeep` | Tidy what is theirs |
| `recreate` | Find games and company |
| `recreate` | Lose an hour to the loved thing |
| `recreate` | Watch the world go by |
| `recreate` | Take a small private pleasure |

## Explicit Meaningful Pins

Every listed branch retains `promotable=False` and has an adjacent explicit
`AttentionClass.MEANINGFUL` keyword. Total: 29.

| Template | Branch |
| --- | --- |
| `make_acquaintance` | Exchange names |
| `advance_relocation_plan` | Put another share aside |
| `advance_relocation_plan` | Scout a candidate place |
| `advance_relocation_plan` | Lose ground to a setback |
| `advance_relocation_plan` | Press on with the next practical step |
| `advance_recruit_ally` | Lose ground through neglect |
| `advance_recruit_ally` | Learn what the candidate actually wants |
| `advance_recruit_ally` | Prove reliable in a small consequential way |
| `advance_recruit_ally` | Make the next commitment concrete |
| `advance_pursue_romance` | Lose romantic ground through neglect |
| `advance_pursue_romance` | Offer another honest opening |
| `advance_pursue_romance` | Build closeness through chosen time |
| `advance_pursue_romance` | Make the next intention legible |
| `advance_court_patron` | Lose ground through neglect |
| `advance_court_patron` | Make useful work visible |
| `advance_court_patron` | Prove reliable under scrutiny |
| `advance_court_patron` | Make the next claim on favor legible |
| `advance_court_patron_faction` | Lose institutional ground through neglect |
| `advance_court_patron_faction` | Make useful work visible to the faction |
| `advance_court_patron_faction` | Prove reliable under institutional scrutiny |
| `advance_court_patron_faction` | Make the next claim on standing legible |
| `advance_seek_redemption` | Lose ground through neglected amends |
| `advance_seek_redemption` | Name the wrong without self-exoneration |
| `advance_seek_redemption` | Make one concrete repair |
| `advance_seek_redemption` | Leave forgiveness in the wronged party's hands |
| `advance_build_venture` | Lose ground through neglect |
| `advance_build_venture` | Make the venture legible |
| `advance_build_venture` | Secure one more commitment |
| `advance_build_venture` | Finish the next opening task |

## Canonical Documents

A source-only scan of actual leading front matter finds exactly two affected
canonical records: 0042 declares `substrate.py`, and 0054 declares
`nexus-layout.css`. Their bodies, owner quotations, statuses and source lists
are unchanged; only their stamps move. The lane stamped both at
`4ae8b8d2`; the assembly moved both `verified_commit` stamps to
`f073b371`, which is what the tree now carries. The records
state rulings, not claims that their full issues are implemented: #782 still
has the unchanged one-active-project policy here, and #777's bottom-rail
implementation is pending in the separately owned lane. Attention metadata
changes neither policy. `AGENTS.md` and `docs/turn_flow_sequence.md` declare
none of this slice's changed files. `tests/test_doc_front_matter.py` passed on `4c066cba` (focused offline set
below).

## Source Operations Recorded by the Author

Codex recorded these two commands at one-minute load 19.48, in its own
checkout (`/Users/pythagor/.codex/worktrees/resume-attention-class`), on the
lane's base `4ae8b8d2`. The file list behind `<15 changed Python files>` was
not recorded, so the first line is the author's summary, not a reproducible
command:

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black <15 changed Python files>
6 files reformatted, 9 files left unchanged.

nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m nexus.agents.orrery.catalog --write
Wrote /Users/pythagor/.codex/worktrees/resume-attention-class/nexus/docs/orrery_packages.md
```

Earlier text here also claimed a source inspection of the catalog bytes and
an independent production review. Neither has a recorded command, so this
file no longer relies on them. The Black check, the catalog write with no
diff and the catalog delta against main below replace them.

## Review Fixes (2026-10-13)

- `0fb9024c`, `nexus-layout.css`: the shared `row-in` keyframe
  ended at an explicit `opacity: 1`, so a background row faded up to full
  brightness, then snapped to `.55`. The `to` frame now keeps only
  `transform: none`, so each row ends at its computed opacity. The other two
  users of `row-in` (`.nexus-backstage-bubble` at `:1788`, `.nexus-backstage-write-row`
  at `:1818`) set no opacity anywhere in `ui/client/src`, so they still end
  at 1. The reduced-motion block still sets `animation: none` on all three.
- `4c066cba`, `tests/test_orrery/test_config.py`: the 2026-10-09 gate found
  `test_epistemics_rejects_event_type_without_birth_role_policy` failing,
  because `["ate"]` now fails as a background event first. Order item 5
  places the background refusal before `missing_policy`, and the order's
  own test must fail "if item 5 is ... placed after the birth-role check",
  so the validator order stays. The test keeps its intent with `socialized`,
  which has no birth-role policy and which no background branch emits (the
  background event set is `ate`, `drank`, `errands_run`,
  `recreation_taken`, `slept`, `stroll_taken`, `training_performed`,
  `upkeep_done`). The new
  `test_epistemics_rejects_background_event_before_birth_role_policy` pins
  the new message for `ate`.
- `4c066cba`, `tests/test_api/test_backstage_endpoints_pg.py`: the snapshot
  test described under "Implementation and Source Review".

## Integrated-Tree Proof (2026-10-13)

Worktree `/Users/pythagor/nexus/.claude/worktrees/fix-784-s2`, branch
`claude/waveb-fix-784-s2`, base `a563203a` (the integration head). Every
command below ran on `4c066cba` (base plus the two review-fix commits),
with `PY=/Users/pythagor/nexus/.venv/bin/python`. The import root printed
`/Users/pythagor/nexus/.claude/worktrees/fix-784-s2/nexus/__init__.py`.
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` were unset with
`env -u` on every pytest command. One pytest session ran at a time.
`uptime` was read before every PostgreSQL run. The one-minute load was
3.27 to 18.41, below 24 each time, so no wait loop was needed. No PostgreSQL
connection timed out, so no file was rerun.

### Focused Offline Set

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_substrate.py tests/test_orrery/test_catalog.py tests/test_orrery/test_audit.py tests/test_orrery/test_explain.py tests/test_orrery/test_coverage_accounting.py tests/test_orrery/test_config.py tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
324 passed in 19.16s
```

This run was on `a563203a` with the two test edits in the working tree,
immediately before they were committed unchanged as `4c066cba`.

### Ordered PostgreSQL Proof Set

```text
$ uptime
17:08  up 6 days,  3:48, 5 users, load averages: 4.86 5.27 6.38
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py tests/test_api/test_backstage_endpoints_pg.py tests/test_orrery/test_attention_class_grammar_probe.py tests/test_orrery/test_claim_birth_coverage_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 11 targets: postgres, qa640_778s6a_backstage_*, qa640_778s6a_empty_*, qa640_784s1_*, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_uib_turn_*, qa679_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:51813 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:51814 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:51813 (psycopg2), save_04@local:51814 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
54 passed, 2 skipped, 9 warnings in 78.77s (0:01:18)
```

The two skips are the `requires_corpus` parametrized exposure test in
`test_card_identity.py:123` (`asynchronous` False and True). The set
includes `test_card_identity.py` and `test_connection_lifecycle.py`, which
the machine-load rule requires in place of the whole gate.

### Red Controls

Each plant was made in this worktree, the named file ran, and the original
bytes were copied back from a scratch copy. `git diff --quiet` on the path
returned 0 after every restore. No plant was committed.

**A. Background invariants removed** (`substrate.py` lines 3006-3032 of
`Template.__post_init__`, the background block and the deviation check):

```text
before   df19e18a680443a8ffbf33f4eeaaabb8fd22d1a9fb973dc55e7cd20947d90b20  nexus/agents/orrery/substrate.py
planted  bdc4e36b1097695ceb01ed2321950595ed9928b707337234a04a1fce9b9b9ebb  nexus/agents/orrery/substrate.py
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_substrate.py -k 'background_branch or deviation'
tests/test_orrery/test_substrate.py:162: Failed
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_substrate.py::test_background_branch_refuses_crisis_band
FAILED tests/test_orrery/test_substrate.py::test_background_branch_refuses_milestone
FAILED tests/test_orrery/test_substrate.py::test_background_branch_refuses_relationship_effects[state_delta0-changed_fields0]
FAILED tests/test_orrery/test_substrate.py::test_background_branch_refuses_relationship_effects[state_delta1-changed_fields1]
FAILED tests/test_orrery/test_substrate.py::test_background_branch_refuses_relationship_effects[state_delta2-changed_fields2]
FAILED tests/test_orrery/test_substrate.py::test_background_branch_refuses_status_effect
FAILED tests/test_orrery/test_substrate.py::test_deviation_requires_background
7 failed, 73 deselected in 0.14s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_backstage_endpoints_pg.py -k attention
dbname audit: owner targets: none
2 passed, 13 deselected, 5 warnings in 3.13s
restored df19e18a680443a8ffbf33f4eeaaabb8fd22d1a9fb973dc55e7cd20947d90b20  nexus/agents/orrery/substrate.py
git diff --quiet: clean
```

The endpoint attention tests pass under plant A, as expected: the plant
removes construction-time refusals, not the authored roster or the lookup.

**B. Background pin removed from STROLL "Pace the near ground"**
(`templates.py` line 4119, `attention=AttentionClass.BACKGROUND,`):

```text
before   97a861ab824777d0dcb94111a6fb23d9f9f2c760fb4245432483a7342258dd67  nexus/agents/orrery/templates.py
planted  1f72f1e10c8f5900bbba19ea1a5f9514a39005f7cd09dc5aa11d56ac805378e6  nexus/agents/orrery/templates.py
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_substrate.py
E       AssertionError: assert {('drink', 'D...sehold'), ...} == {('drink', 'D...sehold'), ...}
FAILED tests/test_orrery/test_substrate.py::test_attention_roster_matches_ruling
1 failed, 79 passed in 0.13s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -vv -p tests.dbname_audit tests/test_orrery/test_substrate.py::test_attention_roster_matches_ruling
E         Extra items in the right set:
E         ('stroll', 'Pace the near ground')
dbname audit: owner targets: none
FAILED tests/test_orrery/test_substrate.py::test_attention_roster_matches_ruling
============================== 1 failed in 0.09s ===============================
$ uptime
17:10  up 6 days,  3:50, 5 users, load averages: 9.94 7.02 6.91
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_backstage_endpoints_pg.py -k attention
E                 {('stroll', 'Pace the near ground'): 'meaningful'} != {('stroll', 'Pace the near ground'): 'background'}
E                 At index 0 diff: ('stroll', 'Pace the near ground', 'meaningful') != ('stroll', 'Pace the near ground', 'background')
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa640_778s6a_backstage_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_backstage_endpoints_pg.py::test_payload_reports_known_branch_attention
FAILED tests/test_api/test_backstage_endpoints_pg.py::test_snapshot_reports_background_attention_without_pressure_row
2 failed, 13 deselected, 5 warnings in 3.11s
restored 97a861ab824777d0dcb94111a6fb23d9f9f2c760fb4245432483a7342258dd67  nexus/agents/orrery/templates.py
git diff --quiet: clean
```

**C. Backstage lookup replaced with `None`** (`backstage.py:732-734`,
`attention=attention_by_branch.get(...)` became `attention=None,`):

```text
before   a39f0b83d39a6b89ac887ceb0b83d71f09b621a9129c193fee5c2139d752e4cb  nexus/agents/orrery/backstage.py
planted  d15f19ebdcae00a2f53bfdd13e7c35f0b255380f5ff10f3bc351828bd1fb3b2b  nexus/agents/orrery/backstage.py
$ uptime
17:10  up 6 days,  3:50, 5 users, load averages: 15.02 8.29 7.37
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_substrate.py
dbname audit: owner targets: none
80 passed in 0.10s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_backstage_endpoints_pg.py
E               AssertionError: assert {('evade_purs...round'): None} == {('evade_purs... 'background'}
E                 {('evade_pursuers', 'Go to ground in flooded tunnels'): None} != {('evade_pursuers', 'Go to ground in flooded tunnels'): 'meaningful'}
E                 {('stroll', 'Pace the near ground'): None} != {('stroll', 'Pace the near ground'): 'background'}
E               AssertionError: assert [('stroll', '...round', None)] == [('stroll', '...'background')]
E                 At index 0 diff: ('stroll', 'Pace the near ground', None) != ('stroll', 'Pace the near ground', 'background')
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 4 targets: postgres, qa640_778s6a_backstage_*, qa640_778s6a_empty_*, qa640_uib_turn_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_backstage_endpoints_pg.py::test_payload_reports_known_branch_attention
FAILED tests/test_api/test_backstage_endpoints_pg.py::test_snapshot_reports_background_attention_without_pressure_row
2 failed, 13 passed, 9 warnings in 26.55s
restored a39f0b83d39a6b89ac887ceb0b83d71f09b621a9129c193fee5c2139d752e4cb  nexus/agents/orrery/backstage.py
git diff --quiet: clean
```

Both endpoint tests fail on the class mapping itself, not on setup or empty
output. The substrate file does not read the Backstage lookup, so it stays
green under plant C.

### Offline Suites

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1914 passed, 1529 skipped, 7 warnings in 48.54s

$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
3197 passed, 677 skipped, 8 warnings in 640.58s (0:10:40)
```

The skips are the PostgreSQL-gated tests of the offline run; the PostgreSQL
coverage is the focused set above plus the coordinator's whole gate.

### Configuration, Catalog and Exception Dispositions

```text
$ PYTHONPATH=$PWD nice -n 15 $PY scripts/validate_config_commit.py; echo "exit=$?"
exit=0
$ PYTHONPATH=$PWD nice -n 15 $PY -m nexus.agents.orrery.catalog --write
Wrote /Users/pythagor/nexus/.claude/worktrees/fix-784-s2/docs/orrery_packages.md
$ git diff --quiet -- docs/orrery_packages.md && echo "catalog: no diff"
catalog: no diff
$ git diff f073b371 --stat -- docs/orrery_packages.md
 docs/orrery_packages.md | 72 +++++++++++++++++++++++++------------------------
 1 file changed, 37 insertions(+), 35 deletions(-)
$ git diff f073b371 -- docs/orrery_packages.md | grep -c '^+.*\*\*background\*\*'
36
$ nice -n 15 $PY -S scripts/check_exception_dispositions.py --baseline-base-ref f073b371
OK: exception disposition coverage and shrink-only baseline verified.
```

The 36 added lines naming `**background**` are the 35 headings and the
intro paragraph; the 37th insertion is the blank line before it.

### Black, flake8 and mypy

Pre-existing diagnostics only: the two flake8 lists hold the same 14 E501
lines at shifted numbers. The file set is every Python file in `git diff --name-only c8abc33f 71f2b4f9`
plus `tests/test_orrery/test_config.py`: 16 files, all present on main.
Main's versions came from `git show f073b371:<path>` (flake8) and from
`git archive f073b371 nexus tests pyproject.toml` into a scratch tree
(mypy, which needs the whole package to resolve imports).

```text
$ nice -n 15 $PY -m black --check <16 files>
All done! ✨ 🍰 ✨
16 files would be left unchanged.
$ nice -n 15 $PY -m flake8 <16 files>            # head 4c066cba
nexus/agents/orrery/audit.py:1708:89: E501 line too long (114 > 88 characters)
nexus/agents/orrery/audit.py:1727:89: E501 line too long (89 > 88 characters)
nexus/agents/orrery/audit.py:1728:89: E501 line too long (90 > 88 characters)
nexus/agents/orrery/backstage.py:650:89: E501 line too long (91 > 88 characters)
nexus/config/settings_models.py:87:89: E501 line too long (89 > 88 characters)
nexus/config/settings_models.py:134:89: E501 line too long (90 > 88 characters)
nexus/config/settings_models.py:149:89: E501 line too long (101 > 88 characters)
nexus/config/settings_models.py:157:89: E501 line too long (91 > 88 characters)
nexus/config/settings_models.py:2524:89: E501 line too long (93 > 88 characters)
nexus/config/settings_models.py:4570:89: E501 line too long (131 > 88 characters)
tests/test_orrery/test_card_identity.py:233:89: E501 line too long (109 > 88 characters)
tests/test_orrery/test_card_identity.py:234:89: E501 line too long (96 > 88 characters)
tests/test_orrery/test_card_identity.py:272:89: E501 line too long (96 > 88 characters)
tests/test_orrery/test_card_identity.py:427:89: E501 line too long (110 > 88 characters)
$ nice -n 15 $PY -m flake8 <16 files>            # main f073b371
nexus/agents/orrery/audit.py:1701:89: E501 line too long (114 > 88 characters)
nexus/agents/orrery/audit.py:1720:89: E501 line too long (89 > 88 characters)
nexus/agents/orrery/audit.py:1721:89: E501 line too long (90 > 88 characters)
nexus/agents/orrery/backstage.py:547:89: E501 line too long (91 > 88 characters)
nexus/config/settings_models.py:87:89: E501 line too long (89 > 88 characters)
nexus/config/settings_models.py:134:89: E501 line too long (90 > 88 characters)
nexus/config/settings_models.py:149:89: E501 line too long (101 > 88 characters)
nexus/config/settings_models.py:157:89: E501 line too long (91 > 88 characters)
nexus/config/settings_models.py:2505:89: E501 line too long (93 > 88 characters)
nexus/config/settings_models.py:4518:89: E501 line too long (131 > 88 characters)
tests/test_orrery/test_card_identity.py:233:89: E501 line too long (109 > 88 characters)
tests/test_orrery/test_card_identity.py:234:89: E501 line too long (96 > 88 characters)
tests/test_orrery/test_card_identity.py:272:89: E501 line too long (96 > 88 characters)
tests/test_orrery/test_card_identity.py:414:89: E501 line too long (110 > 88 characters)
$ nice -n 15 $PY -m mypy --explicit-package-bases <16 files>   # head
Found 67 errors in 6 files (checked 16 source files)
$ nice -n 15 $PY -m mypy --explicit-package-bases <16 files>   # main scratch tree
Found 332 errors in 58 files (checked 16 source files)
```

Per changed file, head and main error counts are equal (backstage.py 11/11,
settings_models.py 11/11, test_card_identity.py 23/23, test_config.py
25/25, test_substrate.py 2/2, the rest 0/0) except
`tests/test_api/test_backstage_endpoints_pg.py` (6/0). Those six are the
`requests` missing-stub note, which mypy reports once at the first importer
(main reports it at `memnon.py:24`), and two `tomlkit` index errors at
`:1068`, a line from UI-B's commit `7557f00c`, not this lane. The higher
total on main comes from following imports into unchanged modules. No new
diagnostic sits on a line this lane changed.

### UI

```text
$ nice -n 15 npm --prefix ui ci
added 959 packages, and audited 960 packages in 3s
$ nice -n 15 npm --prefix ui run check
> tsc && npm run check:design-sync
> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
check exit=0
$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ✓ src/components/nexus/BackstageDrawer.test.tsx (12 tests)
 Test Files  1 failed | 40 passed (41)
      Tests  632 passed (632)
$ nice -n 15 npm --prefix ui test -- src/components/nexus/BackstageDrawer.test.tsx
 ✓ src/components/nexus/BackstageDrawer.test.tsx (12 tests) 233ms
 Test Files  1 passed (1)
      Tests  12 passed (12)
$ nice -n 15 npm --prefix ui run build
build exit=0
precache  22 entries (2322.17 KiB)
```

`state-shades.test.ts` fails only as stale, as expected. The build left
`git status --short` empty.

### Coordinator's Steps

- State-surface regeneration (order item 13): coordinator's step, run once
  on the final UI union. Then `npm --prefix ui test` including
  `state-shades.test.ts`. No measured sample should move: the `.55` rule
  applies only to `[data-attention="background"]` Backstage orrery rows, and
  the keyframe change only removes an end opacity that already equalled the
  computed opacity of every other `row-in` user. A moved sample is a
  stop-report item.
- The whole-tree PostgreSQL gate: coordinator's step.
- Landing: no migration and no fleet application. Product code changed
  (`substrate.py`, `templates.py`, `backstage.py`, `settings_models.py`), so
  a gateway restart is owed when the services run again; `ui/` changed, so a
  UI rebuild is owed. The class is on no model wire. This slice closes
  neither #784 nor 784-S3a, S3b, S4a, S4b or S5.
