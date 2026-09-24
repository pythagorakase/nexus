# Attempt Manifest Verification

Work order 764-B; branch `claude/764-attempt-manifests`; migration **124**.
All implementation and test commands ran from this worktree using
`/Users/pythagor/nexus/.venv/bin/python`. No installation, fleet migration,
template modification, paid provider call, or merge was performed.

## PR #933 Review Amendments

Fix commit `1d5b7d29` addresses the coordinator's P2/P3 and port findings:

- `nexus/telemetry/attempt_manifest.py:77` locks the session row and copies its
  terminal outcome on insert. Later session transitions still synchronize via
  migration 124's existing trigger. `provider_outcome` remains independent.
- `tests/test_api/test_attempt_manifest_pg.py:148` discards an existing session,
  inserts its late retry, finishes the provider attempt as accepted, and asserts
  both manifests remain discarded while the retry's provider outcome is accepted.
- `nexus/agents/logon/orrery_tag_validation.py:1047` and `:1246` include the resolved
  entity kind and database ID in active-extend-expiry repair notes. The manifest
  retains those safe references and repair code alongside the original-note hash;
  names, tags, paths and free text are omitted. The inspector prints repair codes.
- The TEST turn requests port 0; `tests/scheduler_helpers.py:127` retains the bound
  listener and propagates its actual ephemeral port, avoiding a release/rebind race.
- `git fetch origin` followed by `git merge origin/main` reported
  `Already up to date.` Main was `53ac8fa2`; PR #932 was not in that fetched main.

The revised real TEST turn produced session
`14f9ee7a-5ade-48ca-b06a-0af03293f58d`, accepted chunk **51**, accepted manifests
for **gaia** and **skald_writer**, and correlated compaction job **2**. The migration
preserved **46** existing chunk IDs/text hashes. The privacy/retention fixture
pruned exactly one aged terminal manifest. No paid calls were made.

### Amendment Validation

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black nexus/telemetry/attempt_manifest.py nexus/agents/logon/orrery_tag_validation.py nexus/cli.py tests/scheduler_helpers.py tests/test_api/test_attempt_manifest_pg.py
All done! ✨ 🍰 ✨
2 files reformatted, 3 files left unchanged.

$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/telemetry/attempt_manifest.py nexus/agents/logon/orrery_tag_validation.py nexus/cli.py tests/scheduler_helpers.py tests/test_api/test_attempt_manifest_pg.py
All done! ✨ 🍰 ✨
5 files would be left unchanged.

$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_attempt_manifest_pg.py
3 passed, 9 warnings in 79.25s (0:01:19)

$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
2708 passed, 895 skipped, 9 warnings in 147.08s (0:02:27)
```

```console
$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery -k 'session or manifest or inspect or job or correlat'
FAILED tests/test_orrery/test_claim_propagation_live.py::test_null_awareness_is_possession_terminal
1 failed, 66 passed, 1917 deselected, 11 warnings in 173.23s (0:02:53)
```

Only the explicitly exempt #885 slot-5 test failed, with
`need-clock anchor unavailable: no canonical world time or base_timestamp`.
No selected PostgreSQL tests skipped. The offline gate and this PostgreSQL
selection ran after the requested fetch/merge. Both repository commit hooks passed.

The separate automated review comment about async exposure binding
([discussion](https://github.com/pythagorakase/nexus/pull/933#discussion_r4098683930))
is outside these frozen coordinator amendments and remains for coordinator triage.

## Behavior and Evidence

- `nexus/api/commit_handler_sync.py:373` and `nexus/api/commit_handler.py:604`
  set the generation UUID transaction-locally. Migration 124 uses that value
  at insertion into experience, maturation, compaction, and milestone queues;
  existing job IDs remain unchanged. Independent/legacy jobs remain nullable.
- `nexus/agents/orrery/worker.py:818` propagates the accepting session when a
  resolution is subsequently promoted into a narration job.
- `nexus/agents/lore/logon_utility.py:1915` measures ordered rendered blocks at
  the existing prompt-window guard. The manifest records system and request
  framing counts alongside renderer blocks, model registry identity, story
  pins, effective window, and configuration/schema hashes.
- `nexus/telemetry/attempt_manifest.py:46` persists a manifest only inside the
  canonical durable generation scope. Standalone diagnostics retain their
  existing JSONL telemetry without inventing durable sessions.
- `nexus/telemetry/attempt_manifest.py:152` hashes the SDK response envelope
  before validation repairs. SDK-derived parsed objects are excluded. Hashes
  use canonical UTF-8 JSON with sorted keys and compact separators. Neither
  rendered prompt nor response text is copied into the manifest.
- Validation notes retain recognized repair/rejection codes, moved/dropped
  counts, and hashes. Character names and free-text error messages are omitted.
  Provider acceptance is separate from the owning session's terminal outcome;
  a database trigger updates the latter atomically with the session decision.
- `nexus/telemetry/attempt_manifest.py:234` uses a database-enforced read-only,
  repeatable-read inspection transaction. It does not call the recovery reader
  that expires leases. `--chunk` resolves only an accepted session.
- The default tabular inspector is compact; `--json` includes complete ordered
  blocks and full hashes. Neither output includes narrative prose.
- `[usage].manifest_retention_days = 30` is validated by `UsageSettings`.
  `nexus prune-manifests --slot N` is explicit maintenance on a writable slot;
  only aged terminal manifests are removed. Generation never prunes them.
  Session truth, chunks, phase history and child jobs are retained.

## Database and TEST-Provider Proof

`tests/test_api/test_attempt_manifest_pg.py` uses real PostgreSQL and the
repository's HTTP TEST provider. The revised gateway proof binds an ephemeral port (port 0), publishes the
bound port to both gateway environment variables, and stops through the fixture
and `nexus down` with that same environment. The original proof below used 8015. Every manually selected database
prefix is `qa640_`; existing suite fixture prefixes remain unchanged.

Migration 124 was applied by the repository migration runner to populated
`qa640_764_*` clones of `save_04`. Before/after comparison of
`SELECT id, md5(raw_text) FROM narrative_chunks ORDER BY id` preserved all
**46** existing chunk IDs and text hashes. The source save was only read.

[turn-proof.json](turn-proof.json) contains reference/hash-only evidence from
the real CLI continuation and acceptance:

| Item | Observed Value |
| --- | --- |
| Generation session | `3b4d8208-2c83-425a-a7b5-fa96f8c15afc` |
| Accepted chunk | `51` |
| Seats | `gaia`, `skald_writer` |
| Model | `TEST` for both seats |
| Provider and session outcomes | `accepted` |
| Child compaction job | Job `2`, same generation session, `queued` |
| Retrieval reference | Coverage row `51` |
| Recall references | Rows `162`–`165` |

[inspect-turn.txt](inspect-turn.txt) preserves the actual compact CLI output.
The proof executes `nexus inspect-turn --slot 4 --session <uuid>` and
`nexus inspect-turn --slot 4 --chunk 51 --json`, asserting the same session
and accepted chunk. It also executes `nexus jobs --slot 4`.

A separate real enqueue proof produced experience jobs **10–19**, maturation
job **18**, and milestone version/job **216**, all with the same session UUID.
A later transaction's independent maturation job had a NULL session, proving
transaction-local attribution does not leak. Job IDs remain integers.

The retention fixture ages one terminal and one nonterminal manifest by 90
days. `nexus prune-manifests --slot 4 --json` deletes exactly **1** row; a fresh
terminal manifest and the aged nonterminal manifest remain. A second prune
returns **0**. All three session rows survive. Privacy assertions reject the
fixture's private prompt, response-error and character-name strings in every
stored manifest.

## Validation Commands

The required import proof printed:

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/764-attempt-manifests/nexus/__init__.py
```

Commands use `PY=/Users/pythagor/nexus/.venv/bin/python` and `PYTHONPATH=$PWD`.
The required PostgreSQL selection ran every selected test (no skips):

```console
$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery -k 'session or manifest or inspect or job or correlat'
FAILED tests/test_orrery/test_claim_propagation_live.py::test_null_awareness_is_possession_terminal
1 failed, 66 passed, 1917 deselected, 11 warnings in 164.49s (0:02:44)
```

The single failure is explicitly exempt under #885; there are no other failures.

```console
$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_jobs_cli_pg.py tests/test_api/test_attempt_manifest_pg.py::test_child_job_enqueue_correlation_and_transaction_reset tests/test_qa_shift.py
49 passed, 7 warnings in 7.68s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_cli_generation_http.py
32 passed in 55.59s

$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py tests/test_reentry_wire_ledger.py
60 passed, 5 warnings in 25.82s

$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_attempt_manifest_pg.py tests/test_api/test_session_truth_pg.py
6 passed, 9 warnings in 72.72s (0:01:12)
```

Black validation:

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/telemetry/attempt_manifest.py nexus/agents/lore/logon_utility.py nexus/agents/orrery/experiences.py nexus/agents/orrery/job_queues.py nexus/agents/orrery/retrograde_maturation.py nexus/agents/orrery/worker.py nexus/api/commit_handler.py nexus/api/commit_handler_sync.py nexus/api/narrative_generation.py nexus/cli.py nexus/config/settings_models.py nexus/telemetry/usage.py scripts/api_openai.py scripts/api_anthropic.py scripts/qa_shift/qa_shift.py tests/test_api/test_attempt_manifest_pg.py tests/test_jobs_cli_pg.py tests/test_orrery/test_narration_job_fencing_pg.py tests/test_prompt_lint.py tests/test_qa_shift.py
All done! ✨ 🍰 ✨
20 files would be left unchanged.
```

Implementation commit `894bda21` ran the repository hooks:

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.................................Passed
```

Final committed-source offline gate and captured PostgreSQL/TEST proof:

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
2708 passed, 895 skipped, 9 warnings in 131.89s (0:02:11)

$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_attempt_manifest_pg.py
3 passed, 9 warnings in 60.03s (0:01:00)
```

The offline skips are gated PostgreSQL/live-provider cases; the separate required
PostgreSQL selection had no skipped tests. Lane 8015 was no longer listening
after teardown, and no `qa640_764_*` database remained.


## Gate Repairs and Earlier Runs

- The first session test run found a settings-hash serialization error on
  `timedelta`; canonical Pydantic JSON conversion fixed it.
- The first offline run reported `4 failed, 2704 passed, 892 skipped`:
  two new-module reachability-ratchet failures and two pre-existing exact
  prompt-lint allowlist failures caused by docstring whitespace drift.
  The baseline now includes the new production module, and the allowlist
  matches the unchanged docstring's exact whitespace. No prompt was changed.
- A concurrent gate was interrupted to prevent two proofs claiming lane 8015.
- One offline run overlapped a transient CLI edit and reported five subprocess
  syntax failures. The corrected CLI HTTP suite subsequently passed all 32
  cases. Final gates run against stable source.
- The first full PostgreSQL selection found seven narration fixtures that
  copied an older template without pending migrations. Narration and jobs-CLI
  fixtures now apply migrations to their own disposable databases. Jobs-CLI
  expected keys also include the new nullable correlation field. The QA guard
  now validates and preserves that field instead of discarding it before its
  consistency check; its offline fixtures explicitly supply NULL correlation.
- The selected slot-5 failure is the explicitly exempt #885 ID
  `tests/test_orrery/test_claim_propagation_live.py::test_null_awareness_is_possession_terminal`.
  Its exact error is `need-clock anchor unavailable: no canonical world time or base_timestamp`.

## Deferred Work and Coordinator Questions

Embedding remains an undurable scheduler sweep. There is no embedding-job row
whose identity or correlation column can be extended; when that queue becomes
durable, it must carry this same nullable UUID. Legacy rows are not assigned
speculative session IDs, and historical phase transitions are not invented.

The coordinator must apply migration **124** fleet-wide at landing. No open
implementation question remains for this order. No merge or review-bot wait
was performed.

## Files Changed

- `config/reachability_baseline.json` — Register the new production telemetry module.
- `migrations/124_attempt_manifests.sql` — Add indexed correlation, manifests, phase history and outcome synchronization.
- `nexus.toml` — Declare explicit manifest retention days.
- `nexus/agents/lore/logon_utility.py` — Capture ordered prompt blocks and per-attempt identities.
- `nexus/agents/orrery/experiences.py` — Expose experience-job session correlation.
- `nexus/agents/orrery/job_queues.py` — Expose correlation in shared scheduler status.
- `nexus/agents/orrery/retrograde_maturation.py` — Expose maturation-job session correlation.
- `nexus/agents/orrery/worker.py` — Correlate later narration promotion with its accepted turn.
- `nexus/api/commit_handler.py` — Set transaction-local acceptance correlation.
- `nexus/api/commit_handler_sync.py` — Set acceptance correlation and bind exposure references.
- `nexus/api/narrative_generation.py` — Scope manifest writes to the durable generation owner.
- `nexus/cli.py` — Add read-only inspection, explicit pruning and job correlation output.
- `nexus/config/settings_models.py` — Validate manifest retention.
- `nexus/telemetry/attempt_manifest.py` — Persist safe metadata, hash responses, inspect and prune.
- `nexus/telemetry/usage.py` — Forward safe validation metadata to the manifest.
- `scripts/api_anthropic.py` — Record raw response hashes and attempt outcomes.
- `scripts/api_openai.py` — Record raw response hashes and attempt outcomes across supported transports.
- `scripts/qa_shift/qa_shift.py` — Validate and preserve the new job correlation field.
- `tests/test_api/test_attempt_manifest_pg.py` — Prove migration preservation, TEST turns, correlation, privacy and retention.
- `tests/test_jobs_cli_pg.py` — Migrate disposable fixtures and verify the expanded status contract.
- `tests/test_orrery/test_narration_job_fencing_pg.py` — Apply pending migrations to its existing disposable fixture.
- `tests/test_prompt_lint.py` — Align the exact allowlist with pre-existing docstring whitespace.
- `tests/test_qa_shift.py` — Supply explicit nullable correlation in existing status fixtures.
- `docs/qa/764-attempt-manifests/verification.md` — Record commands, results, evidence and deployment deferral.
- `docs/qa/764-attempt-manifests/turn-proof.json` — Preserve reference/hash-only real-turn evidence.
- `docs/qa/764-attempt-manifests/inspect-turn.txt` — Preserve the actual compact read-only CLI output.

Authored by Codex (Astra), running GPT-6 Astra.
