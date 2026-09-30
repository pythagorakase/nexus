# Mock Provider Direct-Launch Logging Verification (#842, Order 842-S4)

## Scope

Only the direct launch of the mock provider (`python -m nexus.api.mock_openai`) changes. The supervised launch, `nexus.toml`, and the in-process `uvicorn.run` launches in `scripts/qa_shift/card_identity_probe.py` and `scripts/qa_shift/long_absence_probe.py` (PR #1046 edits those) are untouched. No migration, no paid call, no database write. The owner's mock provider on 5102 and gateway on 8002 were never bound, stopped, or restarted.

## Behavior Before This Change

`nexus/api/mock_openai.py` on `origin/main` (`172bd0e2`) ended with:

```python
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5102)
```

No `log_config`, so a direct launch used uvicorn's default format and ignored `[runtime.logs]`; the host bound every interface. The gateway's direct launch (`nexus/api/narrative.py:1743-1764`) already loads the typed settings, raises when `[runtime]` is absent, binds `127.0.0.1`, and passes `log_config=build_logging_config(_runtime.logs)`.

## Change

`direct_launch_config(settings=None)` in `nexus/api/mock_openai.py` returns the `uvicorn.run` keyword arguments, and the `__main__` block calls `uvicorn.run(app, **direct_launch_config())`:

- `log_config` is `build_logging_config(settings.runtime.logs)`, the same dictConfig the supervisor writes to `<state_dir>/logging.json` and hands the service through `--log-config`.
- `[runtime]` absent raises `RuntimeError("nexus.toml has no [runtime] section for [runtime.logs]")`, the gateway block's wording. No fallback to uvicorn's defaults.
- `host` is the literal `127.0.0.1` (#415/#458).
- `port` is `settings.runtime.services["mock_openai"].port`. The typed settings expose it (`RuntimeServiceSettings.port`, `nexus/config/settings_models.py:520`), so the literal 5102 is gone; `[runtime.services.mock_openai]` absent raises a `RuntimeError` naming that section. No new tunable was added.

How the supervised command names host and port (`nexus.toml:1437-1442`):

```toml
[runtime.services.mock_openai]
command = ["{python}", "-m", "uvicorn", "nexus.api.mock_openai:app", "--host", "{host}", "--port", "{port}", "--log-config", "{log_config}"]
host = "127.0.0.1"
port = 5102  # must match [global.model.api_models.test] base_url (validated)
```

The supervisor substitutes `{host}` and `{port}` from that entry, so both launches now take the port from the same key. The direct launch keeps its host a loopback literal rather than reading `host`, as the order requires.

## Tests Added (`tests/test_runtime/test_logging_config.py`, Offline)

- `test_mock_openai_direct_launch_uses_the_shared_log_config`: keys are exactly `host`, `port`, `log_config`; `log_config == build_logging_config(load_settings().runtime.logs)`; host `127.0.0.1`; port equals the service entry's.
- `test_mock_openai_direct_launch_requires_the_runtime_section`: `settings_with({"runtime": None, "local_models.model": None})` raises and the message names `[runtime]`. The local model is cleared because `Settings` rejects a configured local model with no `[runtime.services.llama_server]` serving window.
- `test_mock_openai_direct_launch_requires_the_mock_service_entry`: the repository settings without `[runtime.services.mock_openai]` raise and name that section.
- `test_importing_mock_openai_binds_no_port_and_configures_no_logging`: a fresh interpreter imports `nexus.api.mock_openai` and reports no new socket file descriptor (checked through `/dev/fd` with `S_ISSOCK`) and no handler on root, `nexus.api.mock_openai`, `uvicorn`, or `uvicorn.access`.

## Manual Direct Launch

Script: session scratchpad `842-S4/direct_launch.py`. It copies the worktree's `nexus.toml` with `[runtime.services.mock_openai].port` and the TEST provider `base_url` both moved to 5187 (they are validated to match), points `NEXUS_RUNTIME_CONFIG` at the copy, and runs the real `python -m nexus.api.mock_openai`. No code change was needed to move the port: the helper reads it from the settings.

```text
before launch: (no listener on 5187)
GET /health -> 200
GET /no-such-route -> 404
POST /v1/chat/completions {} -> 422
while running: COMMAND     PID     USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
python3.1 61467 pythagor    6u  IPv4 0xe556a97cfade211d      0t0  TCP 127.0.0.1:5187 (LISTEN)
exit code: -15
after stop: (no listener on 5187)
---- server output ----
2026-09-30 11:39:44,262 - uvicorn.error - INFO - Started server process [61467]
2026-09-30 11:39:44,262 - uvicorn.error - INFO - Waiting for application startup.
2026-09-30 11:39:44,262 - uvicorn.error - INFO - Application startup complete.
2026-09-30 11:39:44,263 - uvicorn.error - INFO - Uvicorn running on http://127.0.0.1:5187 (Press CTRL+C to quit)
2026-09-30 11:39:44,519 - uvicorn.access - INFO - 127.0.0.1:52988 - "GET /no-such-route HTTP/1.1" 404
2026-09-30 11:39:44,520 - uvicorn.access - INFO - 127.0.0.1:52989 - "POST /v1/chat/completions HTTP/1.1" 422
2026-09-30 11:39:44,666 - uvicorn.error - INFO - Shutting down
2026-09-30 11:39:44,768 - uvicorn.error - INFO - Waiting for application shutdown.
2026-09-30 11:39:44,768 - uvicorn.error - INFO - Application shutdown complete.
2026-09-30 11:39:44,768 - uvicorn.error - INFO - Finished server process [61467]
```

Every line uses the `[runtime.logs].format` (`%(asctime)s - %(name)s - %(levelname)s - %(message)s`). The successful `GET /health` is absent, as `access_success_exclude_paths` requires; the 404 and 422 remain. The listener is on `127.0.0.1:5187` only, and the port is free after the stop.

## Gates

Import check:

```text
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/842-mock-openai-logging/nexus/__init__.py
```

All runs below used the shared interpreter from the worktree root with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT` unset.

```text
$ python -m pytest -q tests/test_runtime/test_logging_config.py tests/test_mock_openai.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
68 passed, 2 skipped, 5 warnings in 4.38s
```

The two skips are the PostgreSQL tests in `tests/test_mock_openai.py` (lines 332 and 352); run with PostgreSQL:

```text
$ NEXUS_RUN_POSTGRES=1 python -m pytest -q -p tests.dbname_audit tests/test_mock_openai.py
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
16 passed in 0.44s
```

```text
$ python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2612 passed, 391 skipped, 8 warnings in 402.22s (0:06:42)

$ python -m pytest -q tests/test_api tests/test_orrery -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1811 passed, 742 skipped, 7 warnings in 37.78s

$ python -m pytest -q tests/test_reachability.py -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.42s
```

Skips in the offline runs are the PostgreSQL and live suites, which need `NEXUS_RUN_POSTGRES=1` or `NEXUS_RUN_LIVE_LLM=1`.

```text
$ python -m black --check nexus/api/mock_openai.py tests/test_runtime/test_logging_config.py
All done! ✨ 🍰 ✨
2 files would be left unchanged.

$ python -m flake8 nexus/api/mock_openai.py tests/test_runtime/test_logging_config.py
nexus/api/mock_openai.py:1146:89: E501 line too long (132 > 88 characters)
nexus/api/mock_openai.py:1161:89: E501 line too long (103 > 88 characters)
nexus/api/mock_openai.py:1171:89: E501 line too long (117 > 88 characters)

$ python -m mypy nexus/api/mock_openai.py tests/test_runtime/test_logging_config.py
nexus/api/mock_openai.py:1139: error: Item "None" of "APISettings | None" has no attribute "test_provider"  [union-attr]
nexus/api/mock_openai.py:1151: error: Item "None" of "APISettings | None" has no attribute "test_provider"  [union-attr]
Found 2 errors in 1 file (checked 2 source files)
```

The flake8 and mypy findings are in code this change does not touch. flake8 on the `origin/main` copy of the file reports the same three lines. The mypy lines sit above the new function, which is appended at the end of the file. They are left for the coordinator.

## Review Fix: Module Usage Docstring (Commit a7ff0870)

The module docstring's Usage line named `poetry run uvicorn nexus.api.mock_openai:app --port 5102`, a launch without `--log-config` that ignores `[runtime.logs]`. It now names `python -m nexus.api.mock_openai` (loopback, port from `[runtime.services.mock_openai]`, dictConfig from `[runtime.logs]`) and `nexus up` for the supervised launch. Docstring only; no code path changed.

Tails on a7ff0870:

```
$ python -m pytest -q tests/test_runtime/test_logging_config.py tests/test_mock_openai.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
68 passed, 2 skipped, 5 warnings in 3.98s

$ python -m black --check nexus/api/mock_openai.py
All done! ✨ 🍰 ✨
1 file would be left unchanged.
```

flake8 on the file reports the same three pre-existing E501 lines as `origin/main` (now at 1151, 1166 and 1176 after the five added docstring lines).

## Coordinator Note

Only the direct launch changes, so no restart of the owner's mock provider or gateway is owed.
