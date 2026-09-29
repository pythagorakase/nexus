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

Exit code 0. The embedder folder has no Hugging Face snapshot metadata, so its
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
nexus/agents/memnon/utils/embedding_manager.py:71:            model = SentenceTransformer(path, device=device, local_files_only=True)
nexus/agents/memnon/utils/cross_encoder.py:125:        Keyword arguments for ``CrossEncoder(path, **kwargs)``
nexus/agents/memnon/utils/cross_encoder.py:189:            self.model = CrossEncoder(
nexus/agents/memnon/utils/cross_encoder.py:574:            self.tokenizer = AutoTokenizer.from_pretrained(
nexus/agents/memnon/utils/cross_encoder.py:578:                AutoModelForCausalLM.from_pretrained(
nexus/telemetry/prompt_window.py:338:    return AutoTokenizer.from_pretrained(repository, trust_remote_code=False)
```

- `embedding_manager.py:71` is the one SentenceTransformer loader
  (`get_or_load_sentence_transformer`), and it passes `local_files_only=True`.
- `cross_encoder.py:189` passes `**cross_encoder_kwargs(...)`, which always
  holds `local_files_only=True`. The test
  `test_every_cross_encoder_keyword_is_accepted_by_the_installed_library` checks
  it against the installed signature.
- `cross_encoder.py:574` and `:578` are the Qwen3 loads, both with
  `local_files_only=True`.
- `prompt_window.py:338` loads a chat model's tokenizer for prompt-token
  counting. It is not a retrieval artifact and is outside this slice.

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
3 failed, 4050 passed, 1048 skipped, 8 warnings in 325.51s (0:05:25)
```

- The two `test_database_contract` failures are a worktree artifact, not a
  regression. The test runs `python -m nexus.database` from a foreign
  directory, so the subprocess imports `nexus` through the shared venv's
  editable install, which is the main checkout
  (`/Users/pythagor/nexus/nexus/database.py` in the traceback). That older
  code still requires `hybrid_search.target_model`, but the test reads the
  worktree's `nexus.toml`, where the key is gone:
  `memnon.retrieval.hybrid_search.target_model Field required`. With
  `PYTHONPATH=$PWD` the subprocess imports the worktree code, and both cases
  pass (`2 passed in 2.47s`).
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
51 passed, 5 warnings in 32.69s
```

The changed and adjacent suites, with PostgreSQL:

```sh
NEXUS_RUN_POSTGRES=1 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:cacheprovider -rs \
  tests/test_memnon_embedding_cache.py tests/test_api/test_narrative_jobs_pg.py \
  tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_cross_encoder.py \
  tests/test_memnon_cross_encoder_dependencies.py tests/test_memnon_embedding_contract.py \
  tests/test_memnon_script_model_loaders.py tests/test_model_artifact_lock_committed.py \
  tests/test_embedding_artifacts.py tests/test_qa_shift.py tests/test_config
```

```text
SKIPPED [1] tests/test_memnon_cross_encoder_dependencies.py:28: Local DeBERTa cross-encoder model is not available
198 passed, 1 skipped, 8 warnings in 77.33s (0:01:17)
```

The skipped test looks for the reranker under `<checkout>/models/`, which a
worktree does not have. The skip predates this branch.
