# Issue 811 Slice B: Deprecated-Category Audit Verification

Branch `claude/811-tags-audit`, rebased onto `origin/main` at 813c23d9 on
2026-09-29. No migration and no paid calls. No `save_NN` database or
`NEXUS_template` was written: the audit opens each database in a read-only,
repeatable-read transaction, and every PostgreSQL test ran on the disposable
clones its fixtures create and drop.

## Fleet Audit (Read-Only)

Expected baseline from slice A (`docs/qa/811-stale-vocab-dead-helpers/verification.md`):
0/0/4/6/0 active rows on slots 1–5, and 0 on the template. The audit matches it.

```text
$ PYTHONPATH=$PWD $PY -m nexus.cli tags audit --all --json
{
  "data": {
    "active_rows": 10,
    "databases": [
      {
        "active_rows": 0,
        "database": "NEXUS_template",
        "deprecated_categories": [
          "bodyform",
          "hidden_agenda_class",
          "history_class",
          "ideology_axis",
          "legitimacy_status",
          "operational_secrecy",
          "orrery_signal",
          "place_affordance",
          "power_posture",
          "profession_lite",
          "resource_class",
          "role"
        ],
        "groups": [],
        "slot": null
      },
      {
        "active_rows": 0,
        "database": "save_01",
        "deprecated_categories": [
          "bodyform",
          "hidden_agenda_class",
          "history_class",
          "ideology_axis",
          "legitimacy_status",
          "operational_secrecy",
          "orrery_signal",
          "place_affordance",
          "power_posture",
          "profession_lite",
          "resource_class",
          "role"
        ],
        "groups": [],
        "slot": 1
      },
      {
        "active_rows": 0,
        "database": "save_02",
        "deprecated_categories": [
          "bodyform",
          "hidden_agenda_class",
          "history_class",
          "ideology_axis",
          "legitimacy_status",
          "operational_secrecy",
          "orrery_signal",
          "place_affordance",
          "power_posture",
          "profession_lite",
          "resource_class",
          "role"
        ],
        "groups": [],
        "slot": 2
      },
      {
        "active_rows": 4,
        "database": "save_03",
        "deprecated_categories": [
          "bodyform",
          "hidden_agenda_class",
          "history_class",
          "ideology_axis",
          "legitimacy_status",
          "operational_secrecy",
          "orrery_signal",
          "place_affordance",
          "power_posture",
          "profession_lite",
          "resource_class",
          "role"
        ],
        "groups": [
          {
            "category": "orrery_signal",
            "entity_ids": [
              3
            ],
            "replacement_categories": [
              "state"
            ],
            "row_count": 1,
            "tag": "debt_pulse_active"
          },
          {
            "category": "place_affordance",
            "entity_ids": [
              24
            ],
            "replacement_categories": [
              "place_function",
              "place_visibility",
              "place_access",
              "place_environment",
              "place_threat"
            ],
            "row_count": 1,
            "tag": "worksite"
          },
          {
            "category": "profession_lite",
            "entity_ids": [
              3,
              26
            ],
            "replacement_categories": [
              "role.function"
            ],
            "row_count": 2,
            "tag": "black_market_operator"
          }
        ],
        "slot": 3
      },
      {
        "active_rows": 6,
        "database": "save_04",
        "deprecated_categories": [
          "bodyform",
          "hidden_agenda_class",
          "history_class",
          "ideology_axis",
          "legitimacy_status",
          "operational_secrecy",
          "orrery_signal",
          "place_affordance",
          "power_posture",
          "profession_lite",
          "resource_class",
          "role"
        ],
        "groups": [
          {
            "category": "legitimacy_status",
            "entity_ids": [
              32
            ],
            "replacement_categories": [
              "legitimacy"
            ],
            "row_count": 1,
            "tag": "gray_legal"
          },
          {
            "category": "orrery_signal",
            "entity_ids": [
              1,
              3
            ],
            "replacement_categories": [
              "state"
            ],
            "row_count": 2,
            "tag": "debt_pulse_active"
          },
          {
            "category": "place_affordance",
            "entity_ids": [
              24
            ],
            "replacement_categories": [
              "place_function",
              "place_visibility",
              "place_access",
              "place_environment",
              "place_threat"
            ],
            "row_count": 1,
            "tag": "worksite"
          },
          {
            "category": "profession_lite",
            "entity_ids": [
              3,
              26
            ],
            "replacement_categories": [
              "role.function"
            ],
            "row_count": 2,
            "tag": "black_market_operator"
          }
        ],
        "slot": 4
      },
      {
        "active_rows": 0,
        "database": "save_05",
        "deprecated_categories": [
          "bodyform",
          "hidden_agenda_class",
          "history_class",
          "ideology_axis",
          "legitimacy_status",
          "operational_secrecy",
          "orrery_signal",
          "place_affordance",
          "power_posture",
          "profession_lite",
          "resource_class",
          "role"
        ],
        "groups": [],
        "slot": 5
      }
    ]
  },
  "ok": true
}
```

The same audit in the human format:

```text
$ PYTHONPATH=$PWD $PY -m nexus.cli tags audit --all
DATABASE        ROWS
NEXUS_template  0
save_01         0
save_02         0
save_03         4
save_04         6
save_05         0

DATABASE  CATEGORY           TAG                    ROWS  ENTITIES  REPLACEMENTS
save_03   orrery_signal      debt_pulse_active      1     3         state
save_03   place_affordance   worksite               1     24        place_function,place_visibility,place_access,place_environment,place_threat
save_03   profession_lite    black_market_operator  2     3,26      role.function
save_04   legitimacy_status  gray_legal             1     32        legitimacy
save_04   orrery_signal      debt_pulse_active      2     1,3       state
save_04   place_affordance   worksite               1     24        place_function,place_visibility,place_access,place_environment,place_threat
save_04   profession_lite    black_market_operator  2     3,26      role.function
```

`orrery_signal` is also deprecated by migration 043 (replacement `state`); the
`orrery_` prefix pin already keeps it prompt-visible only for Retrograde.

## Named PostgreSQL Tests

Gateway variables unset.

```text
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_tag_library.py tests/test_orrery/test_tag_writer.py tests/test_orrery/test_retrograde_vocabulary.py tests/test_orrery/test_retrograde_seed_candidates.py tests/test_orrery/test_retrograde_expansion.py tests/test_cli_contract.py tests/test_cli.py tests/test_turn_observation.py tests/test_tags_audit_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
1 failed, 386 passed, 1 skipped, 5 warnings in 93.79s (0:01:33)
```

The one failure is the known #885 exemption: the test hardwires the owner's
`save_05`, which is an empty story, and fails at
`assert entity_refs, "save_05 must contain current entity tags"`
(`tests/test_orrery/test_tag_library.py:551`). The branch does not touch it.

Fixture follow-ups for the library filter (item 2), also on PostgreSQL:

```text
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery_tag_validation_pg.py tests/test_orrery/test_gaia_registry_schema_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
33 passed, 1 skipped, 5 warnings in 4.66s
```

The skip is the live Gaia enum gate (`NEXUS_638_ENUM_E2E=1`, paid).

## Session-Truth Proof on Lane 8018

Against a `save_04` clone (`qa640_775_browser`), TEST provider only.

```text
$ NEXUS_RUN_POSTGRES=1 NEXUS_GATEWAY_PORT=8018 NEXUS_API_URL=http://127.0.0.1:8018 $PY -m pytest -q -s tests/proofs/proof_session_truth.py
Lane 8018; evidence directory /private/var/folders/r5/zvbnrwp55r7dctnkr9s3b3780000gn/T/pytest-of-pythagor/pytest-1016/test_disconnected_session_brow0/775-session-truth
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed, 12 warnings in 95.59s (0:01:35)
$ git status --porcelain docs/qa/775-session-truth | wc -l
       0
$ nexus down   # NEXUS_GATEWAY_PORT=8018
nothing running
$ lsof -nP -iTCP:8018 -sTCP:LISTEN; echo $?
1
```

The evidence (two screenshots, `provider-usage.json`, `session-rows.json`)
landed in the pytest temporary directory; the tracked
`docs/qa/775-session-truth` stayed untouched.

## Offline Suite

Run in two pieces for the ten-minute shell limit, gateway and PostgreSQL
variables unset.

```text
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2444 passed, 356 skipped, 8 warnings in 354.09s (0:05:54)
$ $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 728 skipped, 7 warnings in 29.85s
$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.92s
```

After the final rebase onto 813c23d9 (#1029 changed only
`tests/test_api/test_place_reference_validation_pg.py` and
`tests/test_api/test_session_truth_pg.py`):

```text
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api/test_place_reference_validation_pg.py tests/test_api/test_session_truth_pg.py
7 passed, 7 warnings in 15.57s
```

## Static Checks on Changed Files

- Black: `23 files would be left unchanged.`
- flake8: no finding the branch introduces. Compared with the `origin/main`
  copies of the same files under the repository's `.flake8`, the branch
  removes two long lines in `nexus/presence/identity.py`, and every remaining
  finding already exists on main.
- mypy (the `nexus/` files): six errors, all on lines from before this branch
  (`nexus/presence/identity.py:171,281-283` from e0d9424c,
  `nexus/presence/roster.py:398` from 82ca8a9d). The test files cannot be
  checked together because mypy finds `tests/test_orrery/__init__.py` under
  two module names, as on main.

## Review Fixes: Clears Stay Open, and the Last Async Twin

Review found that the registry filter on the prompt-facing library also
narrowed the vocabulary that clears are checked against. With it, Skald and
Gaia could no longer clear the ten active deprecated-category rows on
`save_03` and `save_04` (`worksite`, `black_market_operator`, `gray_legal`,
`debt_pulse_active`). Blocking those clears would be write-gate enforcement,
which stays on #811 behind the owner's rulings. The fix:

- `read_tag_library(..., include_deprecated_categories=True)` drops only the
  registry-category predicate, and each entry now carries
  `category_deprecated`. `read_storyteller_vocabulary` makes one read and
  splits it. `tag_names_by_kind` (the add and hint vocabulary) stays filtered.
  The new `clearable_tag_names_by_kind` also holds the 97 live tags of
  deprecated categories.
- The generation-time validator checks `tags_to_clear` (and replacement
  `entity_tags_*_remove`) against `StorytellerVocabulary.clearable_tags(kind)`.
  An add of those tags is still rejected.
- Gaia's strict grammar: `tags_clear` items are `anyOf` of `<Kind>TagName` and
  a new `<Kind>ClearOnlyTagName` enum. `tags_add` and `tag_hints` keep only
  `<Kind>TagName`. The enum-value count is back to 625 (25,920 bytes / 6,349
  tokens, inside the 26,800 / 6,600 ceilings). This replaces the 528 given in
  09f68223.
- `canonical_player_character_id_async` (`nexus/agents/orrery/player_identity.py`)
  lost its only caller when `story_active_zone_async` was deleted, so it is
  deleted too. `_PLAYER_IDENTITY_SQL` and `_coerce_player_identity` stay:
  the sync `_canonical_player_identity` still uses both.

New PostgreSQL tests on the `qa649_*` template clone, one per entity kind
(`black_market_operator`, `worksite`, `gray_legal`): the validator accepts
the clear and rejects the add, and the registry Gaia model validates the
clear and raises `ValidationError` on the add.

```text
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery_tag_validation_pg.py -k deprecated_category
6 passed, 31 deselected, 5 warnings in 1.61s
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery_tag_validation_pg.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_orrery/test_tag_library.py tests/test_orrery/test_tag_writer.py tests/test_orrery/test_retrograde_vocabulary.py tests/test_orrery/test_retrograde_seed_candidates.py tests/test_orrery/test_retrograde_expansion.py tests/test_tags_audit_pg.py tests/test_player_identity_consumers_pg.py tests/test_orrery/test_identity_consumers_pg.py
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
1 failed, 240 passed, 2 skipped, 7 warnings in 35.27s
$ $PY -m pytest -q tests/test_reachability.py tests/test_orrery_tag_validation.py
90 passed, 5 warnings in 10.17s
$ $PY -m pytest -q -x
4250 passed, 1090 skipped, 8 warnings in 385.44s (0:06:25)
```

The one failure is the #885 `save_05` exemption described above. Black is
clean on the changed files. flake8 and mypy report only findings that also
exist on the HEAD copies of `orrery_tag_validation.py` and
`tests/test_orrery_tag_validation_pg.py` (three and three E501 long lines,
and two mypy `index` errors). No gateway was started for these fixes.

## Review Fixes: The Turn-Observation Clock

Review found that `tests/test_turn_observation.py` still read its instant and
`TODAY` at import, and that no test advanced the clock. The module now has no
import-time clock values. The autouse `ledger_clock` fixture reads the
writer's own clock when each test starts, pins `usage_ledger.datetime` to
that instant, and yields a settable `_LedgerClock`; each test derives
`today`, `yesterday`, `read_at` and the job enqueue time from it.

`test_a_turn_straddling_utc_midnight_writes_and_joins_both_days` sets the
clock to 23:59:59.9 UTC, records the writer's prompt window and usage event,
advances 200 ms past midnight, records Gaia's, and calls `observe_turn` with
`read_at` on the new day. Each record is in its own day's `windows-*.jsonl`
and `usage-*.jsonl`, `ledger_days_read` is `[yesterday, today]`, and both
attempts join their window and usage. Changing `record_prompt_window` to read
the real `datetime` makes the test fail
(`assert ['skald_writer', 'gaia'] == ['skald_writer']`); the file was
restored afterwards.

The docstring of `tests/test_character_name_reveals_pg.py` no longer says
"sync/async": its only async test went with the async cluster.

```text
$ $PY -m pytest -q tests/test_turn_observation.py
14 passed, 5 warnings in 1.23s
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_tag_library.py tests/test_orrery/test_tag_writer.py tests/test_orrery/test_retrograde_vocabulary.py tests/test_orrery/test_retrograde_seed_candidates.py tests/test_orrery/test_retrograde_expansion.py tests/test_cli_contract.py tests/test_cli.py tests/test_turn_observation.py tests/test_tags_audit_pg.py
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
1 failed, 387 passed, 1 skipped, 5 warnings in 97.97s (0:01:37)
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery_tag_validation_pg.py tests/test_orrery_tag_validation.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_character_name_reveals_pg.py
93 passed, 1 skipped, 5 warnings in 10.38s
$ $PY -m pytest -q tests/test_reachability.py
38 passed in 8.99s
```

The one failure is the #885 `save_05` exemption. Black and flake8 are clean
on `tests/test_turn_observation.py`, and mypy reports no issues in it.

## Review Fixes: `mood` and `write_roster_async`

Review found that the R1 spec and the comment above
`STABLE_SEED_TAG_CATEGORIES` said every live registry category is classified
explicitly, but the live `mood` category (migration 095) is in neither
seed-eligible set and has no `orrery_` prefix. It reaches
`prompt_visible_only` only through the unclassified default. Both texts now
name `mood` as the one live category that deliberately takes that default
(transient affect, never seeded). The template registry confirms it is the
only one:

```text
$ psql -d NEXUS_template -Atc "select count(*), count(*) filter (where not deprecated) from tag_category_registry"
45|33
```

Of the 33 live categories, the ones outside `STABLE_SEED_TAG_CATEGORIES`,
`EVENT_ANCHORED_TAG_CATEGORIES`, and the `orrery_` prefix are `{mood}`.
`test_registry_deprecated_categories_are_never_seed_eligible` now reads the
whole registry from its template clone and also asserts that set equals
`{"mood"}`, so a new unclassified live category fails there.

`write_roster_async` (`nexus/presence/roster.py`) had no caller in `nexus/`,
`scripts/`, `ir_eval/`, or `tests/` (`grep -rn write_roster_async .` returns
only its definition), the same dead asyncpg twin as `read_roster_async`, so
it is deleted. `re` stays for the sync `write_roster`.

```text
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_retrograde_vocabulary.py tests/test_reachability.py
66 passed, 5 warnings in 10.99s
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_presence_roster.py tests/test_presence_roster_pg.py tests/test_commit_choice_presence_pg.py tests/test_presence_reconciliation.py
81 passed, 5 warnings in 35.02s
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery_tag_validation_pg.py tests/test_orrery/test_gaia_registry_schema_pg.py
SKIPPED [1] tests/test_orrery/test_gaia_registry_schema_pg.py:250: Set NEXUS_638_ENUM_E2E=1 for the live Gaia enum-schema gate.
39 passed, 1 skipped, 5 warnings in 6.39s
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_tag_library.py tests/test_orrery/test_tag_writer.py tests/test_orrery/test_retrograde_vocabulary.py tests/test_orrery/test_retrograde_seed_candidates.py tests/test_orrery/test_retrograde_expansion.py tests/test_cli_contract.py tests/test_cli.py tests/test_turn_observation.py tests/test_tags_audit_pg.py
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
1 failed, 387 passed, 1 skipped, 5 warnings in 97.50s (0:01:37)
```

The one failure is the #885 `save_05` exemption
(`tests/test_orrery/test_tag_library.py:554`). Black is clean on the three
changed Python files. flake8 and mypy report only findings that also exist on
the HEAD copy of `nexus/presence/roster.py` (nine E501 SQL lines, and the
mypy `arg-type` error at line 398); `retrograde_vocabulary.py` and the test
file are clean. No gateway was started for these fixes.

## Review Round (Astra)

Astra's review of the PR (`CHANGES_REQUIRED`, three P2 findings) and the fixes:

1. **Scene visibility.** `format_contextual_tag_library` now reads the shared
   query once with `include_deprecated_categories=True`. The taxonomy, name
   index, and digest keep only live categories. Under Scene-Relevant Tags it
   also renders each deprecated-category entry whose tag is active on a
   present entity (`read_current_entity_tag_names`), with ` (clear only)` on
   the entry line. A proposal never selects such an entry.
   `test_scene_shows_a_present_entitys_deprecated_tag_as_clear_only` seeds two
   places on a template clone, one carrying `worksite`, and checks both scenes
   plus the default-keyword library and taxonomy.
2. **Active-row clearance set.** The shared query gains `active_somewhere`
   (an `EXISTS` over uncleared `entity_tags` rows on entities of the entry's
   kind), computed only with `include_deprecated_categories=True`, in the same
   statement and so the same snapshot as the library. `read_storyteller_vocabulary`
   adds a deprecated-category name to the clearable set only when it is
   active; a name active nowhere is unknown to both fields. Gaia's
   `<Kind>ClearOnlyTagName` enums now come from the turn's present entities
   (cast, setting, player; `present_entity_refs` in `logon_utility.py`, shared
   with the contextual library) intersected with that clearable set, so a turn
   whose scene carries no deprecated tag has no clear-only enum at all.
   Tests: `test_deprecated_category_tag_is_clearable_only_while_a_row_is_active`
   (per kind: unknown, then clearable while active, cleared through the real
   validator and commit route, then unknown),
   `test_worksite_stays_clearable_until_its_last_active_row_is_cleared`,
   `test_gaia_grammar_clears_a_deprecated_category_tag_only_in_its_scene`, and
   `test_turn_grammar_offers_a_deprecated_tag_only_when_a_present_entity_has_it`
   (LOGON's own `_gaia_schema_model` on a template clone with two places).
   Without a scene the template grammar has 528 enum values (the 97
   deprecated-category tags left the add/hint enums and no longer ride along as
   clear-only), measured at 23,846 bytes / 5,806 o200k tokens, inside the
   pinned 26,800 / 6,600 ceilings.
3. **Audit preflight.** `_require_schema` now checks every table and column
   the two audit statements read (`entity_tags.entity_id`, `.tag_id`,
   `.cleared_at`; `tags.id`, `.tag`, `.category`;
   `tag_category_registry.category`, `.entity_kind`, `.deprecated`,
   `.replacement_categories`), each naming the migration that created it.
   `test_all_audit_missing_an_entity_tags_column_keeps_the_partial` drops
   `entity_tags.cleared_at` on a second clone routed as slot 3 and runs
   `nexus tags audit --all --json` through `cli.main()`: the domain-failure
   envelope names `023_orrery_schema` and its `partial.databases` keeps the
   template clone's report. On the pre-fix preflight the same test fails with
   PostgreSQL's `UndefinedColumn`.

```text
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfs tests/test_orrery/test_tag_library.py tests/test_orrery_tag_validation_pg.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_tags_audit_pg.py tests/test_cli_contract.py tests/test_skald_wire.py tests/test_lore/test_two_pass_pipeline.py tests/test_prompt_lint.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
SKIPPED [1] tests/test_orrery/test_tag_library.py:708: save_05 has no character whose characters.id differs from characters.entity_id; cannot exercise namespace translation
SKIPPED [1] tests/test_orrery/test_gaia_registry_schema_pg.py:348: Set NEXUS_638_ENUM_E2E=1 for the live Gaia enum-schema gate.
SKIPPED [1] tests/test_skald_wire.py:2061: Slot has no parent chunk with presence junction rows
SKIPPED [1] tests/test_skald_wire.py:2094: Set NEXUS_639_PRESENCE_E2E=1 for the live writer presence gate.
1 failed, 341 passed, 4 skipped, 5 warnings in 117.74s (0:01:57)
$ $PY -m pytest -q tests/test_reachability.py
38 passed in 9.22s
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery_tag_validation.py tests/test_orrery/test_tag_writer.py tests/test_orrery/test_retrograde_vocabulary.py tests/test_lore/test_pass2_baseline_pg.py tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_place_reference_validation.py tests/test_name_reveal_tag_validation.py tests/test_reachability.py tests/test_cli.py
258 passed, 9 warnings in 41.66s
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/config tests/test_orrery/test_bleed.py tests/test_lore/test_turn_cycle.py tests/test_lore/test_seat_blocks.py tests/test_lore/test_historical_render.py tests/test_lore/test_window_coverage_pg.py tests/test_lore/test_seat_window.py
204 passed, 5 warnings in 16.29s
$ $PY -m pytest -q tests/test_lore tests/test_orrery tests/test_api
2212 passed, 780 skipped, 7 warnings in 49.11s
```

The one failure is the #885 `save_05` exemption (slot 5 is an empty story:
"save_05 must contain current entity tags"). The two new place-seeding tests
each spend about 50 s in `disposable_slot_database` teardown: a bare clone and
drop measured `clone 1.1s drop 51.6s` on this machine tonight, so the time is
`DROP DATABASE`, not the code under test.

The fleet audit after the preflight change, read-only, is unchanged:

```text
$ PYTHONPATH=$PWD $PY -m nexus.cli tags audit --all
DATABASE        ROWS
NEXUS_template  0
save_01         0
save_02         0
save_03         4
save_04         6
save_05         0

DATABASE  CATEGORY           TAG                    ROWS  ENTITIES  REPLACEMENTS
save_03   orrery_signal      debt_pulse_active      1     3         state
save_03   place_affordance   worksite               1     24        place_function,place_visibility,place_access,place_environment,place_threat
save_03   profession_lite    black_market_operator  2     3,26      role.function
save_04   legitimacy_status  gray_legal             1     32        legitimacy
save_04   orrery_signal      debt_pulse_active      2     1,3       state
save_04   place_affordance   worksite               1     24        place_function,place_visibility,place_access,place_environment,place_threat
save_04   profession_lite    black_market_operator  2     3,26      role.function
```

Black is clean on the ten changed Python files. flake8 and mypy report only
findings that the HEAD copies of the same files also report (flake8: E501 and
F401 lines in `orrery_tag_validation.py`, `logon_utility.py`, and
`test_orrery_tag_validation_pg.py`; mypy: the same 12 errors in
`orrery_tag_validation.py` and `logon_utility.py`, compared line-number
blind). No gateway was started and no provider was called.

### Follow-Up: Faction Reach and Kind-Scoped Scene Lines

Astra's verification of 6d77aa5a found one overstated claim and one latent
mismatch; the coordinator ruled not to invent a faction scope.

1. **What the Gaia path reaches.** The character and place rows (the nine on
   slots 3 and 4: `debt_pulse_active`, `worksite`, `black_market_operator`)
   are clear-only entries in any scene whose present entities carry them. The
   faction row `gray_legal` (save_04 entity 32) has no scene presence: a
   turn's `PresenceBaseline` holds characters and the setting place, so
   `present_entity_refs` (`nexus/agents/lore/logon_utility.py:285-310`) never
   yields a faction and Gaia's strict grammar cannot clear it, while the
   validator and the manifest tooling still accept the clear. Its disposition
   is the owner's ruling. The PR body's "Clearance Stays Possible" section and
   the remaining-on-#811 bullet now say this instead of "all ten remain
   clearable by the writer".
2. **The grammar test takes its scene from a real turn.**
   `test_gaia_grammar_clears_a_deprecated_category_tag_only_in_its_scene` now
   runs for the character and place rows only, and builds each grammar through
   LOGON's `_gaia_schema_model` from a real `PresenceBaseline` (the carrier in
   the cast or as the setting, against a player-only scene). The hand-made
   faction scene is gone. The new
   `test_turn_grammar_cannot_clear_an_active_faction_tag_the_validator_accepts`
   asserts the limitation: while `gray_legal` is active, the validator's clear
   set holds it and a `tags_clear` payload collects no issue, yet the turn
   grammar (for a scene with two characters and the place, and for a
   player-only scene) has no `FactionClearOnlyTagName` and rejects the clear.
3. **Scene lines follow the carrier's kind.** `format_contextual_tag_library`
   (`nexus/agents/orrery/tag_library.py`) groups `present_entity_refs` by kind,
   reads the active names per kind, and selects a deprecated-category entry
   only when its tag is active for `entry.entity_kind`, as
   `_scene_clear_only_tags` does for the grammar.
   `test_scene_clear_only_line_follows_the_carrying_entitys_kind` registers
   `place_affordance` for characters too (still deprecated) on a clone, puts
   `worksite` on a present character with a bare place also present, and
   asserts the only ` (clear only)` line is the character-kind entry. Against
   the previous code the same test fails with the extra line
   `- place/place_affordance: `worksite`: ... (clear only)`.

```text
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfs tests/test_orrery/test_tag_library.py tests/test_orrery_tag_validation_pg.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_lore/test_two_pass_pipeline.py tests/test_skald_wire.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
SKIPPED [1] tests/test_orrery/test_tag_library.py:781: save_05 has no character whose characters.id differs from characters.entity_id; cannot exercise namespace translation
SKIPPED [1] tests/test_orrery/test_gaia_registry_schema_pg.py:348: Set NEXUS_638_ENUM_E2E=1 for the live Gaia enum-schema gate.
SKIPPED [1] tests/test_skald_wire.py:2061: Slot has no parent chunk with presence junction rows
SKIPPED [1] tests/test_skald_wire.py:2094: Set NEXUS_639_PRESENCE_E2E=1 for the live writer presence gate.
1 failed, 189 passed, 4 skipped, 5 warnings in 16.26s
$ $PY -m black --check nexus/agents/orrery/tag_library.py tests/test_orrery/test_tag_library.py tests/test_orrery_tag_validation_pg.py
3 files would be left unchanged.
$ $PY -m flake8 nexus/agents/orrery/tag_library.py tests/test_orrery/test_tag_library.py tests/test_orrery_tag_validation_pg.py
tests/test_orrery_tag_validation_pg.py:229:89: E501 line too long (93 > 88 characters)
tests/test_orrery_tag_validation_pg.py:230:89: E501 line too long (89 > 88 characters)
tests/test_orrery_tag_validation_pg.py:306:89: E501 line too long (98 > 88 characters)
$ $PY -m mypy nexus/agents/orrery/tag_library.py
Success: no issues found in 1 source file
```

The one failure is the #885 `save_05` exemption ("save_05 must contain
current entity tags"). The three E501 lines are in the `qa649_db` fixture and
exist on the HEAD copy (lines 224, 225, and 301 there). Gateway variables were
unset; no gateway was started and no provider was called.
