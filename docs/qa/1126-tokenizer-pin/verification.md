# Pin and Fetch the Prompt-Window Tokenizers (1126-S1)

Frozen order 1126-S1 on `claude/1126-tokenizer-pin`, cut from `origin/main`
c7ae2988d07b443f627a04d3a4eed1816b1cd438 (still the newest `origin/main` when
this was written). Closes #1126, refs #812. Decisions 1126-D1 to D9 are
recorded on #1126. No migration, no `ui/` change, no gateway lane, no paid
call; the one network use is the free Hugging Face tokenizer download in the
manual proof below.

## What Was Wrong on Main (c7ae2988)

- `nexus/telemetry/prompt_window.py:347-352`: `_load_tokenizer(repository)`
  ran `AutoTokenizer.from_pretrained(repository, trust_remote_code=False)`
  with no revision and no `local_files_only`, so it followed each
  repository's `main` and downloaded on first use. It was the last
  `from_pretrained` under `nexus/` without `local_files_only=True`; compare
  `nexus/agents/memnon/utils/cross_encoder.py:538-544`.
- Callers: `local_text_counter` (`prompt_window.py:132-139`, the only one
  wrapping errors in `_tokenizer_error`, `:113-120`), `local_request_counter`
  (`:162-175`) and `rendered_request_counter` (`:284-344`, load at `:332`).
  The per-turn counter cache key was `(entry.tokenizer_encoding,
  entry.tokenizer_repository)` (`nexus/agents/lore/logon_utility.py:1713`).
- `APIModelEntry` had `tokenizer_repository` and `tokenizer_encoding` and no
  revision (`nexus/config/settings_models.py:111-113`).
- The lock and `nexus models lock|verify|plan|fetch` covered only the
  embedder and the reranker (`artifact_manifest.py:106-146`); `_plan_artifacts`
  and `_fetch_artifacts` return early on embedder configuration problems
  (`:780-781`, `:832-833`) and fetch refuses everything when a folder drifts
  (`:850-853`). The boot check (`:731-748`) and the doctor check
  `models.artifacts` (`nexus/runtime/readiness.py:1092-1110`) saw no tokenizer.
- The commit probe loaded every declared repository from the Hub
  (`scripts/validate_config_commit.py:41-90`).
- `docs/vector_embeddings.md:115-117` put the tokenizer "outside this rule".

## The Five Pins and the Hub Cache

Read-only listing of the owner's default Hugging Face cache, 2026-10-26 16:12
CDT (`~/.cache/huggingface/hub`):

| Repository | Pinned revision | `refs/main` now | Snapshot files |
| --- | --- | --- | --- |
| `NousResearch/Hermes-4-70B` | d5dec2bd6b3930a09ddefd0b7fc6523fe0720d09 | same | chat_template.jinja, special_tokens_map.json, tokenizer_config.json, tokenizer.json |
| `NousResearch/Hermes-4.3-36B` | 3899db2b6c4b35f16bde3b570bb7dd2775d56161 | same | same four |
| `deepseek-ai/DeepSeek-V4-Pro` | b5968e9190ef611bbf34a7229255be88a0e937c1 | same | tokenizer_config.json, tokenizer.json |
| `NousResearch/Hermes-4-405B` | 88e3dce03c4a5535e2f4a2bcc08e939a2b302f82 | same | same four as Hermes 70B |
| `MiniMaxAI/Minimax-M3` | f0e1c1e04d40177e4673a22097036854f536e9c0 | d95e30cb912fe3021bb9c2ba66a8ce60b6c937a9 | added_tokens.json, chat_template.jinja, special_tokens_map.json, tokenizer_config.json, tokenizer.json |

Sizes: 33M, 23M, 12M, 33M, 28M (`du -shL`).

Finding: MiniMax's `refs/main` moved to d95e30cb… at 13:38 CDT today, after the
coordinator's read and before this build began (16:11). Something ran the
unpinned loader against the Hub, so it followed `main`. This is the drift the
issue describes. The order's pin f0e1c1e… is still in the cache. Both
snapshots link every file to the same blob (43c846ca…, 93022eb9…, c55c5c84…,
44840ad8…, 9065e14e…), so pinning f0e1c1e… does not change any count. This
build never wrote to the default cache; `find … -newer red.log` over the five
repository folders lists nothing.

## Lock Diff

`config/model_artifacts.lock.json` was loaded, given `tokenizers` from
`registry_tokenizer_specs(load_settings())`, and written back with
`write_manifest`. Nothing was re-hashed. The only change is the added key
(`lock.diff` in this folder):

```diff
-  "schema_version": 1
+  "schema_version": 1,
+  "tokenizers": [
+    {"repo_id": "MiniMaxAI/Minimax-M3", "revision": "f0e1c1e04d40177e4673a22097036854f536e9c0"},
+    {"repo_id": "NousResearch/Hermes-4-405B", "revision": "88e3dce03c4a5535e2f4a2bcc08e939a2b302f82"},
+    {"repo_id": "NousResearch/Hermes-4-70B", "revision": "d5dec2bd6b3930a09ddefd0b7fc6523fe0720d09"},
+    {"repo_id": "NousResearch/Hermes-4.3-36B", "revision": "3899db2b6c4b35f16bde3b570bb7dd2775d56161"},
+    {"repo_id": "deepseek-ai/DeepSeek-V4-Pro", "revision": "b5968e9190ef611bbf34a7229255be88a0e937c1"}
+  ]
```

(The real file is pretty-printed with two-space indentation; this block is
condensed.)

## Red Run (New Tests Against Unchanged Product Code)

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rf <the 13 new test ids>
E       Failed: DID NOT RAISE <class 'ValueError'>                      # [unpinned]
E             Extra inputs are not permitted [type=extra_forbidden, input_value='main', ...]   # [branch]
E             Extra inputs are not permitted [type=extra_forbidden, input_value='aaaa…', ...]  # [encoding]
E         - Model 'nousresearch/hermes-4-70b': tokenizer_repository 'NousResearch/Hermes-4-70B' at tokenizer_revision None is not in the local Hugging Face cache. Run `nexus models fetch` to download it.
E         + Model 'nousresearch/hermes-4-70b': cannot load tokenizer_repository 'NousResearch/Hermes-4-70B' with trust_remote_code=False. ... Cause: We couldn't connect to 'https://hug...
E             Extra inputs are not permitted [type=extra_forbidden, input_value='1111…', ...]  # unfetchable pin
E             Extra inputs are not permitted [type=extra_forbidden, input_value='2222…', ...]  # cached pin (x5)
E       AssertionError: assert ['nexus/telem...indow.py:352'] == []
E           Extra inputs are not permitted [type=extra_forbidden, input_value='4444…' / '5555…', ...]  # D9 key
E             Extra inputs are not permitted [type=extra_forbidden, input_value='0123456789abcdef…', ...]  # x4 artifact tests
E       AssertionError: assert None == [{'repo_id': 'MiniMaxAI/Minimax-M3', 'revision': None}, ...]
FAILED tests/test_lore/test_token_estimator.py::test_settings_require_a_pinned_tokenizer_revision[unpinned]
FAILED tests/test_lore/test_token_estimator.py::test_settings_require_a_pinned_tokenizer_revision[branch]
FAILED tests/test_lore/test_token_estimator.py::test_settings_require_a_pinned_tokenizer_revision[encoding]
FAILED tests/test_lore/test_token_estimator.py::test_first_use_on_an_empty_hf_cache_names_the_fetch_command
FAILED tests/test_lore/test_token_estimator.py::test_commit_probe_names_an_unfetchable_pin
FAILED tests/test_lore/test_token_estimator.py::test_commit_probe_accepts_a_cached_pin
FAILED tests/test_lore/test_token_estimator.py::test_every_tracked_from_pretrained_call_is_local_only
FAILED tests/test_lore/test_token_estimator.py::test_window_counter_cache_keys_on_the_revision
FAILED tests/test_embedding_artifacts.py::test_tokenizer_section_reports_absent_then_present
FAILED tests/test_embedding_artifacts.py::test_fetch_handles_tokenizers_when_the_embedder_drifts
FAILED tests/test_embedding_artifacts.py::test_tokenizer_pin_drift_is_a_configuration_problem
FAILED tests/test_embedding_artifacts.py::test_boot_check_ignores_tokenizers
FAILED tests/test_model_artifact_lock_committed.py::test_committed_lock_pins_every_registry_tokenizer
13 failed, 5 warnings in 9.30s
```

Decision 1126-D9 key check: with items 1 to 8 in place and only the
`logon_utility.py` cache key put back to two elements, the D9 test still fails
because the second entry reuses the first counter:

```
E       assert 2 != 2
1 failed, 5 warnings in 4.95s
```

With the three-element key it passes (`[2, 1]`).

## Green Runs

PostgreSQL proof set (one session; `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT` unset; load 17.37 at start):

```
$ NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_lore/test_token_estimator.py tests/test_lore/test_token_budget.py tests/test_lore/test_turn_cycle.py tests/test_embedding_artifacts.py tests/test_model_artifact_lock_committed.py tests/test_runtime/test_readiness.py tests/config tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 9 targets: postgres, qa640_816_lifecycle_test_provider, qa640_818_estimate_*, qa640_818_pin_* x2, qa640_885_ren_replay_* x4
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:57195 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:57198 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:57195 (psycopg2), save_04@local:57198 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
320 passed, 2 skipped, 7 warnings in 122.27s (0:02:02)
```

The two skips: `SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set
NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.`

Offline suites:

```
$ nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3209 passed, 678 skipped, 8 warnings in 645.45s (0:10:45)

$ nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 46.37s

$ $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py tests/test_cli_reference_doc.py
130 passed, 5 warnings in 16.81s
```

## Manual Real Fetch (One Attempt, No Retry)

`manual_fetch.py.txt` ran `fetch_tokenizers(verify_tokenizers(s,
read_manifest(lock_file_path(s))))` with network and a fresh
`HF_HOME=<scratch>/1126-S1/hf`. It did not use the CLI, whose fetch would also
re-hash the 9.8 GB embedder and reranker. Output (`manual_fetch.out.log`,
progress bars omitted):

```
[
  true,
  [
    "tokenizer MiniMaxAI/Minimax-M3 @ f0e1c1e04d40177e4673a22097036854f536e9c0: downloaded into the Hugging Face cache",
    "tokenizer NousResearch/Hermes-4-405B @ 88e3dce03c4a5535e2f4a2bcc08e939a2b302f82: downloaded into the Hugging Face cache",
    "tokenizer NousResearch/Hermes-4-70B @ d5dec2bd6b3930a09ddefd0b7fc6523fe0720d09: downloaded into the Hugging Face cache",
    "tokenizer NousResearch/Hermes-4.3-36B @ 3899db2b6c4b35f16bde3b570bb7dd2775d56161: downloaded into the Hugging Face cache",
    "tokenizer deepseek-ai/DeepSeek-V4-Pro @ b5968e9190ef611bbf34a7229255be88a0e937c1: downloaded into the Hugging Face cache"
  ]
]
```

Then, with `HF_HUB_OFFLINE=1`, `manual_counts.py.txt` counted one fixed
sentence through each entry's `local_text_counter(entry)`, once from the fresh
`HF_HOME` and once from the default cache (`manual_counts.out.log`):

```
sentence: "The quick brown fox jumps over the lazy dog; <|endoftext|> stays text."
nousresearch/hermes-4-70b: NousResearch/Hermes-4-70B @ d5dec2bd…: fresh HF_HOME 19, default cache 19, equal=True
nousresearch/hermes-4.3-36b: NousResearch/Hermes-4.3-36B @ 3899db2b…: fresh HF_HOME 20, default cache 20, equal=True
deepseek/deepseek-v4-pro: deepseek-ai/DeepSeek-V4-Pro @ b5968e91…: fresh HF_HOME 20, default cache 20, equal=True
nousresearch/hermes-4-405b: NousResearch/Hermes-4-405B @ 88e3dce0…: fresh HF_HOME 19, default cache 19, equal=True
minimax/minimax-m3: MiniMaxAI/Minimax-M3 @ f0e1c1e0…: fresh HF_HOME 19, default cache 19, equal=True
all five counts equal
```

`du -sh <scratch>/1126-S1/hf`: `60M`. The fresh cache holds one snapshot per
repository, with the same files as the default-cache listing above.

## Static Checks

`black --check` passes on all nine changed Python files.

flake8 (`flake8.log`) gives the same 23 diagnostics on the branch and on the
`origin/main` versions after normalizing line numbers. They are pre-existing
E501/F401 on untouched lines of `logon_utility.py`, `settings_models.py` and
`test_token_estimator.py`. There are no new diagnostics.

mypy, `$PY -m mypy --explicit-package-bases <changed files>` (`mypy.log`),
compared over the changed files with line numbers normalized: no new
diagnostics. Gone on the branch: the `sorted` type-var error in
`scripts/validate_config_commit.py` and eight tomlkit `Item | Container`
errors in `test_token_estimator.py` (the edited tests annotate `entry: Any`).
The branch run reports 34 errors in 4 files; the remaining ones are
pre-existing on untouched lines. The `origin/main` run was made in a
`git archive origin/main` export, which follows imports into the whole tree
(294 errors in 53 files); only the changed files were compared.

Exception dispositions:

```
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

One new marked handler: `fetch_tokenizers` catches `(OSError,
ArtifactLockError)` and carries `# nexus-exception-disposition: fail;
reason=hub; safety=failed result`. The baseline is unchanged. The new handlers
in `tokenizer_cached` and `_entry_tokenizer` always raise.

## Document Freshness

AGENTS.md, `docs/turn_flow_sequence.md`, and decisions 0009, 0010, 0019, 0024
and 0034 were re-read against the changed sources. None of them makes a claim
about tokenizers. 0019's `logon_utility.py:2457-2476` is a quote of #849's
historical verdict, not a current claim. Each `verified_commit` moved to the
merge base c7ae2988d07b443f627a04d3a4eed1816b1cd438;
`tests/test_doc_front_matter.py` passes.
