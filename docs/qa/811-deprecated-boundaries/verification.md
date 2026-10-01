# Verification: Deprecated-Category Boundaries and the Three live_llm Markers (#811 S2, S7)

Branch `claude/811-deprecated-boundaries`, cut from and rebased onto `origin/main` at `41783c1d`. Every PostgreSQL run below ran from the worktree root with `PYTHONPATH=$PWD`, the shared interpreter, `-p tests.dbname_audit`, and `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` and `NEXUS_RUN_LIVE_LLM` unset. No run wrote to a `save_NN` or to `NEXUS_template`; every audit tail reads `owner targets: none`.

## Red Runs Against `main`

A detached scratch worktree at `origin/main` (`41783c1d`) received the branch's six test files (`tests/test_orrery_tag_validation_pg.py`, `tests/test_orrery/test_retrograde_maturation.py`, `tests/test_api/test_wizard_confirmation_pg.py`, `tests/test_entity_tag_manifest_apply.py`, `tests/test_faction_table_audit.py`, `tests/test_prompt_tag_vocabulary_pg.py`) and kept `main`'s product code, prompt and golden-path fixture. Only the new test ids ran:

```
FAILED tests/test_orrery_tag_validation_pg.py::test_writer_rejects_deprecated_category_application[characters-active_character-character-black_market_operator]
FAILED tests/test_orrery_tag_validation_pg.py::test_writer_rejects_deprecated_category_application[places-place-place-worksite]
FAILED tests/test_orrery_tag_validation_pg.py::test_writer_rejects_deprecated_category_application[factions-faction-faction-gray_legal]
FAILED tests/test_orrery_tag_validation_pg.py::test_validate_tag_bestowal_splits_application_from_clear[characters-active_character-character-black_market_operator]
FAILED tests/test_orrery_tag_validation_pg.py::test_validate_tag_bestowal_splits_application_from_clear[places-place-place-worksite]
FAILED tests/test_orrery_tag_validation_pg.py::test_validate_tag_bestowal_splits_application_from_clear[factions-faction-faction-gray_legal]
FAILED tests/test_orrery_tag_validation_pg.py::test_staged_draft_with_deprecated_category_application_fails
FAILED tests/test_orrery/test_retrograde_maturation.py::test_pg_deprecated_category_tag_hint_fails_loudly
FAILED tests/test_api/test_wizard_confirmation_pg.py::test_wildcard_with_deprecated_category_tag_gets_model_retry
FAILED tests/test_entity_tag_manifest_apply.py::test_apply_entity_tag_manifest_rejects_deprecated_category_on_clone
FAILED tests/test_faction_table_audit.py::test_live_faction_apply_rejects_deprecated_category_tag
FAILED tests/test_prompt_tag_vocabulary_pg.py::test_prompt_backticked_tags_are_live_tags_in_live_categories
FAILED tests/test_prompt_tag_vocabulary_pg.py::test_wildcard_description_names_only_live_character_categories
13 failed, 4 passed, 5 warnings in 9.71s
```

The failure reasons on `main`: the writer, exclusive writer, staged-draft commit, retrograde enqueue and faction applicator `DID NOT RAISE`; `validate_tag_bestowal` returned `[]` where one `applied_tags:` issue was expected; the wizard tool raised `CallDeferred` (it accepted `informant_handler`) instead of `ModelRetry`; the entity-tag applicator passed the tag lookup and failed later on `Manifest targets missing entity_id=1001`; the prompt check found `cellular_clandestine (operational_secrecy)` and `informant_handler (profession_lite)`, and the description check found `['bodyform', 'role']`.

```
FAILED tests/test_prompt_tag_vocabulary_pg.py::test_prompt_backticked_tags_are_live_tags_in_live_categories
FAILED tests/test_prompt_tag_vocabulary_pg.py::test_wildcard_description_names_only_live_character_categories
2 failed, 1 passed in 1.48s
```

The four passes on `main` are by design: clearing a deprecated-category tag already worked there (three `..._clears_active_deprecated_category_tag_with_ledger` cases), and `main`'s writer accepts the fixture's `fixer`, `salvager` and `broker` (the golden-path case). Two scratch reverts in the same scratch worktree show both tests bite:

```
--- scratch A: branch writer + main fixture (fixer/salvager/broker kept)
E         Left contains 3 more items, first extra item: "applied_tags: Orrery tag 'fixer' has category 'profession_lite', which tag_category_registry deprecates for entity_kind='character'; bestowal uses the live library only (replacement categories: role.function)"
1 failed in 1.35s
--- scratch B: branch writer with tags_to_clear validated as an application
E           ValueError: Orrery tag 'black_market_operator' has category 'profession_lite', which tag_category_registry deprecates for entity_kind='character'; bestowal uses the live library only (replacement categories: role.function)
E           ValueError: Orrery tag 'worksite' has category 'place_affordance', which tag_category_registry deprecates for entity_kind='place'; bestowal uses the live library only (replacement categories: place_function, place_visibility, place_access, place_environment, place_threat)
E           ValueError: Orrery tag 'gray_legal' has category 'legitimacy_status', which tag_category_registry deprecates for entity_kind='faction'; bestowal uses the live library only (replacement categories: legitimacy)
3 failed in 0.96s
```

The scratch worktree was removed afterward (`git worktree remove`).

## The Order's Proof Set (Branch)

`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery_tag_validation_pg.py tests/test_orrery_tag_validation.py tests/test_commit_handler_sync.py tests/test_orrery/test_tag_writer.py tests/test_orrery/test_retrograde_maturation.py tests/test_api/test_wizard_confirmation_pg.py tests/test_entity_tag_manifest_apply.py tests/test_faction_table_audit.py tests/test_prompt_tag_vocabulary_pg.py tests/test_pg_legacy_faction_tag_seed.py tests/test_tags_audit_pg.py tests/test_connection_lifecycle.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 36 targets: mock, postgres, qa640_811_tags_audit_* x5, qa640_811_tags_audit_nocol_*, qa640_compaction_retry_*, qa640_maturation799_*, qa640_offline_gate_* x17, qa649_*, qa811_entity_manifest_*, qa811_prompt_vocab_*, qa885_faction_audit_*, qa885_legacy_tag_* x4, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:50779 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:50784 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:50779 (psycopg2), save_04@local:50784 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
369 passed, 5 warnings in 92.81s (0:01:32)
```

`tests/test_connection_lifecycle.py` transitions the trimmed golden-path fixture through `continue --accept-fate` inside this run.

## 811-S7: The Three Modules

`origin/main`, from a detached scratch worktree (`PYTHONPATH=<scratch>`, shared interpreter):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [5] tests/test_orrery/test_stage2a_status_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [18] tests/test_orrery/test_claim_propagation_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_claim_propagation_live.py:1075: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py:546: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
32 skipped in 0.23s
```

Branch:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa885_claim_propagation_*, qa885_composition_sources_*, qa885_stage2a_status_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
32 passed in 9.35s
```

### Item 9 Grep (Before the Edit)

The three modules, the one `tests/` helper module they import besides `tests/pg_fixtures.py` (`tests/test_orrery/claim_accounts_test_support.py`), and `tests/pg_fixtures.py`:

```
$ grep -nEi "openai|anthropic|httpx|requests\.|aiohttp|urlopen|pydantic_ai|Agent\(|TestClient|api_models|responses\.(parse|create)|chat\.completions|provider|llm" <three modules> tests/test_orrery/claim_accounts_test_support.py tests/pg_fixtures.py
tests/test_orrery/test_composition_sources_live.py:54:pytestmark = [pytest.mark.requires_postgres, pytest.mark.live_llm]
tests/test_orrery/test_stage2a_status_live.py:52:pytestmark = [pytest.mark.requires_postgres, pytest.mark.live_llm]
tests/test_orrery/test_claim_propagation_live.py:73:pytestmark = [pytest.mark.requires_postgres, pytest.mark.live_llm]
tests/pg_fixtures.py:160:    the source pin requires the explicit live-LLM opt-in.
tests/pg_fixtures.py:166:    if story_pin is None and os.environ.get("NEXUS_RUN_LIVE_LLM") != "1":
tests/pg_fixtures.py:167:        raise ValueError("story_pin=None requires NEXUS_RUN_LIVE_LLM=1")
tests/pg_fixtures.py:1374:# The TEST provider's registered model id; a fixture turn records it as the
tests/pg_fixtures.py:1554:    ``drain_narration_outbox_sync`` (deterministic descriptors; no provider
tests/pg_fixtures.py:1901:# The TEST provider's registered model id; a fixture turn records it as the
tests/pg_fixtures.py:2348:                "llm_response_id": f"fixture_{uuid.uuid4().hex[:8]}",
tests/pg_fixtures.py:2623:    so a scheduler that renders it reaches only the TEST provider; the helper
```

The only hits in the three modules are the markers themselves; the `pg_fixtures` hits are comments and the TEST-pin guard. All three modules build their clone with `disposable_slot_database(...)` at its default `story_pin="TEST"` (`test_stage2a_status_live.py:69`, `test_claim_propagation_live.py:148`, `test_composition_sources_live.py:139`).

## Full PostgreSQL Gate (Branch, Split by Directory)

| Slice | Tail |
| --- | --- |
| `tests/test_orrery` | `1675 passed, 10 skipped, 2 warnings in 317.89s` |
| `tests/test_api` | `871 passed, 4 skipped, 9 warnings in 525.17s` |
| `tests/config tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_util tests/proofs tests/live_*_test.py` | `863 passed, 5 skipped, 9 warnings in 254.07s` |
| top-level `tests/test_*.py`, files 1-41 | `653 passed, 11 skipped, 4 warnings in 420.90s` |
| top-level `tests/test_*.py`, files 42-82 | `781 passed, 10 skipped, 3 warnings in 130.50s` |
| top-level `tests/test_*.py`, files 83-121 | `720 passed, 16 skipped, 4 warnings in 233.00s` |

Every slice printed `secret-store guard: active; nexus-api: denied; disposable keychain: denied` and `dbname audit: owner targets: none`. No failure appeared, including none of the #885 slot-5 exemptions. The 56 skips, by gate:

- `NEXUS_RUN_LIVE_LLM` (`live_llm` and the live-module skips that read the same flag): 31. `test_live_cycle`, `test_retrograde_live`, `test_retrograde_maturation_live`, `test_conversations:377`, `test_secrets_endpoints:268,279` (2), `live_seed_schema_test`, `live_set_designer_test`, `test_local_skald_live`, `test_model_registry_live` (3), `test_new_story_integration` (2), `test_new_story_schemas:756,775` (4), `test_wizard_live:244,294` (13).
- `NEXUS_RUN_CORPUS` (`requires_corpus`): 7. `test_card_identity:121` (2), `test_projects:609`, `test_recruit_ally_projects:808`, `test_lore/test_infrastructure:219`, `test_lore/test_pass2_chunk1369`, `test_memnon/test_ann_gate:115`.
- Explicit opt-in live gates: 14. `NEXUS_GOLDEN_PATH_E2E` (`test_golden_path_live`, 8), `NEXUS_CONSPIRACY_E2E` (`test_correspondence_live`), `NEXUS_ISSUE_601_LIVE` (`test_issue_601_wizard_live:125`), `NEXUS_ISSUE_600_LIVE` (`test_wizard_live:433`), `NEXUS_638_ENUM_E2E` (`test_gaia_registry_schema_pg:347`), `NEXUS_639_PRESENCE_E2E` (`test_skald_wire:2110`), `NEXUS_RETROGRADE_WIZARD_E2E` (`test_retrograde_wizard_live`).
- Paid authorization: 1. `test_narrative_summary_paid_pg` (two-call summary authorization).
- Environment: 3. `test_retrograde_retrieval_live` (`NEXUS_RETROGRADE_RETRIEVAL_TEST_DB_URL` unset), `test_memnon_cross_encoder_dependencies:28` (local DeBERTa model absent), `test_secret_store_integration` (`NEXUS_RUN_SECRET_STORE` unset).

31 + 7 + 14 + 1 + 3 = 56.

## Offline Suites, Reachability, Lint

```
$ $PY -m pytest -q tests/test_api tests/test_orrery
1816 passed, 744 skipped, 7 warnings in 38.88s
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
2625 passed, 434 skipped, 8 warnings in 411.92s (0:06:51)
$ $PY -m pytest -q tests/test_reachability.py
38 passed, 5 warnings in 11.69s
```

Each printed the secret-store guard line. Black: `17 files would be left unchanged`. flake8 on the 17 changed Python files reports the same count per file as `origin/main` (no new finding). mypy on the four product files: `Success: no issues found in 4 source files`; the changed test files raise no mypy error on a line this branch adds.
