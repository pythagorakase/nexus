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
build never wrote to the default cache. The reference file is the build's first
red log in the scratch directory, last written 2026-10-26 16:16:01 CDT when that
red run finished (the red run itself used private `HF_HOME` directories);
`default_cache_find.txt` in this folder holds the run, made at 17:06 CDT in the
review-fix round after its commit 5d0a9cc5 and its tests:

```
$ find ~/.cache/huggingface/hub/models--NousResearch--Hermes-4-70B ~/.cache/huggingface/hub/models--NousResearch--Hermes-4.3-36B ~/.cache/huggingface/hub/models--deepseek-ai--DeepSeek-V4-Pro ~/.cache/huggingface/hub/models--NousResearch--Hermes-4-405B ~/.cache/huggingface/hub/models--MiniMaxAI--Minimax-M3 -newer <scratch>/1126-S1/red.log
(exit 0; no lines printed)
```

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

Re-run in the review-fix round against an export of `origin/main` c7ae2988:
`git archive origin/main | tar -x -C <scratch>/1126-S1/fix-r1/main_export`, with
the branch's `tests/test_lore/test_token_estimator.py`,
`tests/test_embedding_artifacts.py` and
`tests/test_model_artifact_lock_committed.py` copied in. The export is not a
git checkout, so the script indexes its `nexus/` tree (`git init`, `git add
nexus`, no commit) for the test that lists tracked files with `git ls-files`.
The script is `red_run.sh.txt` and the raw output is `red.txt` (both in this
folder); it names the 13 test ids. Verbatim tail:

```
$ red_run.sh   (script saved beside this log as red_run.sh.txt)
...
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
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
13 failed, 5 warnings in 8.92s
```

The failure causes in `red.txt`: `[unpinned]` does not raise (`DID NOT RAISE`);
`[branch]`, `[encoding]`, the two commit-probe tests, the D9 test and the four
artifact tests fail in `load_settings` with `Extra inputs are not permitted`
(`settings_models.py:98`); the first-use test gets today's "cannot load
tokenizer_repository … with trust_remote_code=False" text instead of the fetch
command; the AST test reports `['nexus/telem...indow.py:352']`; the committed
lock has no `tokenizers` key (`assert None == [...]`).

### Decision 1126-D9 Key Check

`d9_key.patch` (in this folder) puts the `logon_utility.py` cache key back to
two elements. It was applied to the branch tree (cdd74bd5 plus the uncommitted
fix-round edits that became 5d0a9cc5) with `git apply d9_key.patch`, the D9
test was run, the patch was removed with `git apply -R d9_key.patch`, and the
test was run again. Raw output: `d9_key.txt`. Verbatim tails:

```
$ git apply d9_key.patch
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rf -p no:cacheprovider tests/test_lore/test_token_estimator.py::test_window_counter_cache_keys_on_the_revision
...
>       assert counts[0] != counts[1], counts
E       AssertionError: [2, 2]
E       assert 2 != 2

tests/test_lore/test_token_estimator.py:371: AssertionError
...
FAILED tests/test_lore/test_token_estimator.py::test_window_counter_cache_keys_on_the_revision
1 failed, 5 warnings in 4.98s
$ git apply -R d9_key.patch
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rf -p no:cacheprovider tests/test_lore/test_token_estimator.py::test_window_counter_cache_keys_on_the_revision
...
1 passed, 5 warnings in 4.85s
```

### Lock-Shape Test (Review-Fix Round)

`test_lock_tokenizer_section_shape_is_enforced[missing|malformed]` covers a
lock without `tokenizers` (plan, verify and fetch exit 1 with "the lock records
no tokenizers"; fetch leaves no `models--*` under `HF_HOME`) and a malformed
`tokenizers` value (`run_models_command("plan", ...)["error"]` names the
malformed-lock error). Red first: `red_shape.patch` removes the
`read_manifest` check and the missing-key branch of `verify_tokenizers`; the
working tree held it while the test ran, and the fixed file was restored
afterwards (`git apply --check red_shape.patch` succeeds on 5d0a9cc5). Raw
output: `red_shape.txt`. Verbatim tail:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rf -p no:cacheprovider tests/test_embedding_artifacts.py::test_lock_tokenizer_section_shape_is_enforced
...
FAILED tests/test_embedding_artifacts.py::test_lock_tokenizer_section_shape_is_enforced[missing]
FAILED tests/test_embedding_artifacts.py::test_lock_tokenizer_section_shape_is_enforced[malformed]
2 failed, 5 warnings in 3.22s
```

(`[missing]`: the plan stderr lacks "the lock records no tokenizers";
`[malformed]`: `verify_tokenizers` raised `KeyError: 'revision'`.)

### Review Round 2 (d875e7d5)

- `run_models_command` now reads the lock, runs `verify_tokenizers`, and for
  `fetch` runs `fetch_tokenizers`, before it reads the embedder folders. The
  new `_verify_embedder` turns an `ArtifactLockError` from `verify_artifacts`
  (for example a folder whose Hugging Face metadata mixes revisions,
  `artifact_manifest.py` `_snapshot_revision`, or a `.git` whose HEAD cannot be
  read, `_git_revision`) into a failed result, and plan, fetch and verify join
  the tokenizer section to it. This is option (a) of the finding, so fetch
  handles tokenizers whatever the embedder's state, as `docs/cli.md` and the
  docstrings already said. Its handler carries
  `# nexus-exception-disposition: fail; reason=folder; safety=failed result`.
- New test `test_tokenizers_survive_an_embedder_folder_that_cannot_be_read`:
  after the lock, one embedder metadata file names a second revision; plan,
  fetch and verify each exit 1 naming both the mixed-revision error and the
  tokenizer line, and fetch writes no `models--*` under `HF_HOME`.
- `test_tokenizer_section_reports_absent_then_present` now reads plan's
  structured `tokenizers` key (a `python -c` subprocess with the same offline
  `HF_HOME`) and asserts `[{"repo_id", "revision", "models":
  ["nousresearch/hermes-4-70b"], "state": "absent"}]`, then `present` after
  the plant.
- The two edited tomlkit tests annotate the parsed document (`settings: Any`,
  `config: Any`), which clears the mypy diagnostics on their edited lines.
- `docs/vector_embeddings.md` adds one sentence after the verify remediation
  sentence naming the two tokenizer failures and their remedies.

Red first: with f827f8d3's `artifact_manifest.py` and d875e7d5's tests, the
new folder test fails (the plan stderr holds only the embedder error) and the
plan-key test passes, as expected for a test that adds coverage of an existing
key. Raw output: `round2_red.txt`. Verbatim tail:

```
>           assert tokenizer_line in result.stderr, result.stderr
E           AssertionError: Error: /private/var/folders/.../test_tokenizers_survive_an_emb0/models/embedder mixes files downloaded at several revisions ['0123456789abcdef0123456789abcdef01234567', '6666666666666666666666666666666666666666']; re-download it at one revision before locking
...
FAILED tests/test_embedding_artifacts.py::test_tokenizers_survive_an_embedder_folder_that_cannot_be_read
1 failed, 1 passed, 47 deselected in 7.91s
```

## Green Runs

The runs in this section through "Offline suites" predate the review-fix
commits and name no commit; the round-2 runs at the end of this section
supersede them and ran on d875e7d5, the last commit that changes product or
test code (the commit after it adds only evidence files).

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

Review-fix round, on 5d0a9cc54ae763d7171e4616b0b13e34845bf26f (the files the
fixes touch, plus the document checks; load 16.66 at start). Raw output:
`fix_round_green.txt`.

```
$ NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_lore/test_token_estimator.py tests/test_embedding_artifacts.py tests/test_model_artifact_lock_committed.py tests/test_doc_front_matter.py tests/test_cli_reference_doc.py
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 4 targets: postgres, qa640_818_estimate_*, qa640_818_pin_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
168 passed, 7 warnings in 67.57s (0:01:07)
```

`_lock_summary` on the committed lock after the fix (`lock_summary.txt`):

```
Locked 2 artifact(s) and 5 tokenizer(s) in config/model_artifacts.lock.json:
  embedder Octen-Embedding-4B: Octen/Octen-Embedding-4B @ fea468fae3f0caffbae8a12ba792d1c394b6277d (git), 2560d, 18 files, 7686.2 MiB
  reranker deberta-v3-trecdl22: naver/trecdl22-crossencoder-debertav3 @ 24f6a61d11707432d5780a1d5cf4e3af25cfaddb (huggingface), 10 files, 1662.1 MiB
  tokenizer MiniMaxAI/Minimax-M3 @ f0e1c1e04d40177e4673a22097036854f536e9c0
  tokenizer NousResearch/Hermes-4-405B @ 88e3dce03c4a5535e2f4a2bcc08e939a2b302f82
  tokenizer NousResearch/Hermes-4-70B @ d5dec2bd6b3930a09ddefd0b7fc6523fe0720d09
  tokenizer NousResearch/Hermes-4.3-36B @ 3899db2b6c4b35f16bde3b570bb7dd2775d56161
  tokenizer deepseek-ai/DeepSeek-V4-Pro @ b5968e9190ef611bbf34a7229255be88a0e937c1
```

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

Review round 2, on d875e7d5 and unchanged since (raw output with the commit id
and an `uptime` reading on the first line of each file). The first offline
suite ran in two pieces so that no command passed the ten-minute limit; the
pieces cover the same files as `tests --ignore=tests/test_api
--ignore=tests/test_orrery`.

```
$ NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_lore/test_token_estimator.py tests/test_lore/test_token_budget.py tests/test_lore/test_turn_cycle.py tests/test_embedding_artifacts.py tests/test_model_artifact_lock_committed.py tests/test_runtime/test_readiness.py tests/config tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 9 targets: postgres, qa640_816_lifecycle_test_provider, qa640_818_estimate_*, qa640_818_pin_* x2, qa640_885_ren_replay_* x4
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
323 passed, 2 skipped, 7 warnings in 124.10s (0:02:04)
```
(`round2_pg_proof.txt`; load 12.90 at start. Three more than before: the
folder test and the two lock-shape cases.)

```
$ nice -n 15 $PY -m pytest -q tests/config tests/fixtures tests/proofs tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1053 passed, 89 skipped, 7 warnings in 152.77s (0:02:32)

$ nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/config --ignore=tests/fixtures --ignore=tests/proofs --ignore=tests/test_config --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_scripts --ignore=tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
2159 passed, 589 skipped, 8 warnings in 483.75s (0:08:03)

$ nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 43.48s

$ $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py tests/test_cli_reference_doc.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
130 passed, 5 warnings in 17.22s
```
(`round2_offline_a.txt`, `round2_offline_b.txt`,
`round2_offline_api_orrery.txt`, `round2_reachability_docs.txt`. The two
pieces total 3212 passed and 678 skipped: the earlier 3209 plus the three new
tests.)

## Manual Real Fetch (One Attempt, No Retry)

`manual_fetch.py.txt` ran `fetch_tokenizers(verify_tokenizers(s,
read_manifest(lock_file_path(s))))` with network and a fresh
`HF_HOME=<scratch>/1126-S1/hf`. It did not use the CLI, whose fetch would also
re-hash the 9.8 GB embedder and reranker. Output (`manual_fetch.out.txt`,
progress bars omitted here):

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
`HF_HOME` and once from the default cache (`manual_counts.out.txt`):

```
sentence: "The quick brown fox jumps over the lazy dog; <|endoftext|> stays text."
nousresearch/hermes-4-70b: NousResearch/Hermes-4-70B @ d5dec2bd…: fresh HF_HOME 19, default cache 19, equal=True
nousresearch/hermes-4.3-36b: NousResearch/Hermes-4.3-36B @ 3899db2b…: fresh HF_HOME 20, default cache 20, equal=True
deepseek/deepseek-v4-pro: deepseek-ai/DeepSeek-V4-Pro @ b5968e91…: fresh HF_HOME 20, default cache 20, equal=True
nousresearch/hermes-4-405b: NousResearch/Hermes-4-405B @ 88e3dce0…: fresh HF_HOME 19, default cache 19, equal=True
minimax/minimax-m3: MiniMaxAI/Minimax-M3 @ f0e1c1e0…: fresh HF_HOME 19, default cache 19, equal=True
all five counts equal
```

The `du -sh` command and its output are appended to `manual_fetch.out.txt`
(re-run in the review-fix round on the same, untouched `HF_HOME`):

```
$ du -sh <scratch>/1126-S1/hf
 60M	<scratch>/1126-S1/hf
```

The fresh cache holds one snapshot per repository (listed in the same file),
with the same files as the default-cache listing above.

## Static Checks

Re-run in review round 2 on the nine changed Python files at d875e7d5,
against a `git archive origin/main` export (the `origin/main` half of each
file is unchanged from the earlier round; `origin/main` is still c7ae2988).

`black --check` passes on all nine changed Python files.

flake8 (`flake8.txt`, both commands and both outputs) gives the same 23
diagnostics on the branch and on the `origin/main` versions after normalizing
line numbers; the round-2 branch run is byte-identical to the recorded one.
They are pre-existing E501/F401 on untouched lines of `logon_utility.py`,
`settings_models.py` and `test_token_estimator.py`. There are no new
diagnostics, and none on a changed or added line.

mypy, `$PY -m mypy --explicit-package-bases <changed files>` (`mypy.txt`, both
commands and both outputs; the branch half re-run on d875e7d5): no diagnostic
on a changed or added line, and no new diagnostics. The branch run reports 28
errors in 4 files (34 before round 2). The two edited tomlkit tests now
annotate the parsed document (`settings: Any` at `test_token_estimator.py:113`,
`config: Any` at `:614`), so their edited lines carry no diagnostic. Gone on the
branch: the `sorted` type-var error in `scripts/validate_config_commit.py` and
fourteen tomlkit `Item | Container` errors in `test_token_estimator.py`. The
remaining tomlkit errors (`:81-87`, `:136-137`) sit on lines identical to
`origin/main` `:77-83` and `:128-129`; the other remaining ones are
pre-existing on untouched lines of `settings_models.py`, `prompt_window.py`
and `logon_utility.py`. The `origin/main` run was made in the export, which
follows imports into the whole tree (294 errors in 53 files); only the changed
files were compared.

Exception dispositions:

```
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

Two new marked handlers: `fetch_tokenizers` catches `(OSError,
ArtifactLockError)` and carries `# nexus-exception-disposition: fail;
reason=hub; safety=failed result`; `_verify_embedder` (review round 2) catches
`ArtifactLockError` and carries `# nexus-exception-disposition: fail;
reason=folder; safety=failed result`. The baseline is unchanged (the three
baselined `run_models_command` handlers are textually unchanged). The new handlers
in `tokenizer_cached` and `_entry_tokenizer` always raise.

## Document Freshness

AGENTS.md, `docs/turn_flow_sequence.md`, and decisions 0009, 0010, 0019, 0024
and 0034 were re-read against the changed sources. None of them makes a claim
about tokenizers. 0019's `logon_utility.py:2457-2476` is a quote of #849's
historical verdict, not a current claim. Each `verified_commit` moved to the
merge base c7ae2988d07b443f627a04d3a4eed1816b1cd438;
`tests/test_doc_front_matter.py` passes.
