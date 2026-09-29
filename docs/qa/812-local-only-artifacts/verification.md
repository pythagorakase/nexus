# Local-Only Model Artifacts Verification

Work order 812 (bug-fix slice), branch `claude/812-local-only-artifacts`, cut
from `origin/main` at `9a67e864`. No migration, no gateway, no paid calls.

## Import Provenance

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/nexus/__init__.py
```

## Artifact Lock

`git check-ignore -v config/model_artifacts.lock.json` printed nothing (exit 1):
the lock is not ignored.

```sh
PYTHONPATH=$PWD $PY -m nexus.cli models lock --json
```

```text
{
  "lock_file": "/Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json",
  "message": "Locked 2 artifact(s) in /Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json:\n  embedder Octen-Embedding-4B: Octen/Octen-Embedding-4B @ unknown (no Hugging Face snapshot metadata), 2560d, 18 files, 7686.2 MiB\n  reranker deberta-v3-trecdl22: naver/trecdl22-crossencoder-debertav3 @ 24f6a61d11707432d5780a1d5cf4e3af25cfaddb, 10 files, 1662.1 MiB",
  "success": true
}
```

Wall time: 4.99 s.

```sh
PYTHONPATH=$PWD $PY -m nexus.cli models verify --json
```

```text
{
  "lock_file": "/Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json",
  "message": "Model artifacts match /Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json: embedder Octen-Embedding-4B, reranker deberta-v3-trecdl22",
  "success": true
}
```

Exit code 0. Rerun after the review fixes (which removed `use_8bit` from
`nexus.toml`) with the same command: identical output, exit code 0. The
embedder folder has no Hugging Face snapshot metadata, so its
locked `revision` is `null`; the reranker's revision came from the
`hf download --local-dir` metadata.

## Grep Proofs

No reader of `target_model` remains for the MEMNON setting. The only other
`target_model` in these trees is `scripts/qa_shift`'s own unrelated config key,
excluded here, plus unrelated `target_models` and `get_target_model` names:

```sh
grep -rn "target_model" nexus scripts ir_eval/*.py ir_eval/scripts ir_eval/engine \
  tests/test_config nexus.toml --include='*.py' --include='*.toml' \
  | grep -v "scripts/qa_shift/" | grep -v "target_models\|get_target_model"
```

```text
(no output; grep exit 1)
```

Every model-loading call in `nexus/`, `scripts/`, and `ir_eval/`:

```sh
grep -rn "SentenceTransformer(\|CrossEncoder(\|from_pretrained(" nexus scripts ir_eval --include='*.py'
```

```text
nexus/agents/memnon/utils/cross_encoder.py:119:        Keyword arguments for ``CrossEncoder(path, **kwargs)``
nexus/agents/memnon/utils/cross_encoder.py:178:            self.model = CrossEncoder(
nexus/agents/memnon/utils/cross_encoder.py:563:            self.tokenizer = AutoTokenizer.from_pretrained(
nexus/agents/memnon/utils/cross_encoder.py:567:                AutoModelForCausalLM.from_pretrained(
nexus/agents/memnon/utils/embedding_manager.py:54:        Keyword arguments for ``SentenceTransformer(path, **kwargs)``
nexus/agents/memnon/utils/embedding_manager.py:87:            model = SentenceTransformer(path, **sentence_transformer_kwargs(device))
nexus/telemetry/prompt_window.py:338:    return AutoTokenizer.from_pretrained(repository, trust_remote_code=False)
```

- `embedding_manager.py:87` is the one SentenceTransformer loader
  (`get_or_load_sentence_transformer`). It passes
  `**sentence_transformer_kwargs(device)`, which always holds
  `local_files_only=True` (review finding: the rewritten alias test had
  dropped the old stub's `local_files_only` assertion). Two tests in
  `tests/test_memnon_embedding_cache.py` replace it:
  `test_every_sentence_transformer_keyword_is_accepted_and_local_only` checks
  the helper against the installed `SentenceTransformer.__init__` signature,
  and `test_the_one_loader_passes_only_the_local_only_keywords` parses
  `embedding_manager.py` and asserts its single `SentenceTransformer(...)` call
  spreads exactly that helper. Each fails when the keyword is dropped from the
  helper or the call bypasses it (both mutations checked).
- `cross_encoder.py:178` passes `**cross_encoder_kwargs(...)`, which always
  holds `local_files_only=True`. The test
  `test_every_cross_encoder_keyword_is_accepted_by_the_installed_library` checks
  it against the installed signature.
- `cross_encoder.py:563` and `:567` are the Qwen3 loads, both with
  `local_files_only=True`.
- `prompt_window.py:338` loads a chat model's tokenizer for prompt-token
  counting. It is not a retrieval artifact and is outside this slice;
  `docs/vector_embeddings.md` names it as the exception.

The `use_8bit` setting is deleted rather than refused at load (review
finding): it could only ever be false, and `true` passed validation and then
silently disabled reranking through MEMNON's reranker fallback. No reader
remains; the one hit is the comment recording why it was removed:

```sh
git grep -n "use_8bit" -- nexus scripts nexus.toml ir_eval/engine ir_eval/*.py tests/test_config
```

```text
nexus/agents/memnon/utils/cross_encoder.py:105:# ``use_8bit`` setting could therefore only ever be false and was removed.
```

`CrossEncoderReranking` is `extra="forbid"`, so a leftover `use_8bit` key now
fails validation at commit (validate-config) and boot;
`test_a_use_8bit_key_fails_config_validation` proves it. The legacy
`ir_eval/golden_queries.json` snapshot still holds the key in a plain dict
that nothing validates.

`--truncate-table` in `scripts/regenerate_embeddings.py` now runs only after
the model loads (review finding). `tests/test_regenerate_embeddings_truncate_pg.py`
points a real config's `bge-large` entry at a missing folder, runs
`EmbeddingRegenerator(truncate_table=True)` against a disposable slot holding
two stored rows, and asserts `SystemExit(1)` with both rows kept. Run against
the pre-fix script order it fails:

```text
>       assert _stored_rows(seeded_slot) == 2
E       AssertionError: assert 0 == 2
1 failed, 5 warnings in 4.00s
```

`scripts/query_narratives_vector.py` now loads only the `--model` it queries
(none for `--text-only`); `test_query_narratives_vector_loads_only_the_queried_model`
loads a tiny real model for `e5-large` while the other registered embedders
point at missing folders.

`regenerate_all_models` (`--all-models`) no longer swallows settings errors,
no longer prints "Using HuggingFace remote" for an entry without a
`local_path` (`load_local_model` rejects it), and raises
`RuntimeError("No active model in [memnon.models]")` instead of defaulting to
the unregistered `infly/inf-retriever-v1` (review finding). The `--model` help
example is now the registered `Octen-Embedding-4B`.
`test_regenerate_all_models_refuses_a_registry_with_no_active_model` proves
the raise offline.

## Gates

Offline gate, with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:cacheprovider
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory[False]
FAILED tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory[True]
FAILED tests/test_skald_wire.py::test_state_authoring_documents_share_core_invariants
3 failed, 4052 passed, 1049 skipped, 8 warnings in 312.75s (0:05:12)
```

- The two `test_database_contract` failures are a worktree artifact, not a
  regression. The test runs `python -m nexus.database` from a foreign
  directory, so the subprocess imports `nexus` through the shared venv's
  editable install, which is the main checkout
  (`/Users/pythagor/nexus/nexus/database.py` in the traceback). That older
  code still requires `hybrid_search.target_model` and
  `cross_encoder_reranking.use_8bit`, but the test reads the worktree's
  `nexus.toml`, where both keys are gone:
  `memnon.retrieval.hybrid_search.target_model Field required` and
  `memnon.retrieval.cross_encoder_reranking.use_8bit Field required`. With
  `PYTHONPATH=$PWD` the subprocess imports the worktree code, and both cases
  pass (`2 passed in 2.33s`).
- `test_skald_wire.py::test_state_authoring_documents_share_core_invariants`
  also fails on an unmodified `git archive origin/main` tree
  (`1 failed, 5 warnings in 0.87s`). The failure is in prompt text
  (`'rather than invent' in` the Gaia document), which this branch does not
  touch.

PostgreSQL MEMNON gate:

```sh
NEXUS_RUN_POSTGRES=1 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:cacheprovider tests/test_memnon
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
51 passed, 5 warnings in 29.70s
```

The changed and adjacent suites, with PostgreSQL:

```sh
NEXUS_RUN_POSTGRES=1 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:cacheprovider -rs \
  tests/test_memnon_embedding_cache.py tests/test_api/test_narrative_jobs_pg.py \
  tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_cross_encoder.py \
  tests/test_memnon_cross_encoder_dependencies.py tests/test_memnon_embedding_contract.py \
  tests/test_memnon_script_model_loaders.py tests/test_model_artifact_lock_committed.py \
  tests/test_embedding_artifacts.py tests/test_qa_shift.py tests/test_config \
  tests/test_regenerate_embeddings_truncate_pg.py
```

```text
SKIPPED [1] tests/test_memnon_cross_encoder_dependencies.py:28: Local DeBERTa cross-encoder model is not available
201 passed, 1 skipped, 8 warnings in 77.62s (0:01:17)
```

The skipped test looks for the reranker under `<checkout>/models/`, which a
worktree does not have. The skip predates this branch.

## Lint and Types

Every command runs from the worktree root with
`PY=/Users/pythagor/nexus/.venv/bin/python`, in `bash` (the loops rely on word
splitting). `FILES` is every changed Python file on the branch (24 files).

Reachability and doc front matter:

```sh
$PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
67 passed in 9.79s
```

The truncate test's dynamic import of `scripts/regenerate_embeddings.py` is
declared in `config/reachability.toml`. That script and
`scripts/utils/embedding_utils.py` leave the orphan baseline only because the
test imports them; neither gained an operator entry point.
`scripts/import_narratives.py` and `scripts/query_narratives_vector.py` stay
orphan-baselined. #811's quarantine triage should treat all four as
import-era tooling, not operator tools.

Black:

```sh
FILES=$(git diff --name-only origin/main...HEAD -- "*.py")
$PY -m black --check $FILES
```

```text
All done! ✨ 🍰 ✨
24 files would be left unchanged.
```

flake8, per file, against the same file on `origin/main`:

```sh
for f in $FILES; do
  n=$($PY -m flake8 "$f" | wc -l | tr -d " ")
  if git cat-file -e origin/main:"$f" 2>/dev/null; then
    m=$(git show origin/main:"$f" | $PY -m flake8 --stdin-display-name="$f" - | wc -l | tr -d " ")
  else m=new; fi
  echo "$f branch=$n main=$m"
done
```

```text
ir_eval/engine/run_executor.py branch=3 main=3
ir_eval/ir_eval.py branch=70 main=70
ir_eval/ir_eval_sqlite.py branch=50 main=50
ir_eval/scripts/display.py branch=11 main=11
ir_eval/scripts/golden_queries_module.py branch=16 main=16
ir_eval/scripts/settings_compare.py branch=17 main=17
nexus/agents/memnon/memnon.py branch=68 main=68
nexus/agents/memnon/utils/alias_search.py branch=10 main=10
nexus/agents/memnon/utils/cross_encoder.py branch=1 main=1
nexus/agents/memnon/utils/embedding_manager.py branch=0 main=0
nexus/config/settings_models.py branch=6 main=6
nexus/jobs/embeddings.py branch=2 main=2
scripts/import_narratives.py branch=9 main=13
scripts/query_narratives_vector.py branch=18 main=22
scripts/regenerate_embeddings.py branch=68 main=75
scripts/run_golden_queries.py branch=10 main=10
tests/test_api/test_narrative_jobs_pg.py branch=12 main=12
tests/test_memnon_cross_encoder_artifact.py branch=0 main=0
tests/test_memnon_embedding_cache.py branch=1 main=1
tests/test_memnon_script_model_loaders.py branch=0 main=new
tests/test_model_artifact_lock_committed.py branch=0 main=new
tests/test_qa_shift.py branch=0 main=0
tests/test_regenerate_embeddings_truncate_pg.py branch=0 main=new
tests/tiny_models.py branch=0 main=new
```

No file gains a flake8 finding; the three scripts lose some. The one finding
in `tests/test_memnon_embedding_cache.py` (F401 `sqlalchemy_url`) is on
`origin/main` too.

mypy on the changed `nexus/` and `tests/` files (14). Without
`--explicit-package-bases` mypy stops at "Source file found twice" for
`tests/tiny_models.py` (`tests/` has no `__init__.py`), and without
`--ignore-missing-imports` it stops at the missing `requests` stubs in
`memnon.py`, so both flags are used on the branch and on `origin/main`:

```sh
FILES=$(git diff --name-only origin/main...HEAD -- "nexus/*.py" "tests/*.py")
PYTHONPATH=$PWD $PY -m mypy --explicit-package-bases --ignore-missing-imports $FILES
```

```text
Found 55 errors in 6 files (checked 14 source files)
```

The 10 of those files that exist on `origin/main`, checked in an extracted
`git archive origin/main` tree and then on the branch:

```sh
MAIN=$(mktemp -d); git archive origin/main | tar -x -C "$MAIN"
MAINFILES=$(for f in $FILES; do [ -f "$MAIN/$f" ] && echo "$f"; done)
(cd "$MAIN" && PYTHONPATH=$PWD $PY -m mypy --explicit-package-bases --ignore-missing-imports $MAINFILES)
PYTHONPATH=$PWD $PY -m mypy --explicit-package-bases --ignore-missing-imports $MAINFILES
```

```text
Found 57 errors in 7 files (checked 10 source files)
Found 55 errors in 6 files (checked 10 source files)
```

Per file (`grep error: | cut -d: -f1 | sort | uniq -c`), branch then
`origin/main`:

```text
  36 nexus/agents/memnon/memnon.py
   2 nexus/agents/memnon/utils/alias_search.py
   7 nexus/config/settings_models.py
   1 tests/test_api/test_narrative_jobs_pg.py
   7 tests/test_memnon_embedding_cache.py
   2 tests/test_qa_shift.py
main
  36 nexus/agents/memnon/memnon.py
   2 nexus/agents/memnon/utils/alias_search.py
   2 nexus/agents/memnon/utils/cross_encoder.py
   7 nexus/config/settings_models.py
   1 tests/test_api/test_narrative_jobs_pg.py
   7 tests/test_memnon_embedding_cache.py
   2 tests/test_qa_shift.py
```

The four new test files add no errors (55 on 14 files equals 55 on the 10
files that also exist on `origin/main`), and the branch clears the two
`cross_encoder.py` errors. Every remaining file count matches what `origin/main`
already reports.

## Review Round Three Gates

Three review findings: the orphan-baseline wording, `regenerate_all_models`'s
Hub-era default, and the lost `local_files_only` assertion for the embedder.
With `PY=/Users/pythagor/nexus/.venv/bin/python`:

```sh
NEXUS_RUN_POSTGRES=1 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:cacheprovider \
  tests/test_memnon_embedding_cache.py tests/test_memnon_script_model_loaders.py \
  tests/test_regenerate_embeddings_truncate_pg.py tests/test_reachability.py \
  tests/test_doc_front_matter.py tests/test_memnon_cross_encoder_artifact.py \
  tests/test_embedding_artifacts.py tests/test_memnon_embedding_contract.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
119 passed, 6 warnings in 47.57s
```

Black, flake8 (branch vs the previous branch head), and mypy on the four
changed Python files:

```text
All done! ✨ 🍰 ✨
4 files would be left unchanged.
nexus/agents/memnon/utils/embedding_manager.py branch=0 head=0
scripts/regenerate_embeddings.py branch=68 head=70
tests/test_memnon_embedding_cache.py branch=1 head=1
tests/test_memnon_script_model_loaders.py branch=0 head=0
mypy (embedding_manager.py and both test files), branch: Found 7 errors in 1 file (checked 3 source files)
mypy, previous branch head: Found 7 errors in 1 file (checked 3 source files)
```

## Codex P1: Stale Golden-Query Overrides

The review bot flagged `ir_eval/golden_queries.json`: `create_temp_settings_file`
(`ir_eval/ir_eval.py:101`) merges its `settings` block into the control MEMNON
settings, and the `extra="forbid"` models reject `hybrid_search.target_model`,
which this PR retired. The same block also carried
`cross_encoder_reranking.use_8bit`, retired here too. Both keys are gone from
`ir_eval/golden_queries.json` and its tracked twin
`ir_eval/golden_queries.json.bak`; `target_model` is gone from
`ir_eval/golden_queries_backup.json`, which has no reranking block. The
`ir_eval/results/*.json` files and the run rows in `ir_eval/ir_eval.db` are
historical outputs and stay as recorded.

`tests/test_config/test_ir_eval_golden_overrides.py` runs the CLI's own
`reload_settings` and `create_temp_settings_file` in a fresh interpreter,
because `ir_eval/__init__.py` binds the root `scripts` package and the CLI's
`from scripts.auto_judge import AIJudge` then raises `ModuleNotFoundError`. The
temporary document lands in `tmp_path` through `TMPDIR`, and the test validates
the merged MEMNON section with `Settings` inside canonical `nexus.toml`,
asserting no field-level error. It does not assert full validation, because two
failures predate this PR and reproduce on a `git archive origin/main` tree
(`626b2293`):

- `load_settings_as_dict(<merged>.json)` fails with `nexus.toml is missing
  required [storyteller.correspondence] section`. The legacy JSON loader never
  maps that section, so no legacy document validates.
- `Settings` with the merged MEMNON fails with `[memnon.models] must mark
  exactly one embedder is_active = true (the production embedder); 4 are
  active`. The golden `models` block is a three-embedder ensemble, and the
  invariant arrived with `c7359174`.

On that `origin/main` tree the merge has no field-level error. With this
branch's schema and the unedited golden file, the test fails:

```text
memnon.retrieval.hybrid_search.target_model
  Extra inputs are not permitted [type=extra_forbidden, input_value='inf-retriever-v1-1.5b', input_type=str]
memnon.retrieval.cross_encoder_reranking.use_8bit
  Extra inputs are not permitted [type=extra_forbidden, input_value=True, input_type=bool]
1 failed, 5 warnings in 0.96s
```

The test's file-based load is a test-only dynamic edge in
`config/reachability.toml`, and the ratchet retired the five orphan exemptions
it reaches: `ir_eval/ir_eval.py` and `ir_eval/scripts/auto_judge.py`,
`golden_queries_module.py`, `pg_qrels.py`, and `settings_compare.py`.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_config/test_ir_eval_golden_overrides.py
PYTHONPATH=$PWD $PY -m pytest -q tests/test_config tests/test_qa_shift.py tests/test_reachability.py
$PY -m black --check tests/test_config/test_ir_eval_golden_overrides.py
$PY -m flake8 tests/test_config/test_ir_eval_golden_overrides.py
PYTHONPATH=$PWD $PY -m mypy tests/test_config/test_ir_eval_golden_overrides.py
```

```text
1 passed, 5 warnings in 0.95s
167 passed, 5 warnings in 19.95s
1 file would be left unchanged.
(flake8: no output, exit 0)
Success: no issues found in 1 source file
```

## Astra Review Fixes

The independent review of `fbfa976a` returned three findings, fixed in
`a8f5b81a` (P1), `e221ea54` (P2, lock revision) and `6179c610` (P2, embedding
job); `361697ff` tidies one new test. Every command runs from the worktree
root with `PY=/Users/pythagor/nexus/.venv/bin/python` and `PYTHONPATH=$PWD`,
with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset.

### P1: `--chunk` Deleted the Row Before Loading the Model

`regenerate_specific_chunk()` now calls `ModelLoader.load_model()` before
`delete_existing_chunk_embedding()` commits; the regenerator that embeds the
chunk reuses the process-cached model (the second load logs `Reusing
process-cached SentenceTransformer` and returns the same instance). Every other
deleting path already loads first: `--truncate-table` and the full `--model`
and `--all-models` regeneration delete only after `EmbeddingRegenerator`
loads, `--resume-from` only upserts, and `--only-indexes` builds its
regenerator without the table step, so it never reaches the truncate branch.

`tests/test_regenerate_embeddings_truncate_pg.py::test_chunk_keeps_its_row_when_the_model_artifact_is_missing`
runs `scripts/regenerate_embeddings.py --model bge-large --chunk <id> --db-url
<disposable slot>` in its own interpreter with `HF_HUB_OFFLINE=1` and a
registry whose `local_path` is missing. Against the unfixed script it failed
on the data loss, and the script's log showed the order:

```text
nexus.embeddings - INFO - Deleted existing bge-large embedding for chunk 1
nexus.embeddings - INFO - Loading model: bge-large
nexus.embeddings - ERROR - Failed to load bge-large model: Embedding model 'bge-large' is not installed: ...
E       assert [2] == [1, 2]
1 failed, 5 warnings in 4.49s
```

With the fix the row survives, the script exits 1, and stdout carries:

```text
Error: Embedding model 'bge-large' is not installed: local_path <missing> does not exist. Restore it with `hf download BAAI/bge-large-en --local-dir <missing>`, then run `nexus models verify`.
```

### P2: The Lock Omitted the Checkout's Git Revision

`git -C /Users/pythagor/nexus/models/Octen-Embedding-4B rev-parse HEAD`
prints `fea468fae3f0caffbae8a12ba792d1c394b6277d`; the checkout tracks exactly
the 18 locked files and its `origin` is `https://huggingface.co/Octen/Octen-Embedding-4B`.

`artifact_revision()` in `nexus/agents/memnon/utils/artifact_manifest.py`
reads two sources, and the lock names the one used in `revision_source`:
`huggingface` (the existing Hub-cache snapshot and `hf download --local-dir`
metadata) and `git` (HEAD of a `.git` directory or `.git` file in the artifact
folder itself). Git runs as `git --git-dir=<root>/.git rev-parse --verify HEAD`
without `GIT_*` variables. A scratch probe showed why: `git -C <folder>` with
an invalid nested `.git` printed the enclosing repository's HEAD, and an
exported `GIT_DIR` redirected `-C` to another repository, while `--git-dir`
failed loudly (`fatal: not a git repository`) and read a `.git` file
correctly. The two sources disagreeing is an error. `verify` now reports a
folder whose recorded revision differs from the lock, and every `hf download`
command (lock, verify, the embedder loader, both rerankers, and through them
the scripts and the embedding job) pins `--revision` from the lock, else from
the folder. The loaders build that command only after a load fails.

`models verify --json` against the previous lock (`revision: null`), before
relocking:

```text
{
  "code": "domain_failure",
  "error": "Model artifacts do not match /Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json:\n  - embedder 'Octen-Embedding-4B': git revision 'fea468fae3f0caffbae8a12ba792d1c394b6277d' differs from the locked None\nRemediation:\n  - Restore embedder 'Octen-Embedding-4B' from `hf download Octen/Octen-Embedding-4B --revision fea468fae3f0caffbae8a12ba792d1c394b6277d --local-dir /Users/pythagor/nexus/models/Octen-Embedding-4B`, then re-run `nexus models verify`.\n  - If a changed artifact is an intentional upgrade, re-run `nexus models lock` on the host that holds it and commit the lock.",
  "ok": false,
  "partial": {
    "lock_file": "/Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json",
    "problems": [
      "embedder 'Octen-Embedding-4B': git revision 'fea468fae3f0caffbae8a12ba792d1c394b6277d' differs from the locked None"
    ]
  }
}
exit=1
```

```sh
PYTHONPATH=$PWD $PY -m nexus.cli models lock --json
PYTHONPATH=$PWD $PY -m nexus.cli models verify --json
```

```text
{
  "lock_file": "/Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json",
  "message": "Locked 2 artifact(s) in /Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json:\n  embedder Octen-Embedding-4B: Octen/Octen-Embedding-4B @ fea468fae3f0caffbae8a12ba792d1c394b6277d (git), 2560d, 18 files, 7686.2 MiB\n  reranker deberta-v3-trecdl22: naver/trecdl22-crossencoder-debertav3 @ 24f6a61d11707432d5780a1d5cf4e3af25cfaddb (huggingface), 10 files, 1662.1 MiB",
  "success": true
}
exit=0
lock wall 4.26s
{
  "lock_file": "/Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json",
  "message": "Model artifacts match /Users/pythagor/nexus/.claude/worktrees/812-local-only-artifacts/config/model_artifacts.lock.json: embedder Octen-Embedding-4B, reranker deberta-v3-trecdl22",
  "success": true
}
exit=0
verify wall 4.25s
```

Rerun at `361697ff`: the same `models verify --json` output, exit code 0.

The regenerated lock differs from the previous one only in the revision
fields; every file entry is unchanged:

```text
-      "revision": null,
+      "revision": "fea468fae3f0caffbae8a12ba792d1c394b6277d",
+      "revision_source": "git",
...
       "revision": "24f6a61d11707432d5780a1d5cf4e3af25cfaddb",
+      "revision_source": "huggingface",
```

`tests/test_embedding_artifacts.py` adds a real `git init` and commit in
`tmp_path` for a `.git` directory and a `.git` file, the enclosing-repository
guard, verify catching a moved checkout with the pinned restore, the `lock`
command's missing-folder restore pinned to the lock it replaces, and the
embedder and reranker loader remedies pinned from the lock and from a
half-copied checkout. `tests/test_model_artifact_lock_committed.py` requires a
revision and a known `revision_source` for every locked artifact that restores
from a repository. The two LORE startup tests that named the production
embedder's restore command now expect `--revision` from the committed lock.

### P2: The Embedding Job Omitted the Restore Command

`drain_embedding()` (`nexus/jobs/embeddings.py`), which the Orrery worker
reaches through `SlotScheduler.run_pass()`, now loads through
`load_local_model()` instead of its own folder check and
`get_or_load_sentence_transformer()`. The job keeps the same process-cache
entry, because the cache key is the resolved path.
`tests/test_api/test_narrative_jobs_pg.py::test_embedding_job_names_the_embedder_restore_command`
queues a job on a disposable slot, points the active embedder at a missing
folder or an empty one, sets `HF_HUB_OFFLINE=1`, and runs `run_pass()`.
Against the unfixed loader:

```text
E           ValueError: Configured embedding model Octen-Embedding-4B is not installed at /private/var/folders/.../test_embedding_job_names_the_e0/embedder
E       ValueError: Unrecognized model in /private/var/folders/.../test_embedding_job_names_the_e1/embedder. Should have a `model_type` key in its config.json, ...
2 failed, 7 warnings in 6.10s
```

With the fix, `run_pass()` raises the loader's error, which ends:

```text
Restore it with `hf download Octen/Octen-Embedding-4B --revision fea468fae3f0caffbae8a12ba792d1c394b6277d --local-dir <folder>`, then run `nexus models verify`.
```

The job is `failed` with that message as its `last_error`, and the chunk
stays unembedded.

### Gates

At `361697ff`, the touched test modules and the named adjacent ones, with
PostgreSQL:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider -rs \
  tests/test_regenerate_embeddings_truncate_pg.py tests/test_embedding_artifacts.py \
  tests/test_api/test_narrative_jobs_pg.py tests/test_model_artifact_lock_committed.py \
  tests/test_memnon_embedding_contract.py tests/test_lore/test_runtime_config.py \
  tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_script_model_loaders.py \
  tests/test_memnon_embedding_cache.py tests/test_reachability.py tests/test_doc_front_matter.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
146 passed, 8 warnings in 103.61s (0:01:43)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider -rs \
  tests/test_regenerate_embeddings_truncate_pg.py tests/test_memnon
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
53 passed, 5 warnings in 35.09s
```

The full offline suite ran at `6179c610`; the later `361697ff` changes only
`tests/test_embedding_artifacts.py`, which the first gate above runs.
`PYTHONPATH=$PWD` makes the subprocesses import the worktree rather than the
main checkout's editable install:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider
```

```text
FAILED tests/test_skald_wire.py::test_state_authoring_documents_share_core_invariants
1 failed, 4065 passed, 1052 skipped, 8 warnings in 307.17s (0:05:07)
```

The one failure is the Gaia prompt assertion (`assert 'rather than invent'
in "## Gaia You are Gaia. ..."`) recorded under Gates above as failing on an
unmodified `origin/main` tree at this branch's base; `e124bd54` (#1011) fixed
it on `main` after the branch was cut. The two `test_database_contract`
worktree failures recorded there do not recur, because `PYTHONPATH=$PWD`
reaches the subprocesses.

Black, flake8 per file against `16f3b38f` (the head the review fixes start
from), and mypy on the same 11 changed Python files, in `bash`:

```sh
FILES=$(git diff --name-only 16f3b38f..HEAD -- "*.py")
$PY -m black --check $FILES
for f in $FILES; do
  n=$($PY -m flake8 "$f" | wc -l | tr -d " ")
  m=$(git show 16f3b38f:"$f" | $PY -m flake8 --stdin-display-name="$f" - | wc -l | tr -d " ")
  echo "$f branch=$n before=$m"
done
PYTHONPATH=$PWD $PY -m mypy --explicit-package-bases --ignore-missing-imports $FILES
```

```text
All done! ✨ 🍰 ✨
11 files would be left unchanged.
nexus/agents/memnon/utils/artifact_manifest.py branch=0 before=0
nexus/agents/memnon/utils/cross_encoder.py branch=1 before=1
nexus/agents/memnon/utils/embedding_manager.py branch=0 before=0
nexus/jobs/embeddings.py branch=2 before=2
scripts/regenerate_embeddings.py branch=68 before=68
tests/test_api/test_narrative_jobs_pg.py branch=12 before=12
tests/test_embedding_artifacts.py branch=0 before=0
tests/test_lore/test_runtime_config.py branch=0 before=0
tests/test_memnon_embedding_contract.py branch=0 before=0
tests/test_model_artifact_lock_committed.py branch=0 before=0
tests/test_regenerate_embeddings_truncate_pg.py branch=0 before=0
Found 20 errors in 3 files (checked 11 source files)
```

The same mypy run on an extracted `git archive 16f3b38f` tree also reports
`Found 20 errors in 3 files (checked 11 source files)`, with identical
per-file counts (12 in `scripts/regenerate_embeddings.py`, 7 in
`tests/test_lore/test_runtime_config.py`, 1 in
`tests/test_api/test_narrative_jobs_pg.py`); none is on a changed line.
