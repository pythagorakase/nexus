# Issue 809: Typed Settings Readers Verification

Branch `claude/809-typed-settings-readers`, cut from `588fc543` on
2026-09-29. No `save_NN` or `NEXUS_template` was written by this branch's
code; the pre-existing `test_retrieval_coverage_live` (#885) opens a
rolled-back transaction on live `save_05` as part of the ordered gate (its id
sequences advance). No paid provider call was made.

## Ownership Table

`tests/config/test_settings_parity.py` declares the typed owner of every leaf
the legacy façade (`load_settings_as_dict()`) exposes under its two alias
blocks, and proves the effective values agree with `load_settings()`.

| Façade root | Typed owner | Leaves owned |
|---|---|---|
| `Agent Settings.global` | `global_` | 4 |
| `Agent Settings.LORE` | `lore` | 26 |
| `Agent Settings.MEMNON` | `memnon` | 69 |
| `API Settings.apex` | `apex` | 20 |
| **Total** | | **119** |

Nine open-keyed registries are allowlisted in `DYNAMIC_REGISTRIES` and
compared as whole sub-trees, type-strictly (a bool/int or int/float change
inside a registry fails, as it does for a leaf): the provider registry
(`global_.model.api_models`), the two provider-override tables
(`lore.token_budget.provider_overrides`,
`lore.entity_inclusion.provider_overrides`), the embedding registry
(`memnon.models`), the reranker candidates, and four query-type weight maps.

The walk fails on a façade leaf with no owner, an owner path that does not
exist on `Settings` (it caught `memnon.import` versus the field `import_`), an
owner outside its root, an owner that is not its façade path mapped through
each model's field aliases (`OWNER_PATH_EXCEPTIONS` is empty), or a value
drift. A planted drift, a planted unowned leaf, and a planted Writer-to-Gaia
owner swap (`apex.max_output_tokens` pointed at `apex.gaia.max_output_tokens`,
which holds the same value) are all named, so the walk is not vacuous.

## Assembled-Request Fingerprint

`tests/test_lore/test_assembled_prompt_fingerprint.py` builds one fixed
two-pass turn on the TEST route with a recording client. The route comes from
`LogonUtility._resolve_storyteller_route()`. The settings come from
`settings_with()` with distinct Gaia values (`apex.gaia.max_output_tokens`
23000, reserves 19000/3500, `reasoning_effort` `high`; the Writer keeps
25000, 21000/4000, `medium`), so a seat swap is visible. The test records the
SHA-256 of the exact `responses.create` kwargs for the Writer and Gaia seats;
the per-seat request knobs (`max_output_tokens`, `reasoning_effort`,
`temperature`) of the writer provider after `_initialize_provider` and of each
pass provider after `_clone_provider_for_two_pass`; and the budget lines
(payload budget, per-provider context windows and entity inclusion,
deep-query budget, presence-boost flag, Pass-2 config fingerprint, and both
seats' resolved windows).

The values were recorded from an export of the parity commit `688cb431`,
where every reader still used the alias dict, by running the same fixture
with the overrides delivered as the legacy dict. They pass unchanged at the
head. Planting `self.settings.apex.max_output_tokens` in place of the Gaia
clone's `gaia.max_output_tokens` fails the request test.

## Temperature and Dead Readers

The storyteller sampling temperature is now typed configuration:
`apex.temperature` and `apex.gaia.temperature` (both `0.7` in `nexus.toml`,
the value the old unreachable `apex.get("temperature", 0.7)` fallback sent).
The Writer and the pinned Gaia provider read them, and the slot-following
Gaia clone takes `apex.gaia.temperature` alongside its output allowance and
effort. `correspondence_settings()` and
`TokenBudgetManager.validate_budget_constraints()` (with its `allocation_config`
dict mirror) had no production caller and are deleted.

## Grep Proof

`grep -rn "\"API Settings\"\|\"Agent Settings\"" nexus/ --include='*.py'` at
the head returns only the façade builder and the legacy JSON loader in
`nexus/config/loader.py`, the two remaining serialization filters, and the
`GET /api/settings` payload builder. The third filter
(`logon_utility.py:1722`) is gone because LOGON now holds the typed
`Settings` itself.

```
nexus/config/story_model.py:271:                if k not in {"Agent Settings", "API Settings"}
nexus/config/loader.py:320:    # Legacy has "Agent Settings" with nested agents, we want flat structure
nexus/config/loader.py:321:    legacy_agent_settings = data.get("Agent Settings", {})
nexus/config/loader.py:331:    legacy_new_story = data.get("API Settings", {}).get("new_story", {})
nexus/config/loader.py:338:        "apex": data.get("API Settings", {}).get("apex", {}),
nexus/config/loader.py:381:    # Preserve legacy structure for callers expecting "Agent Settings" and "API Settings"
nexus/config/loader.py:391:        "Agent Settings": legacy_agent_settings,
nexus/config/loader.py:392:        "API Settings": legacy_api_settings,
nexus/agents/orrery/retrograde_maturation.py:596:            if key not in {"Agent Settings", "API Settings"}
nexus/api/settings_endpoints.py:101:    payload["Agent Settings"] = {
nexus/api/settings_endpoints.py:106:    payload["API Settings"] = {"apex": raw.get("apex", {})}
```

## Gate Tails

Parity and fingerprint at the head, plus the correspondence and seat-policy
tests the review fixes touched:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
92 passed, 5 warnings in 3.63s
```

`NEXUS_RUN_POSTGRES=1 python -m pytest -q tests/test_lore` (then
`tests/config`, `tests/test_config`, `tests/test_memnon`), with
`NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset. `tests/test_lore`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_lore/test_pass2_chunk1369.py::test_pass2_handles_karaoke_divergence
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
2 failed, 452 passed, 1 skipped, 9 warnings in 114.18s (0:01:54)
```

`tests/config`, `tests/test_config`, `tests/test_memnon`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
111 passed, 5 warnings in 3.29s
secret-store guard: active; nexus-api: denied; disposable keychain: denied
82 passed, 5 warnings in 3.84s
secret-store guard: active; nexus-api: denied; disposable keychain: denied
51 passed, 5 warnings in 28.00s
```

Both lore failures reproduce unchanged on an export of `588fc543`:
`test_retrieval_coverage_live` hardwires the owner's empty slot 5 (#885,
exempt: `need-clock anchor unavailable: no canonical world time or
base_timestamp`), and `test_pass2_chunk1369` patches `get_recent_chunks`
with a lambda that rejects the `through_chunk_id` keyword the turn cycle
already passed at the base (`FATAL: No warm slice chunks retrieved`).
`test_pass2_chunk1369` is not a #885 exemption: it is a pre-existing failure
left for the coordinator's triage.

Offline suite, `PYTHONPATH=$PWD python -m pytest -q` (the worktree must be
on `PYTHONPATH`: `test_postgres_installer_helper_from_foreign_directory` runs
a subprocess from another directory, and without it that subprocess imports
the main checkout's `nexus`, whose models reject the new temperature keys):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
4112 passed, 1043 skipped in 282.43s (0:04:42)
```

`python -m pytest -q tests/test_reachability.py tests/test_correspondence.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
62 passed, 5 warnings in 9.74s
```

(That run also included `tests/test_correspondence.py`.)

UI, `npm --prefix ui ci` then `npm --prefix ui test` (and `tsc` clean):

```
 Test Files  35 passed (35)
      Tests  462 passed (462)
```

Black reports every changed Python file unchanged. flake8 and mypy on the
changed files report no finding that is absent from the same files at
`588fc543`; both trees carry the repository's existing findings. The review
fixes add no flake8 or mypy finding over the previous head `64229627`.
