# PR #1121 ANN prerequisite follow-up

The initial Claude review correctly found that `--create-indexes` checked its
prerequisite only after embedding generation. Initialization could already load
a model and commit `--truncate-table` deletion. The `--chunk` helper also deleted
its old row before reaching the constructor's check.

The regenerator now checks supported dimensions before model loading, lazy
table creation, or vector deletion. A missing table also refuses, because lazy
creation cannot supply an ANN index. Dimensions above the legacy 2000d limit
retain the ordered exact-search exemption and lazy dimensional-table ownership.
The separate artifact-load guard still precedes every deletion. Temporary
engines are disposed on prerequisite/model-load refusal. The late duplicate
index check and misleading index-creation hint were removed.

Chunk and resume entry points preflight before their existing work. Resume's
ANN check is outside its legacy broad error handler so the required refusal
reaches `main` and exits 1; unrelated resume error policy is unchanged.
All-model processing retains its existing per-model failure aggregation and
continues to the next model; each refused model leaves its stored rows intact.

Only `scripts/regenerate_embeddings.py` changes production behavior in this
follow-up. One stale exception-baseline identity was removed: the model-load
exit handler now disposes its engine and explicitly declares a fail disposition.
No ANN index, owner database, model artifact, setting, service or paid API was
changed. [Exact scoped delta from the earlier integrated head](scoped-f291.patch).

## Proof

The final tested merge parent is `725011c128ab02d1468f0b2178b3c8fac27f2d6a`,
which contains frozen main `be9ce348f0f460dadf6a86aec8a505190318ed00`.
The production/test delta is the linked patch. After the final pytest run, only
the exception-disposition comment was shortened to satisfy line-length lint;
production behavior and test code did not change. All tests used the main checkout's
interpreter and this exact worktree as `PYTHONPATH`, with `nice -n 15` and the
sole shared test slot. One-minute load before final proof was 4.51 (limit 24).

```sh
nice -n 15 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_CORPUS \
  PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/810-legacy-ddl-ownership \
  NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q \
  -p tests.dbname_audit -p no:cacheprovider \
  tests/test_schema_ownership.py \
  tests/test_regenerate_embeddings_truncate_pg.py \
  tests/test_memnon_script_model_loaders.py \
  tests/test_doc_front_matter.py tests/test_reachability.py
```

[Final focused log](green.txt): **139 passed in 103.23s**, exit 0; no skips.

New cases seed real PostgreSQL vectors without an ANN index, both a single-model
table and a shared table containing a second model. Direct construction, dry-run,
chunk, resume and all-model paths must preserve all stored row columns and record
zero calls to the model loader. The real CLI `main` resume cases additionally
require exit 1 and the exact ANN error. Only model loading is a recording sentinel;
catalog queries and row snapshots are real. Two high-dimensional cases retain
lazy creation or suppress it for dry-run. Existing missing-artifact tests remain
unchanged and cover both whole-table regeneration and the chunk helper.

Before the fix, the first ten new refusal cases all failed in 29.93s
([red transcript](red.txt)). They exercised the same constructor/chunk/resume/
all-model paths and single/shared rows against the pre-fix script. The two CLI
exit cases and high-dimensional controls were added after that red run; they are
not claimed in its count. The first green attempt produced 39 passes and two
failures ([intermediate transcript](intermediate.txt)): it exposed resume's
existing catch converting the ANN error into a success-shaped zero result.
Moving only the ANN preflight outside that catch fixed the observed issue.

The final log records active secret-store denial, unchanged receipt roots and
`owner targets: none`. Disposable targets use `qa640_810s3_*` or
`qa640_regen_truncate_*`. This is process instrumentation, not an OS sandbox;
`psycopg2.extensions.ReplicationConnection` remains an unaudited connection class.
Subprocess probes receive only the fixture URL and run with Hugging Face and
Transformers offline flags. No artifact loading or inference is part of the
new ANN-refusal proof.

## Static and independent review

Black and whitespace checks pass; the exception-disposition checker passes
against `origin/main`. The changed two Python files were compared with their
pre-fix versions in a tracked Python/config snapshot of the tested merge parent.
Flake8 uses the same `.flake8`; mypy uses `--explicit-package-bases
--follow-imports=silent --no-incremental` on both sides, retaining imported type
information while limiting diagnostics to the selected files. Line numbers are
normalized for comparison. No new normalized diagnostics: flake8 reports 53 branch diagnostics versus 54 baseline diagnostics, and mypy reports
27 diagnostic lines on both sides (14 errors in the legacy script; no test errors).

[Black](black.txt), [exception check](exceptions.txt),
[static comparison metadata](static-comparison.json),
[flake8 baseline](flake8-baseline.txt), [flake8 branch](flake8-branch.txt),
[flake8 delta](flake8-delta.txt), [mypy baseline](mypy-baseline.txt),
[mypy branch](mypy-branch.txt), [mypy delta](mypy-delta.txt).

An independent Codex source review checked constructor/chunk ordering,
artifact-before-deletion behavior, engine disposal, check-only `--only-indexes`,
the >2000d exemption, all-model aggregation, and then the corrected resume
placement. It found no blocking issue. The reviewer did not run tests or load
owner data. The automated Codex review reported a usage limit; that is not
represented as a completed automated review.

The assembled nine-lane gate at `f291dc792e4b071a4cc4940101f6c40871ea8b7b`
previously passed 6984 tests, with 72 skips and 41 warnings. It predates this
review repair. This follow-up claims the focused proof above, with no new full
integration or separate whole-suite offline rerun. Owner-fleet landing remains
the coordinator's separate operation.

Codex — GPT-6
