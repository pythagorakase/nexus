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
$ psql -d NEXUS_template -Atc "select category, deprecated from tag_category_registry order by 1"
```

Of the 46 rows, the live categories outside `STABLE_SEED_TAG_CATEGORIES`,
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
