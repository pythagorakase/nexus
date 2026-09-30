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
