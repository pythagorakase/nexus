# Issue 809: Typed Settings Readers Verification

Branch `claude/809-typed-settings-readers`, cut from `588fc543` on
2026-09-29, with `origin/main` at `aba785b0` merged in (merge commit, no
history rewrite) so the PostgreSQL tests run against the template after
migration 134 (#1017). No `save_NN` or `NEXUS_template` was written by this
branch's code; the pre-existing `test_retrieval_coverage_live` (#885) opens a
rolled-back transaction on live `save_05` as part of the ordered gate (its id
sequences advance, so the coordinator should expect `save_05` sequence drift
after any `tests/test_lore` PostgreSQL run until that test moves onto a seeded
disposable clone; recorded on #885). No paid provider call was made.

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
inside a registry fails, as it does for a leaf; list leaves such as
`memnon.retrieval.vector_normalization.tiers` are compared element-wise the
same way): the provider registry
(`global_.model.api_models`), the two provider-override tables
(`lore.token_budget.provider_overrides`,
`lore.entity_inclusion.provider_overrides`), the embedding registry
(`memnon.models`), the reranker candidates, and four query-type weight maps.

The walk fails on a façade leaf with no owner, an owner path that does not
exist on `Settings` (it caught `memnon.import` versus the field `import_`), an
owner outside its root, an owner that is not its façade path mapped through
each model's field aliases (`OWNER_PATH_EXCEPTIONS` is empty), or a value
drift. A planted drift, a planted int/float drift inside the `tiers` list
leaf (which `==` alone calls equal), a planted unowned leaf, and a planted
Writer-to-Gaia
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

The recorded fixture gives both seats temperature `0.7`, because the
`688cb431` export had no Gaia temperature field to record, so the digests
cannot see a Gaia site that reads the Writer's `apex.temperature`.
`test_writer_and_gaia_temperatures_come_from_their_own_seats` covers that
separately: with `apex.gaia.temperature` set to `0.3` it asserts the writer
provider and Writer clone carry `0.7` and the Gaia clone `0.3`, and that
`_build_gaia_provider()` on the TEST route (an OpenAI Responses provider)
carries `0.3`. Planting `self.settings.apex.temperature` at either Gaia site
(the clone, or the pinned provider) fails it.

The digests can be re-recorded from an export of `688cb431` (run from the
export root with `PYTHONPATH=$PWD`): the parity commit's own fixture, with the
Gaia overrides written into the legacy dict.

```python
import json
import pytest
import tests.test_lore.test_assembled_prompt_fingerprint as fp
from nexus.config import load_settings_as_dict

GAIA = {"max_output_tokens": 23_000, "reasoning_reserve_tokens": 19_000,
        "response_reserve_tokens": 3_500, "reasoning_effort": "high"}

def settings():
    d = load_settings_as_dict()
    for apex in (d["apex"], d["API Settings"]["apex"]):
        apex["gaia"].update(GAIA)
    return d

fp._settings = settings
mp = pytest.MonkeyPatch()
try:
    requests = fp._assembled_requests(mp)
finally:
    mp.undo()
print(json.dumps({seat: fp._digest(r) for seat, r in requests.items()}, indent=4))
```

```
{
    "writer": "09b26dfed922d661ebbed44ac7f8e5621f5a21734d99d078c2718cb5b505cac6",
    "gaia": "cac3d730f8b3e3081aa4f297a642694fb1f937ffd0639f4f906c70c14e11da6f"
}
```

## Orrery Section Reads

`LogonUtility` and `TurnCycleManager` read the typed `settings.orrery`
section directly; neither dumps the whole `Settings` nor re-validates Orrery
submodels from dict defaults. The absent-section rule is stated once per
class: in the turn cycle, `_enabled_orrery()` returns `None` when `[orrery]`
is absent or disabled; in LOGON, `_retrograde_maturation()` and
`_orrery_prompt_settings()` take the model defaults when it is absent. The
only remaining dump is `orrery.model_dump(by_alias=True)` of the Orrery
section alone, once in the resolve phase, because the resolver's settings
consumers take plain mappings.

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

Parity and fingerprint at the parity commit, on `git archive 688cb431`
extracted to a scratch directory (the import resolves inside the export):

```
$ PYTHONPATH=$PWD python -c 'import nexus;print(nexus.__file__)'
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/p688/nexus/__init__.py
$ PYTHONPATH=$PWD python -m pytest -q tests/config/test_settings_parity.py tests/test_lore/test_assembled_prompt_fingerprint.py -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
9 passed, 5 warnings in 0.74s
```

Parity and fingerprint at the head:

```
$ PYTHONPATH=$PWD python -m pytest -q tests/config/test_settings_parity.py tests/test_lore/test_assembled_prompt_fingerprint.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
12 passed, 5 warnings in 0.62s
```

`NEXUS_RUN_POSTGRES=1 python -m pytest -q tests/test_lore` (then
`tests/config`, `tests/test_config`, `tests/test_memnon`), with
`NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset. `tests/test_lore`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_lore/test_pass2_chunk1369.py::test_pass2_handles_karaoke_divergence
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
2 failed, 453 passed, 1 skipped, 9 warnings in 112.59s (0:01:52)
```

`tests/config`, `tests/test_config`, `tests/test_memnon`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
111 passed, 5 warnings in 3.15s
secret-store guard: active; nexus-api: denied; disposable keychain: denied
82 passed, 5 warnings in 3.75s
secret-store guard: active; nexus-api: denied; disposable keychain: denied
51 passed, 5 warnings in 27.68s
```

Both lore failures reproduce unchanged on an export of `588fc543`:
`test_retrieval_coverage_live` hardwires the owner's empty slot 5 (#885,
exempt: `need-clock anchor unavailable: no canonical world time or
base_timestamp`), and `test_pass2_chunk1369` patches `get_recent_chunks`
with a lambda that rejects the `through_chunk_id` keyword the turn cycle
already passed at the base (`FATAL: No warm slice chunks retrieved`).
`test_pass2_chunk1369` is not a #885 exemption: it is a pre-existing failure
left for the coordinator's triage.

The edited `*_pg.py` files outside the four ordered directories, at the
merged head:

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD python -m pytest -q \
    tests/test_api/test_acceptance_staging_pg.py tests/test_api/test_backstage_endpoints_pg.py \
    tests/test_api/test_correspondence_pg.py tests/test_api/test_maintenance_locked_pg.py \
    tests/test_api/test_narrative_retry_pg.py tests/test_api/test_orrery_config_reuse_pg.py \
    tests/test_api/test_reentry_wire_pg.py tests/test_api/test_return_recap_pg.py \
    tests/test_commit_choice_presence_pg.py tests/test_orrery/test_character_experiences_pg.py \
    tests/test_orrery/test_recall_disclosure_pg.py tests/test_orrery_tag_validation_pg.py \
    tests/test_player_identity_consumers_pg.py tests/test_presence_roster_pg.py \
    tests/test_wizard_opening_presence_pg.py tests/test_world_clock_contract_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_api/test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision
1 failed, 211 passed, 9 warnings in 202.31s (0:03:22)
```

The one failure is #885-exempt and reproduces on an export of `origin/main`
(`aba785b0`): after the recap request the test calls `get_slot_state(5)`,
which opens the owner's live `save_05`, finds no pending draft there, and
fails `assert pending is not None and pending.has_pending`.

The merge brought main's new PostgreSQL fixtures (`seed_pending_turn`, the
accepted-turn factory) onto the typed `story_context_settings()` and
`empty_pass2_baseline()`. Their consumers and the merged
knowledge-surfacing harness:

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD python -m pytest -q tests/test_pg_accepted_turn_factory.py \
    tests/test_pg_disposable_target.py tests/test_api/test_seat_policy_jobs_pg.py \
    tests/test_api/test_scheduler_corpus_pg.py tests/test_api/test_attempt_manifest_pg.py \
    tests/test_orrery/test_knowledge_surfacing_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
42 passed, 9 warnings in 52.58s
```

`NEXUS_RUN_POSTGRES=1 python -m pytest -q tests/test_orrery` (it exercises
the turn cycle's typed Orrery reads) reports
`12 failed, 1604 passed, 39 skipped, 7 warnings, 9 errors in 254.22s`. All 21
failing or erroring ids (`test_reveal_live` ×9,
`test_faction_project_contexts_live` ×8 errors, `test_adjudication_history`,
`test_evidence`, `test_tag_library` save_05 completeness,
`test_polymorphic_patron_live`) fail identically on an export of
`origin/main` (`aba785b0`), which additionally fails
`test_config.py::test_orrery_settings_load_queue_and_resolution_defaults`.
None is introduced by this branch; they are left for the coordinator.

Offline suite, `PYTHONPATH=$PWD python -m pytest -q` (the worktree must be
on `PYTHONPATH`: `test_postgres_installer_helper_from_foreign_directory` runs
a subprocess from another directory, and without it that subprocess imports
the main checkout's `nexus`, whose models reject the new temperature keys):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
4137 passed, 1052 skipped, 8 warnings in 272.33s (0:04:32)
```

`python -m pytest -q tests/test_reachability.py`:

```
38 passed in 7.99s
```

UI, `npm --prefix ui ci` then `npm --prefix ui test` (and `tsc` clean; no UI
file changed after this run):

```
 Test Files  35 passed (35)
      Tests  462 passed (462)
```

Black reports every changed Python file unchanged. flake8 and mypy on the
changed files report no finding that is absent from the same files at
`588fc543`; both trees carry the repository's existing findings. The second
review round's fixes add no flake8 finding over `ae5e70e9` (identical
finding sets on `logon_utility.py` and `turn_cycle.py`), and every mypy
finding on those files sits outside the changed hunks.
