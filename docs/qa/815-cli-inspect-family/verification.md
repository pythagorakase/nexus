# CLI Session Waiter and Inspect Family: Verification

Work order 815-A. Issue #815. Base: `origin/main` at 3ca248df. No migration. Gateway lane 8017, TEST provider only, no paid calls.

**Write safety.** The PostgreSQL proof writes only a disposable `qa640_815_inspect_*` clone created and dropped by `tests.pg_fixtures.disposable_slot_database`; slot 4 is routed to the clone in process (`tests.scheduler_helpers.route_slot`). No `save_NN` or `NEXUS_template` was written. No `qa640_815*` database remains after the runs (`psql -d postgres -Atc "select datname from pg_database where datname like 'qa640_815%'"` printed nothing).

## What Changed

- `nexus/cli.py`: `wait_for_session(session_id, *, slot, timeout, interval)` is the one waiter. `_wait_for_narrative_result` composes it with the slot-state load and serves `continue`, `retry`, `regenerate`, and the seed's opening turn. `regenerate`'s own loop is deleted.
- `nexus/cli.py`: `nexus inspect chunks|chunk|incubator|characters|places|factions`, each reading player-plane GET routes and passing their bodies through under `data`.
- `nexus/cli_contract.py`: the six verbs are `http` transport and `ENVELOPE_COMMANDS`; the docstring states how a saved-work failure reports a lost gateway.
- `nexus/config/settings_models.py`, `nexus.toml`: `[runtime.cli] poll_interval_seconds = 1.0`.
- `docs/cli.md`: the inspect table and a Waiting on a Generation section.

## Session-Wait Contract

1. Reads `GET /api/narrative/status/{id}?slot=N` every `[runtime.cli].poll_interval_seconds`, within `[apex].generation_timeout_seconds` overall; returns the terminal status payload.
2. `status: "error"` from the API: domain failure (exit 1) whose `error` is the API's message.
3. Budget spent while the session runs, an HTTP error answer, or an unusable payload: domain failure (exit 1).
4. Connection refused or dropped mid-wait: `api_unreachable` (exit 4). A failed read is never retried.
5. Every failed wait keeps `session_id`, `generation_error`, and `recovery_command` (and the saved seed) in `partial`.

## CLI Transcript on the Played Clone

`tests/test_cli_inspect_pg.py`, run with `-s`: `seed_played_story(turns=3, cast=("Mara Quill", "Oren Vale"))`, one seeded faction, and a pending turn from `seed_pending_turn`, served by the in-process gateway on 127.0.0.1:8017 with every provider routed to TEST. Each command ran as a `python -m nexus.cli` subprocess. Verbatim stdout (tokenizer fork warnings removed):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -s -p no:warnings tests/test_cli_inspect_pg.py
$ nexus continue --slot 4 --choice 1 --json
{
  "choices": [
    "Continue following the immediate lead.",
    "Pause and reassess the pressure around the scene.",
    "Shift attention to the quieter off-screen consequence."
  ],
  "chunk_id": null,
  "message": "[TEST MODE] The scene advances under deterministic mock control. Orrery pressure is acknowledged structurally, while the prose remains simple enough for integration tests to inspect.",
  "session_id": "d94d1054-b1b6-4b4c-91c0-ffa1d02c5074",
  "success": true
}

$ nexus inspect chunks --last 2 --slot 4 --json
{
  "data": [
    {
      "choiceObject": {
        "presented": [
          "Press on toward the lit doorway.",
          "Wait and watch the street.",
          "Ask the nearest stranger for directions."
        ],
        "selected": 1
      },
      "choiceText": "Press on toward the lit doorway.",
      "createdAt": "2026-09-29T23:47:05.417539Z",
      "hasInlineSceneMarkup": false,
      "id": 3,
      "metadata": {
        "chunkId": 3,
        "episode": 1,
        "generationDate": "2026-09-29T23:47:05.426491",
        "id": 3,
        "scene": 3,
        "season": 1,
        "slug": "S01E01_003",
        "timeDelta": "02:00:00",
        "worldLayer": "primary",
        "worldTime": "2100-01-01T04:00:00+00:00",
        "worldTimeFace": "1 Jan 2100 \u00b7 04:00"
      },
      "rawText": "Fixture turn 3: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business.\n\nPress on toward the lit doorway.",
      "storytellerText": "Fixture turn 3: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business."
    },
    {
      "choiceObject": {
        "presented": [
          "Press on toward the lit doorway.",
          "Wait and watch the street.",
          "Ask the nearest stranger for directions."
        ],
        "selected": 1
      },
      "choiceText": "Press on toward the lit doorway.",
      "createdAt": "2026-09-29T23:47:06.338548Z",
      "hasInlineSceneMarkup": false,
      "id": 4,
      "metadata": {
        "chunkId": 4,
        "episode": 1,
        "generationDate": "2026-09-29T23:47:06.349332",
        "id": 4,
        "scene": 4,
        "season": 1,
        "slug": "S01E01_004",
        "timeDelta": "00:05:00",
        "worldLayer": "primary",
        "worldTime": "2100-01-01T04:05:00+00:00",
        "worldTimeFace": "1 Jan 2100 \u00b7 04:05"
      },
      "rawText": "The pending fixture turn waits for the player's choice.\n\nPress on toward the lit doorway.",
      "storytellerText": "The pending fixture turn waits for the player's choice."
    }
  ],
  "ok": true
}

$ nexus inspect chunks --from 1 --to 2 --slot 4 --json
{
  "data": [
    {
      "choiceObject": {
        "presented": [
          "Press on toward the lit doorway.",
          "Wait and watch the street.",
          "Ask the nearest stranger for directions."
        ],
        "selected": 1
      },
      "choiceText": "Press on toward the lit doorway.",
      "createdAt": "2026-09-29T23:47:05.100604Z",
      "hasInlineSceneMarkup": false,
      "id": 1,
      "metadata": {
        "chunkId": 1,
        "episode": 1,
        "generationDate": "2026-09-29T23:47:05.109560",
        "id": 1,
        "scene": 1,
        "season": 1,
        "slug": "S01E01_001",
        "timeDelta": "00:00:00",
        "worldLayer": "primary",
        "worldTime": "2100-01-01T00:00:00+00:00",
        "worldTimeFace": "1 Jan 2100 \u00b7 00:00"
      },
      "rawText": "Fixture turn 1: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business.\n\nPress on toward the lit doorway.",
      "storytellerText": "Fixture turn 1: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business."
    },
    {
      "choiceObject": {
        "presented": [
          "Press on toward the lit doorway.",
          "Wait and watch the street.",
          "Ask the nearest stranger for directions."
        ],
        "selected": 1
      },
      "choiceText": "Press on toward the lit doorway.",
      "createdAt": "2026-09-29T23:47:05.244014Z",
      "hasInlineSceneMarkup": false,
      "id": 2,
      "metadata": {
        "chunkId": 2,
        "episode": 1,
        "generationDate": "2026-09-29T23:47:05.253059",
        "id": 2,
        "scene": 2,
        "season": 1,
        "slug": "S01E01_002",
        "timeDelta": "02:00:00",
        "worldLayer": "primary",
        "worldTime": "2100-01-01T02:00:00+00:00",
        "worldTimeFace": "1 Jan 2100 \u00b7 02:00"
      },
      "rawText": "Fixture turn 2: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business.\n\nPress on toward the lit doorway.",
      "storytellerText": "Fixture turn 2: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business."
    }
  ],
  "ok": true
}

$ nexus inspect chunk 2 --slot 4 --json
{
  "data": {
    "choiceObject": {
      "presented": [
        "Press on toward the lit doorway.",
        "Wait and watch the street.",
        "Ask the nearest stranger for directions."
      ],
      "selected": 1
    },
    "choiceText": "Press on toward the lit doorway.",
    "createdAt": "2026-09-29T23:47:05.244014Z",
    "hasInlineSceneMarkup": false,
    "id": 2,
    "metadata": {
      "chunkId": 2,
      "episode": 1,
      "generationDate": "2026-09-29T23:47:05.253059",
      "id": 2,
      "scene": 2,
      "season": 1,
      "slug": "S01E01_002",
      "timeDelta": "02:00:00",
      "worldLayer": "primary",
      "worldTime": "2100-01-01T02:00:00+00:00",
      "worldTimeFace": "1 Jan 2100 \u00b7 02:00"
    },
    "rawText": "Fixture turn 2: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business.\n\nPress on toward the lit doorway.",
    "storytellerText": "Fixture turn 2: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business."
  },
  "ok": true
}

$ nexus inspect incubator --slot 4 --json
{
  "data": {
    "authorial_directives": [],
    "choice_object": {
      "presented": [
        "Continue following the immediate lead.",
        "Pause and reassess the pressure around the scene.",
        "Shift attention to the quieter off-screen consequence."
      ],
      "selected": null
    },
    "choice_text": null,
    "chunk_id": null,
    "created_at": "2026-09-29T23:47:06.461349+00:00",
    "entity_changes": {
      "characters": [],
      "factions": [],
      "locations": [],
      "relationships": []
    },
    "entity_update_count": 0,
    "episode_transition": null,
    "orrery_adjudications": [],
    "orrery_proposal": {
      "_bleed_offer_resolution_ids": [],
      "actor_count": 2,
      "ambient_scene_seeds": [],
      "anchor_chunk_id": 4,
      "epistemics_settings": {
        "aware_roles": [
          "actor",
          "observer",
          "target",
          "witness"
        ],
        "claim_event_types": [
          "compliance_alert",
          "encoded_message",
          "hunt_called_off",
          "hunt_declared",
          "informant_contact",
          "intel_acquired",
          "intel_acted_on",
          "protective_intervention",
          "pursue_romance_completed",
          "recruit_ally_completed",
          "relationship_drift_milestone",
          "retaliation_attempted",
          "retaliation_executed",
          "rival_consulted",
          "seek_redemption_completed",
          "surveillance_performed",
          "threat_issued",
          "warning_delivered"
        ],
        "enabled": true
      },
      "generated_at": "2026-09-29T23:47:12.106670+00:00",
      "joint_beats": [],
      "rendered_cards": [
        {
          "kind": "resolution",
          "proposal_id": "upkeep:a339b89d4d913c763526bd612c4b3b2b567321e0aa43e1db0523d256f4f8bd68"
        },
        {
          "kind": "resolution",
          "proposal_id": "recreate:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8"
        }
      ],
      "resolutions": [
        {
          "binding_hash": "a339b89d4d913c763526bd612c4b3b2b567321e0aa43e1db0523d256f4f8bd68",
          "binding_names": {
            "actor": "Oren Vale",
            "place": "Fixture Docks"
          },
          "bindings": {
            "actor": 5
          },
          "branch_label": "Tidy what is theirs",
          "changed_fields": [
            "character.current_activity"
          ],
          "effective_priority": 11.0,
          "evaluated_at": "2100-01-01T04:05:00+00:00",
          "event_type": "upkeep_done",
          "magnitude": 0.08,
          "narrative_stub": "Oren Vale tends whatever corner of the world is currently theirs \u2014 folding, sorting, wiping down, the small housekeeping that keeps a life from silting up.",
          "position": 0,
          "priority": 11,
          "promotable": true,
          "proposal_id": "upkeep:a339b89d4d913c763526bd612c4b3b2b567321e0aa43e1db0523d256f4f8bd68",
          "signal_event_type": null,
          "state_delta": {
            "character.current_activity": "tidying their own space"
          },
          "template_id": "upkeep"
        },
        {
          "binding_hash": "85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
          "binding_names": {
            "actor": "Mara Quill",
            "place": "Fixture Docks"
          },
          "bindings": {
            "actor": 4
          },
          "branch_label": "Watch the world go by",
          "changed_fields": [
            "character.current_activity"
          ],
          "effective_priority": 9.0,
          "evaluated_at": "2100-01-01T04:05:00+00:00",
          "event_type": "recreation_taken",
          "magnitude": 0.1,
          "narrative_stub": "Mara Quill claims a seat with a view of other people's evenings and lets the spectacle of ordinary life be the entertainment.",
          "position": 1,
          "priority": 9,
          "promotable": true,
          "proposal_id": "recreate:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
          "signal_event_type": null,
          "state_delta": {
            "character.current_activity": "watching the world go by"
          },
          "template_id": "recreate"
        }
      ],
      "scene_conditions": {
        "time_of_day": "night",
        "weather": "clear"
      },
      "scene_pressures": []
    },
    "pacing": null,
    "parent_chunk_id": 4,
    "parent_chunk_text": "The pending fixture turn waits for the player's choice.\n\nPress on toward the lit doorway.",
    "references": {
      "characters": [
        {
          "character_id": 1,
          "character_name": "Fixture Player",
          "reference_type": "present"
        }
      ],
      "factions": [],
      "places": [
        {
          "place_id": 1,
          "place_name": "Fixture Plaza",
          "reference_type": "setting"
        }
      ]
    },
    "session_id": "d94d1054-b1b6-4b4c-91c0-ffa1d02c5074",
    "status": "provisional",
    "storyteller_text": "[TEST MODE] The scene advances under deterministic mock control. Orrery pressure is acknowledged structurally, while the prose remains simple enough for integration tests to inspect.",
    "time_delta": null,
    "user_text": "Press on toward the lit doorway.",
    "world_layer": "primary"
  },
  "ok": true
}

$ nexus inspect characters --slot 4 --json
{
  "data": [
    {
      "appearance": null,
      "background": "unknown",
      "createdAt": "2026-09-29T23:47:04.936195Z",
      "currentActivity": null,
      "currentLocation": "1",
      "currentLocationName": "Fixture Plaza",
      "emotionalState": null,
      "extraData": null,
      "id": 1,
      "name": "Fixture Player",
      "personality": null,
      "portraitPath": null,
      "summary": "Canonical player for PostgreSQL coverage.",
      "updatedAt": "2026-09-29T23:47:04.936195Z"
    },
    {
      "appearance": null,
      "background": "unknown",
      "createdAt": "2026-09-29T23:47:04.989777Z",
      "currentActivity": "tidying their own space",
      "currentLocation": "2",
      "currentLocationName": "Fixture Docks",
      "emotionalState": null,
      "extraData": null,
      "id": 2,
      "name": "Mara Quill",
      "personality": null,
      "portraitPath": null,
      "summary": "Mara Quill works the night shift at Fixture Docks.",
      "updatedAt": "2026-09-29T23:47:06.338548Z"
    },
    {
      "appearance": null,
      "background": "unknown",
      "createdAt": "2026-09-29T23:47:05.010013Z",
      "currentActivity": "watching the world go by",
      "currentLocation": "2",
      "currentLocationName": "Fixture Docks",
      "emotionalState": null,
      "extraData": null,
      "id": 3,
      "name": "Oren Vale",
      "personality": null,
      "portraitPath": null,
      "summary": "Oren Vale works the night shift at Fixture Docks.",
      "updatedAt": "2026-09-29T23:47:06.338548Z"
    }
  ],
  "ok": true
}

$ nexus inspect characters 2 --slot 4 --json
{
  "data": {
    "appearance": null,
    "background": "unknown",
    "createdAt": "2026-09-29T23:47:04.989777Z",
    "currentActivity": "tidying their own space",
    "currentLocation": "2",
    "currentLocationName": "Fixture Docks",
    "emotionalState": null,
    "extraData": null,
    "id": 2,
    "name": "Mara Quill",
    "personality": null,
    "portraitPath": null,
    "summary": "Mara Quill works the night shift at Fixture Docks.",
    "updatedAt": "2026-09-29T23:47:06.338548Z"
  },
  "ok": true
}

$ nexus inspect places --slot 4 --json
{
  "data": [
    {
      "createdAt": "2026-09-29T23:47:04.900849Z",
      "currentStatus": null,
      "extraData": null,
      "geometry": {
        "coordinates": [
          -73.9857,
          40.7484,
          0
        ],
        "type": "Point"
      },
      "history": null,
      "id": 1,
      "inhabitants": null,
      "name": "Fixture Plaza",
      "summary": "Fixture place.",
      "type": "fixed_location",
      "updatedAt": "2026-09-29T23:47:04.900849Z",
      "zone": 1
    },
    {
      "createdAt": "2026-09-29T23:47:04.958432Z",
      "currentStatus": null,
      "extraData": null,
      "geometry": {
        "coordinates": [
          -74,
          40.7,
          0
        ],
        "type": "Point"
      },
      "history": null,
      "id": 2,
      "inhabitants": null,
      "name": "Fixture Docks",
      "summary": "Fixture place.",
      "type": "fixed_location",
      "updatedAt": "2026-09-29T23:47:04.958432Z",
      "zone": 1
    }
  ],
  "ok": true
}

$ nexus inspect places 2 --slot 4 --json
{
  "data": {
    "createdAt": "2026-09-29T23:47:04.958432Z",
    "currentStatus": null,
    "extraData": null,
    "geometry": {
      "coordinates": [
        -74,
        40.7,
        0
      ],
      "type": "Point"
    },
    "history": null,
    "id": 2,
    "inhabitants": null,
    "name": "Fixture Docks",
    "summary": "Fixture place.",
    "type": "fixed_location",
    "updatedAt": "2026-09-29T23:47:04.958432Z",
    "zone": 1
  },
  "ok": true
}

$ nexus inspect factions --slot 4 --json
{
  "data": [
    {
      "createdAt": "2026-09-29T23:47:05.470143Z",
      "extraData": null,
      "id": 1,
      "name": "The Lamplighters",
      "primaryLocation": null,
      "summary": "Fixture faction.",
      "updatedAt": "2026-09-29T23:47:05.470143Z"
    }
  ],
  "ok": true
}

$ nexus inspect factions 1 --slot 4 --json
{
  "data": {
    "createdAt": "2026-09-29T23:47:05.470143Z",
    "extraData": null,
    "id": 1,
    "name": "The Lamplighters",
    "primaryLocation": null,
    "summary": "Fixture faction.",
    "updatedAt": "2026-09-29T23:47:05.470143Z"
  },
  "ok": true
}

$ nexus down
nothing running

.
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed in 17.03s
```

`nexus down` on the lane after the run:

```
$ NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017 PYTHONPATH=$PWD $PY -m nexus.cli down
nothing running
$ lsof -nP -iTCP:8017 -sTCP:LISTEN; echo $?
1
```

## Gates

`$PY` is `/Users/pythagor/nexus/.venv/bin/python`; every run is from the worktree root with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset. `PYTHONPATH=$PWD $PY -c 'import nexus;print(nexus.__file__)'` printed the worktree's `nexus/__init__.py`.

Order PostgreSQL gate:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:warnings tests/test_cli_contract.py tests/test_cli.py tests/test_cli_inspect_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
161 passed in 78.39s (0:01:18)
```

Reachability and every other CLI, `continue`, and `regenerate` test (PostgreSQL enabled, no skips):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:warnings tests/test_reachability.py \
    tests/test_cli_session_wait.py tests/test_cli_generation_http.py tests/test_cli_choice_http.py \
    tests/test_cli_wizard_confirmation.py tests/test_cli_model_selection.py tests/test_new_story_cli.py \
    tests/test_record_revelation_cli_pg.py tests/test_jobs_cli_pg.py tests/test_api/test_acceptance_staging_pg.py \
    tests/test_api/test_seat_policy_jobs_pg.py tests/test_api/test_attempt_manifest_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
174 passed in 165.25s (0:02:45)
```

Offline `pytest -q`, split to stay under the ten-minute command limit (the four parts cover `tests/`; part A is the first 57 top-level files plus a second run of `tests/test_cli_session_wait.py`):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:warnings <tests/test_*.py, files 1-57> tests/test_cli_session_wait.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory[False]
FAILED tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory[True]
2 failed, 805 passed, 98 skipped in 215.82s (0:03:35)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:warnings <tests/test_*.py, files 58-105>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
807 passed, 179 skipped in 52.01s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:warnings tests/config tests/proofs tests/test_api tests/test_config tests/test_ir_eval_v2 tests/test_runtime tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
964 passed, 254 skipped in 40.95s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:warnings tests/test_lore tests/test_memnon tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1628 passed, 543 skipped in 30.51s
```

The two `test_postgres_installer_helper_from_foreign_directory` failures are this worktree's environment, not the change. The test runs `python -c 'from nexus.config import load_settings ...'` from a foreign directory without `PYTHONPATH`, so the child imports the shared venv's editable install, which points at the main checkout (`File "/Users/pythagor/nexus/nexus/database.py"` in the failure). That checkout's `RuntimeCliSettings` has no `poll_interval_seconds`, so it rejects the worktree's `nexus.toml` (`runtime.cli.poll_interval_seconds  Extra inputs are not permitted`). With the worktree's code on the path the same test passes:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings "tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory"
..                                                                       [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2 passed in 1.76s
```

Formatting, lint, and types on the changed Python files:

```
$ $PY -m black --check nexus/cli.py nexus/cli_contract.py nexus/config/settings_models.py tests/test_cli_contract.py tests/test_cli_session_wait.py tests/test_cli_inspect_pg.py
6 files would be left unchanged.
$ $PY -m flake8 nexus/cli_contract.py tests/test_cli_contract.py tests/test_cli_session_wait.py tests/test_cli_inspect_pg.py; echo $?
0
$ $PY -m mypy nexus/cli.py nexus/cli_contract.py tests/test_cli_contract.py tests/test_cli_session_wait.py tests/test_cli_inspect_pg.py
Success: no issues found in 5 source files
```

`flake8 nexus/cli.py` reports 9 E501 lines and `flake8 nexus/config/settings_models.py` 6, the same counts as `origin/main` (all in lines this change does not touch). `mypy nexus/config/settings_models.py` reports the same 7 `[operator]` errors at `origin/main` (lines 130, 131, 138, and the local-window check).

## Deferred on #815

The global `{ok, data}` envelope for the remaining commands, the review verbs bound to the incubator lifecycle, operator gating and redaction of spoiler-bearing inspect fields (the incubator draft is served as the player-plane route serves it), inspect verbs for interactions, queues, settings, and secrets status (no player-plane read routes yet; they wait on the operator-plane ruling), and removing the legacy handlers' broad `except Exception`.
