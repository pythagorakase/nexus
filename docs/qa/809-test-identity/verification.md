# 809-S2 Verification: TEST Identity by Registry Provider

Work order 809-S2 (issue #809). Base `origin/main` at `41783c1d`. Line numbers
in "What Was Wrong" are at that base; the cited files did not change between
`d4a1756a` (the coordinator's read) and `41783c1d`.

## What Was Wrong

- Three branches compared the literal model id `"TEST"`:
  - `nexus/api/wizard_chat.py:728` (`new_story_chat_endpoint`) and `:1125`
    (`new_story_chat_stream_endpoint`): `if selected_model == "TEST":`.
  - `nexus/api/new_story_flow.py:40` defined `MOCK_WIZARD_MODEL = "TEST"`;
    `perform_transition_with_retrograde` compared against it at `:542`
    (`effective_model != MOCK_WIZARD_MODEL`, trait-input derivation) and `:567`
    (`elif effective_model == MOCK_WIZARD_MODEL:`, the `"mock_wizard_model"`
    skip reason).
- The id is configuration: the TEST model is one entry of
  `[global.model.api_models.test]` (`nexus.toml:44-49`, id at `:48`). A rename
  is a valid configuration: `tests/config/test_settings_models.py:750-780`
  (`test_default_load_honors_runtime_config_env`) loads `TEMPTEST`, renamed at
  `:756-757`.
- Provider identity already existed: `Settings.provider_for_model`
  (`nexus/config/settings_models.py:4508-4517`) returns the registry provider
  and raises `ValueError` for an unregistered id. Provider-name branches:
  `nexus/config/provider_guard.py:18-19` (`provider = settings.provider_for_model(model)`;
  `if provider != "test":`), `nexus/api/conversations.py:38`
  (`MEMORY_CONVERSATIONS_PROVIDER = "test"`) and `:110`
  (`provider = settings.provider_for_model(model)`), and
  `nexus/config/settings_models.py:235` (`if provider == "test":`).
- The setup script kept a dead graceful fallback: `_get_default_slot_model`
  (`scripts/new_story_setup.py:91-100`) caught every exception from
  `load_settings()` and returned `"TEST"`. Every caller connects next:
  `ensure_global_variables` (`:103-118`) opens `_connect(dbname)` at `:106`;
  `_connect` (`:43-65`) goes through `db_pool.get_connection`, which calls
  `load_settings()` at `nexus/api/db_pool.py:156`, or `connection_kwargs`, which
  calls it at `nexus/database.py:152`. Both slot paths (`:269` initialization,
  `:492` post-clone cleanup) call `subprocess_env()` earlier for `createdb` and
  `pg_dump` (for example `:214`, `:221`, `:450`), and `subprocess_env`
  (`nexus/database.py:366-368`) calls `connection_kwargs("postgres")`.
- Probe (offline, this run; `scratchpad/809-S2/probe.py`): under a copy of the
  active configuration with `default_slot_model = "NO_SUCH_MODEL"`:

  ```
  old _get_default_slot_model() -> 'TEST'
  connection_kwargs('qa640_probe') raised pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings | global.model | Value error, default_slot_model references unknown model id 'NO_SUCH_MODEL'. Known IDs: [...]
  new _get_default_slot_model() raised pydantic_core._pydantic_core.ValidationError
  ```

## Docstring Clauses and Their Evidence

The new module docstring of `nexus/api/wizard_test_cache.py`:

| Clause | Evidence |
| --- | --- |
| Loads and parses `tests/fixtures/test_cache_wizard.json` | `CACHE_FILE` (`nexus/api/wizard_test_cache.py:19-24` after the change; `:22-27` at base) is `tests/fixtures/test_cache_wizard.json`; `load_cache` reads it and `json.loads` each string field that starts with `{`. |
| whose object fields are stored as JSON-encoded strings | In the fixture, `setting_draft`, `character_draft`, `selected_seed`, `initial_location`, `layer_draft` and `zone_draft` are strings holding JSON objects; `id`, `target_slot`, `thread_id`, `base_timestamp` and `updated_at` are plain values (checked by loading the file). |
| Tests stage wizard transition data from `load_cache` | The only importers of the module: `tests/test_live_gate_clones_pg.py:278`, `tests/test_orrery/test_retrograde_wizard_live.py:84` and `:228` (`git grep -n wizard_test_cache -- nexus tests scripts`). |
| The mock provider does not import this module; it has its own cached phase responses | `nexus/api/mock_openai.py` has no import of `wizard_test_cache` (its imports: `:21`, `:23-37`); it defines its own `get_cached_phase_response` at `:301`. |

The old docstring's claims were false: it named `temp/test_cache_wizard.json`
"pre-parsed by user", and said the player selects "TEST" in the UI model
picker, but the TEST provider is hidden from UI pickers (`nexus.toml:45`,
`ui_visible = false`).

## Plants (Each New Test Fails on the Old Code)

Plants were applied by `scratchpad/809-S2/plant.py` to the committed tree and
reverted with `git checkout -- nexus scripts` after each run (`git status`
clean after every revert).

### Combined Plant: The Old Code Restored

Diff of the plant (the literal comparisons, `MOCK_WIZARD_MODEL`, and the
fallback):

```
+MOCK_WIZARD_MODEL = "TEST"
-        not settings.is_test_model(effective_model)
+        effective_model != MOCK_WIZARD_MODEL
-    elif settings.is_test_model(effective_model):
+    elif effective_model == MOCK_WIZARD_MODEL:
-                    if load_settings().is_test_model(selected_model):
+                    if selected_model == "TEST":
-                        if load_settings().is_test_model(selected_model):
+                        if selected_model == "TEST":
-    from nexus.config.loader import load_settings
+    try:
+        from nexus.config.loader import load_settings
-    return load_settings().global_.model.default_slot_model
+        settings = load_settings()
+        return settings.global_.model.default_slot_model
+    except Exception:
+        # Fallback if config not available
+        return "TEST"
```

Offline tails:

```
E       AssertionError: assert ['nexus/api/w...chat.py:1126'] == []
E         Left contains 2 more items, first extra item: 'nexus/api/wizard_chat.py:729'
E         + [
E         +     'nexus/api/wizard_chat.py:729',
E         +     'nexus/api/wizard_chat.py:1126',
E         + ]
E       Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>
FAILED tests/config/test_settings_models.py::test_no_product_code_compares_the_literal_test_id
FAILED tests/test_new_story_setup_config.py::test_default_slot_model_raises_when_the_configuration_is_invalid
=================== 2 failed, 1 passed, 5 warnings in 1.31s ====================
```

PostgreSQL tail:

```
E                   httpcore.ConnectError: [Errno 61] Connection refused
E           httpx.ConnectError: [Errno 61] Connection refused
E               openai.APIConnectionError: Connection error.
dbname audit: owner targets: none
FAILED tests/test_api/test_mock_wizard_responses.py::test_renamed_test_provider_model_skips_derivation_and_retrograde
1 failed, 5 warnings in 3.53s
```

### Single Plants: Which Test Catches Which

| Plant | Caught by |
| --- | --- |
| Fallback restored in `_get_default_slot_model` | `test_default_slot_model_raises_when_the_configuration_is_invalid` (`Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>`) |
| `:542` restored (`effective_model != MOCK_WIZARD_MODEL`, constant restored) | the transition test; refused connection raised from `nexus/api/new_story_flow.py:553` → `nexus/api/trait_input_derivation.py:367` (the deriver ran against `TEMPTEST`) |
| `:567` restored (`elif effective_model == MOCK_WIZARD_MODEL:`, constant restored) | the transition test; refused connection raised from `nexus/api/new_story_flow.py:602` → `nexus/agents/orrery/retrograde_orchestrator.py:216` → `retrograde_seed_candidates.py:1576` (Retrograde ran against `TEMPTEST`) |
| `:542` as an inline literal (`effective_model != "TEST"`) | the transition test and the AST test (`nexus/api/new_story_flow.py:538`) |
| `:567` as an inline literal (`elif effective_model == "TEST":`) | the transition test and the AST test (`nexus/api/new_story_flow.py:563`) |
| Both wizard chat branches (`selected_model == "TEST"`) | the AST test (`nexus/api/wizard_chat.py:729`, `:1126`) |
| `is_test_model` compares the literal id (`return model_id == "TEST"`) | `test_test_identity_follows_the_provider_not_the_id` (`assert False is True` where `False = is_test_model('TEMPTEST')`) and the AST test (`nexus/config/settings_models.py:4526`) |

The AST test catches every inline comparison with `"TEST"`. A comparison
against a restored module constant (`MOCK_WIZARD_MODEL`) compares a name, not
a constant, so only the transition test catches that form.

## Gates

PostgreSQL proof (`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_new_story_setup.py tests/test_api/test_mock_wizard_responses.py tests/test_api/test_wizard_model_switch.py tests/test_live_gate_clones_pg.py tests/test_connection_lifecycle.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 21 targets: mock, nexus_m10_fresh_test_28862, nexus_m10_template_test_28862, nexus_test_issue_613_*, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_offline_gate_*, qa640_renamed_test_model_*, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:55949 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:55958 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:55949 (psycopg2), save_04@local:55958 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
208 passed, 7 warnings in 62.79s (0:01:02)
```

Named offline files:

```
$ PYTHONPATH=$PWD $PY -m pytest -q tests/config/test_settings_models.py tests/test_new_story_setup_config.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_wizard_confirmation.py tests/test_wizard_agent.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
206 passed, 5 warnings in 4.33s
```

Offline suites:

```
$ PYTHONPATH=$PWD $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2628 passed, 419 skipped, 8 warnings in 416.93s (0:06:56)

$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1816 passed, 743 skipped, 7 warnings in 38.24s

$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 9.99s
```

The offline skips are the `requires_postgres` tests (no `NEXUS_RUN_POSTGRES`).

Black, flake8 and mypy on the ten changed Python files:

```
black --check: 10 files would be left unchanged.
flake8 (violations, base -> branch):
  nexus/config/settings_models.py 6 -> 6
  nexus/api/wizard_chat.py 18 -> 20   (the two new E501 lines are the order's
                                       verbatim comment at :728 and :1125)
  nexus/api/new_story_flow.py 4 -> 4
  scripts/new_story_setup.py 7 -> 7
  every other changed file 0 -> 0
mypy --explicit-package-bases --follow-imports=silent --ignore-missing-imports, per file:
  nexus/config/settings_models.py: 7 errors, lines 130 131 138 4382 (none on a changed line)
  nexus/api/wizard_chat.py: 33 errors (none on a changed line: 80, 728-729, 1125-1126)
  nexus/api/new_story_flow.py: 1 error, line 738 (unchanged)
  the other seven files: no issues
```
