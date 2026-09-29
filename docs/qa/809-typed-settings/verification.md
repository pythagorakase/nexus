# Issue 809: Typed Settings Readers Verification

Branch `claude/809-typed-settings-readers`, cut from `588fc543` on
2026-09-29. No `save_NN` database or `NEXUS_template` was written; the
PostgreSQL-backed tests ran on their fixtures' own disposable clones. No paid
provider call was made.

## Ownership Table

`tests/config/test_settings_parity.py` declares the typed owner of every leaf
the legacy façade (`load_settings_as_dict()`) exposes under its two alias
blocks, and proves the effective values agree with `load_settings()`.

| Façade root | Typed owner | Leaves owned |
|---|---|---|
| `Agent Settings.global` | `global_` | 4 |
| `Agent Settings.LORE` | `lore` | 26 |
| `Agent Settings.MEMNON` | `memnon` | 69 |
| `API Settings.apex` | `apex` | 18 |
| **Total** | | **117** |

Nine open-keyed registries are allowlisted in `DYNAMIC_REGISTRIES` and
compared as whole sub-trees: the provider registry
(`global_.model.api_models`), the two provider-override tables
(`lore.token_budget.provider_overrides`,
`lore.entity_inclusion.provider_overrides`), the embedding registry
(`memnon.models`), the reranker candidates, and four query-type weight maps.

The walk fails on a façade leaf with no owner, an owner path that does not
exist on `Settings` (it caught `memnon.import` versus the field `import_`), an
owner outside its root, or a value drift. A planted drift and a planted
unowned leaf are both named, so the walk is not vacuous.

## Assembled-Request Fingerprint

`tests/test_lore/test_assembled_prompt_fingerprint.py` builds one fixed
two-pass turn on the real TEST route and records the SHA-256 of the exact
`responses.create` kwargs for the Writer and Gaia seats, plus the budget
lines (payload budget, per-provider context windows and entity inclusion,
deep-query budget, presence-boost flag, Pass-2 config fingerprint). The
values were recorded at the parity commit `688cb431`, before any reader
moved, and pass unchanged at the head.

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

Parity and fingerprint at the parity commit (`git archive 688cb431`, import
proven from that tree) and at the head:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
9 passed in 0.79s
secret-store guard: active; nexus-api: denied; disposable keychain: denied
9 passed in 0.82s
```

`NEXUS_RUN_POSTGRES=1 python -m pytest -q tests/test_lore` (then
`tests/config`, `tests/test_config`, `tests/test_memnon`), with
`NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset:

```
FAILED tests/test_lore/test_pass2_chunk1369.py::test_pass2_handles_karaoke_divergence
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
2 failed, 452 passed, 1 skipped in 114.74s (0:01:54)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
109 passed in 3.08s
secret-store guard: active; nexus-api: denied; disposable keychain: denied
82 passed in 3.79s
secret-store guard: active; nexus-api: denied; disposable keychain: denied
51 passed in 28.06s
```

Both lore failures reproduce unchanged on an export of `588fc543`:
`test_retrieval_coverage_live` hardwires the owner's empty slot 5 (#885,
exempt: `need-clock anchor unavailable: no canonical world time or
base_timestamp`), and `test_pass2_chunk1369` patches `get_recent_chunks`
with a lambda that rejects the `through_chunk_id` keyword the turn cycle
already passed at the base (`FATAL: No warm slice chunks retrieved`).

Offline suite, `python -m pytest -q`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
4110 passed, 1043 skipped in 287.89s (0:04:47)
```

`python -m pytest -q tests/test_reachability.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 9.25s
```

UI, `npm --prefix ui ci` then `npm --prefix ui test` (and `tsc` clean):

```
 Test Files  35 passed (35)
      Tests  462 passed (462)
```

Black reports every changed Python file unchanged. flake8 and mypy on the
changed files report no finding that is absent from the same files at
`588fc543`; both trees carry the repository's existing findings.
