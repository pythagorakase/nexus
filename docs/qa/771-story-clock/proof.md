# Story Clock Proof — Issue 771

Owner Decision 8, Option A (#857). Implementation: `55c85fe0`.

## Browser Evidence

Chrome at `http://127.0.0.1:8015/nexus`, slot 4. The pending draft was present; Previous scene opened the latest accepted chunk (49 / S01E02_045). Both the top bar and its intertitle show `17 Oct 2189 · 22:37`. See [screenshot](frontier-clock.png) and [route payloads](clock-evidence.json). The ISO strings have different offsets but identify the same instant.

Gateway ran with `PGOPTIONS='-c default_transaction_read_only=on'`. Startup used locked slot 1 (verified locked), then the browser selected slot 4. No story writes or provider calls. Slot routing has no database override, so this used the authorized live read-only view.

The first startup rolled back because an unmanaged mock service occupied 5102. A local proof-only copy of nexus.toml set runtime.services.mock_openai.enabled to never; tracked nexus.toml is unchanged.

```sh
# PROOF_TOML: a scratch copy of nexus.toml whose only change is the TEST-provider
# service set to enabled = "auto" (the repository keeps it "never").
PYTHONPATH=$PWD PGOPTIONS='-c default_transaction_read_only=on' NEXUS_GATEWAY_PORT=8015 NEXUS_API_URL=http://127.0.0.1:8015 $PY -m nexus.cli up --slot 1 --config "$PROOF_TOML"
```

started gateway (pid 51065) on http://127.0.0.1:8015
NEXUS is up: http://127.0.0.1:8015 (slot 1, profile local)

## Validation

`PY=/Users/pythagor/nexus/.venv/bin/python`. Import identity was verified under this worktree. Node dependencies were already installed locally by the preceding run (`npm --prefix ui ci`, recorded in npm-ci.log); no symlink or poetry install.

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2581 passed, 758 skipped, 11 warnings in 90.60s (0:01:30)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_frontier_clock_pg.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 5 warnings in 1.01s
```

```sh
npm --prefix ui run check
```

```text

> nexus-ui@1.0.0 check
> tsc

```

```sh
npm --prefix ui test
```

```text

 Test Files  22 passed (22)
      Tests  238 passed (238)
   Start at  18:10:56
   Duration  2.22s (transform 1.91s, setup 1.20s, collect 6.52s, tests 2.90s, environment 9.04s, prepare 1.45s)

```

```sh
npm --prefix ui run build
```

```text
✓ built in 2.65s

PWA v1.0.3
mode      generateSW
precache  22 entries (2273.64 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

## Pre-existing on Base, Repaired Under a Separate Order

The coordinator completed classification; the retained base-four.log confirms all four failures:

FAILED tests/test_api/test_backstage_endpoints_pg.py::test_payload_assembles_every_committed_stream
FAILED tests/test_api/test_narrative_continue_validation.py::test_concurrent_continues_have_one_owner_and_truthful_result
FAILED tests/test_api/test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit
FAILED tests/test_api/test_orrery_config_reuse_pg.py::test_sync_commit_loads_application_config_once

The full PostgreSQL gate was not rerun, per the third amendment. The earlier interrupted full run is not claimed as a pass. Slot-5-dependent Orrery failures remain exempt under #885. Offline skips are expected; the dedicated PostgreSQL route test actually ran.

## Shutdown

```sh
PYTHONPATH=$PWD NEXUS_GATEWAY_PORT=8015 NEXUS_API_URL=http://127.0.0.1:8015 $PY -m nexus.cli down --config "$PROOF_TOML"
```

```text
stopped gateway (pid 51065)
```

`lsof -nP -iTCP:8015 -sTCP:LISTEN` returned no listener.

Historical-scene following is deferred to C029 (#768). No schema, formatter, intertitle, or tracked configuration changes. No open coordinator questions.

Codex — GPT-6 Astra
