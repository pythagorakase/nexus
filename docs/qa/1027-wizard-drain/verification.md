# Issue #1027 Verification: A Wizard-Phase Slot Has No Experience Work

Live proof on lane 8019 with the TEST provider only (`NEXUS_TEST_PROVIDER_ONLY=1`,
env-only secrets). No paid call was made; token usage: 0.

## Setup

- Scheduler interval, read from `nexus.toml:1354` through `load_settings_as_dict()`:
  `[runtime.scheduler] poll_interval_seconds = 5.0`.
- Clone: `disposable_slot_database("qa640_1027_live")` (a fresh `NEXUS_template`
  clone), staged with the golden path's own `stage_reset_slot` (the canned,
  confirmed wizard cache) after `route_slot_to_disposable(setattr, slot=4, ...)`.
- State before boot, read from the clone:
  `clone=qa640_1027_live_74225c798814 user_character=None experience_jobs=0`.
- Lane check before boot: `lsof -nP -iTCP:8019 -sTCP:LISTEN` returned 1 (free).

## Boot Command

The gateway was launched by `tests.test_golden_path_live.launch_routed_gateway`
(`store_access=False`), the same entry point PR #1026's golden-path fixture uses:

```
NEXUS_SLOT=4 NARRATIVE_API_PORT=8019 NEXUS_GATEWAY_PORT=8019 NEXUS_API_URL=http://127.0.0.1:8019 NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_KEYRING_DISABLE=1 NEXUS_ROUTED_SLOT=4 NEXUS_ROUTED_SLOT_DATABASE=qa640_1027_live_74225c798814 /Users/pythagor/nexus/.venv/bin/python -m tests.slot_routed_gateway
```

`NEXUS_SLOT=4` names the routed slot, so the gateway's `SlotScheduler` owns the
wizard-phase clone's deferred work.

## Pass Count

The run waited 30.0 s after `/health` answered. The idle scheduler pass logs
nothing, so passes were counted from `pg_stat_user_tables` reads of
`character_experience_jobs` on the clone (the drain's due-work probe runs once
per idle pass), calibrated by one in-process `SlotScheduler(4, dbname=...).run_pass()`
on the same clone after the gateway stopped:

```
calibration pass result: {'owner': True, 'drained': True, 'promotion': (0, 0), 'orrery_narration_jobs': [0, 0], 'character_experience_jobs': [0, 0], 'orrery_maturation_jobs': [0, 0], 'relationship_milestone_queue': 0, 'narrative_summary_jobs': 0, 'narrative_embedding_jobs': 0, 'character_experience_embeddings': 0}
waited 30.0s after /health
character_experience_jobs scans during gateway run: 12; per idle pass: 2; gateway scheduler passes: 6
```

Six scheduler passes ran on the wizard-phase clone.

## Log Grep

```
$ grep -n "ERROR\|Traceback" gateway_1027_fixed.log
$ echo $?
1
```

The grep printed nothing. The whole gateway log (10 lines):

```
WARNING UI build not found at /Users/pythagor/nexus/.claude/worktrees/1027-wizard-drain/ui/dist/public - the gateway will serve APIs only. Run `npm --prefix ui run build` (or use the Vite dev server).
2026-09-29 21:21:27,993 - uvicorn.error - INFO - Started server process [26665]
2026-09-29 21:21:27,993 - uvicorn.error - INFO - Waiting for application startup.
2026-09-29 21:21:28,087 - nexus.api.db_pool - INFO - Created connection pool for database: qa640_1027_live_74225c798814
2026-09-29 21:21:28,167 - uvicorn.error - INFO - Application startup complete.
2026-09-29 21:21:28,170 - uvicorn.error - INFO - Uvicorn running on http://127.0.0.1:8019 (Press CTRL+C to quit)
2026-09-29 21:21:59,178 - uvicorn.error - INFO - Shutting down
2026-09-29 21:21:59,278 - uvicorn.error - INFO - Waiting for application shutdown.
2026-09-29 21:21:59,341 - uvicorn.error - INFO - Application shutdown complete.
2026-09-29 21:21:59,341 - uvicorn.error - INFO - Finished server process [26665]
```

(`uvicorn.error` is uvicorn's own logger name; those lines are INFO.)

## Contrast Without the Fix

The same script with the `experiences.py` change reverted (clone
`qa640_1027_live_59216565bf6c`, same boot and wait) logged the defect:

```
7:2026-09-29 21:22:17,029 - nexus.jobs.scheduler - ERROR - Deferred-work owner recovering for qa640_1027_live_59216565bf6c: Cannot resolve canonical player identity: user_character is NULL
```

followed by a traceback (`grep -c Traceback` = 1).

## Teardown

Both clones were dropped by the fixture (`SELECT datname FROM pg_database WHERE
datname LIKE 'qa640_1027%'` returned no rows). Lane 8019 was free afterwards, and
`NEXUS_GATEWAY_PORT=8019 NEXUS_API_URL=http://127.0.0.1:8019 python -m nexus.cli down`
printed `nothing running`.
