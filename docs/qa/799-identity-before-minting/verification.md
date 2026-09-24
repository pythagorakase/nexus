# Identity Before Minting Verification

Work order 799, branch `claude/799-identity-before-minting`.

## Import Provenance

Run from this worktree, using the shared interpreter:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/799-identity-before-minting/nexus/__init__.py
```

## Implemented Contract

- `nexus/presence/identity.py:79`: one resolver returns resolved, ambiguous, or novel using the roster's `IdentityIndex`. Exact canonical names and unique stored aliases bind existing IDs. Case-folded collisions, shared name forms, fuzzy matches, conflicting kinds, and explicit location conflicts require review. Descriptor, role, and location evidence can narrow review candidates but cannot promote ambiguity to an automatic binding.
- `nexus/api/presence_reconciliation.py`: pre-hydration declarations use that resolver; post-insert reconciliation resolves alias declarations to their canonical IDs.
- `nexus/agents/lore/logon_utility.py`: validation runs before the provider repair delegate. `CharacterIdentityAmbiguity` inherits the terminal wire-contract exception and the existing attempt ledger retains the rejection, candidates, and review choices.
- `nexus/api/commit_handler_sync.py` and `commit_handler.py`: acceptance rechecks identity before inserting the narrative chunk. Synchronous maturation and asynchronous declaration conversion also resolve under the transaction's identity advisory lock before inserting a character.
- `nexus/agents/orrery/retrograde_persistence.py`: seeding plans use the same resolver and an alias-aware catalog; insertion rechecks under the lock. A concurrent existing binding is never classified as an inserted stub, including for death/deactivation eligibility.
- Wizard protagonist creation and trait character stubs resolve before insertion. Declaration maturation refreshes generated aliases and treats identity ambiguity as a terminal worker failure.
- Generated aliases are deterministic first-name, surname, and authored-title forms. Generation considers every character's proposed forms and canonical names plus existing aliases. Shared forms are withheld, and generated aliases made ambiguous by a later character are removed. Authored aliases are retained.

## PostgreSQL and Provider Proofs

The real acceptance proofs are in `tests/test_presence_roster_pg.py`; the wizard HTTP staging/acceptance proofs are in `tests/test_wizard_opening_presence_pg.py`. The tests verify exact canonical reuse, unique alias reuse, novel minting, repeated declarations, canonical reference IDs, and a shared surname rejected before any staging row exists.

`tests/test_orrery/test_character_identity_pg.py` exercises real Retrograde seeding, asynchronous declaration conversion, surname rejection, alias provenance and revocation, stale-plan reuse, and a place/character collision. Its terminal-rejection test uses the real OpenAI SDK against a local TEST HTTP server, PostgreSQL catalog reads, the actual provider validator and attempt ledger, and `nexus usage --run <session> --json`. With three provider repairs allowed, ambiguity makes exactly one HTTP request and produces one persisted rejection. No paid inference is used.

The full Retrograde wizard transition in `test_persistence_identity_binds_database_alias_without_packet_alias` now succeeds using the existing protagonist alias, with no alias-named duplicate. The fixture applies migration 123 only to its disposable clone.

## Save 04 Census

Source `save_04` was copied using `pg_dump --format=custom` and restored into disposable `qa640_identity799_review_census_24626cf06dc3`. The repository fixture applied migration 123 only to that clone and dropped it after the census. The source was never changed or disconnected.

[census.json](census.json) records **23 characters, zero resolved to an earlier character ID, and zero ambiguous matches**. This is a conservative name/alias census, not a claim that all semantic duplicates have been identified. The scan compares each character against earlier IDs and their stored aliases; it does not invent aliases for historical rows.

The census connection sets `readonly=True` before these queries:

```sql
SELECT id, name, entity_id, summary FROM characters ORDER BY id;
SELECT character_id, alias FROM character_aliases;
```

The reusable command is:

```sh
PYTHONPATH=$PWD $PY scripts/character_identity_census.py <qa640_clone>
```

The exact clone/census invocation was:

```python
from tests.pg_fixtures import disposable_slot_database
from scripts.character_identity_census import census
with disposable_slot_database(
    'qa640_identity799_review_census', source_db='save_04', include_data=True
) as dbname:
    result = census(dbname)
```

## Review Amendments for PR #929

- **Symmetric title normalization:** `nexus/presence/identity.py:54` applies the configured case, diacritic, and title normalization to both declared names and catalog names/aliases. Title-only equivalence remains ambiguous; it cannot authorize a binding. PostgreSQL tests cover both `Lady Ada` against `Ada` and the reverse, plus a stored `Ada` alias, through reconciliation before hydration and staging.
- **Location evidence:** character catalog reads join the `characters.current_location` place ID to its name (`nexus/presence/identity.py:211`; `nexus/api/presence_reconciliation.py:153`). The frontier comes from `continuation_setting` in the provider validator and both commit paths. `NewEntityDeclaration.scene_location` carries optional independent declaration evidence. Both locations reach the resolver; neither silently overrides the other. A different-location exact name rejects before staging; frontier evidence narrows a shared-surname candidate set without resolving it.
- **Growing batch catalog:** `nexus/presence/identity.py:170` validates against a private copy of the catalog and adds each novel declaration under a provisional negative ID. No database rows are written by validation. `Silas Wren` followed by `Silas Wrenn` fails before staging. The caller's canonical index is preserved, and read-only `asyncpg.Record` evidence is not deep-copied.
- **Terminal failure class:** `nexus/agents/orrery/retrograde_maturation.py:1596` persists `result_manifest.failure_class`, retains the required manifest schema version, and refuses requeue for `CharacterIdentityAmbiguity` even with attempts remaining. A real leased PostgreSQL job proves durable state `failed`, class `CharacterIdentityAmbiguity`, and a cleared lease nonce. Contrary to the amendment's premise, neither this branch nor fetched `origin/main` has a maturation `failure_class` column; the existing structured result manifest holds the class without an additional migration.
- **Alias provenance:** generation/revocation now uses the value `generated`; migration 123's column comment names `authored` and `generated`. Existing authored aliases remain intact.

The TEST HTTP proof now covers surname, title, location, and intra-batch ambiguity. Each case allows three repairs but makes one request and records one rejection, also read through `nexus usage --json`. Exact-name, unique-alias, and novel/idempotent mint proofs run through both real synchronous and asynchronous acceptance connections. New proofs use disposable databases; no paid inference or gateway service is used.

Fix commit `85f2fb7f` was followed by `git fetch origin` and a clean merge of `origin/main` in `c74eec9c`. The gates below run after that merge. The source import was rechecked and still resolves inside this worktree.

## Final Gates

Final post-merge command tails follow. Logs are `/tmp/nexus-799-review-offline-final.log`, `/tmp/nexus-799-review-pg-final.log`, `/tmp/nexus-799-review-reachability.log`, and `/tmp/nexus-799-review-black.log`.

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2686 passed, 883 skipped, 9 warnings in 100.49s (0:01:40)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed'
```

```text
=========================== short test summary info ============================
FAILED tests/test_orrery/test_claim_propagation_live.py::test_replay_readmits_target_participant_awareness_and_never_mints_beneficiary
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction
3 failed, 182 passed, 2 skipped, 1412 deselected, 9 warnings in 62.49s (0:01:02)
```

```sh
PYTHONPATH=$PWD $PY scripts/check_reachability.py
```

```text
  },
  "test_only": 34,
  "existing_unreachable": 85,
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "route_reachability": "not_proven"
}
```

```sh
git diff origin/main --name-only -- '*.py' | xargs /Users/pythagor/nexus/.venv/bin/python -m black --check
```

```text
All done! ✨ 🍰 ✨
24 files would be left unchanged.
```

The diagnostic commands and their verbatim tails are retained in [validation-history.md](validation-history.md).

The three PostgreSQL failures are the explicitly exempt #885 empty-slot-5 cases, verified against the current issue comments:

- `test_claim_propagation_live.py::test_replay_readmits_target_participant_awareness_and_never_mints_beneficiary`: `need-clock anchor unavailable: no canonical world time or base_timestamp`.
- `test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate`: no active faction row (`NoResultFound`).
- `test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction`: no narrative chunk ID (`int(None)`).

All new PostgreSQL proofs ran; they were not skipped. The two existing skips in the targeted selection are retained in the pytest result. Offline opt-in skips do not substitute for these PostgreSQL proofs.

## Land-Time Handoff

Migration `123_character_alias_provenance.sql` adds the documented `character_aliases.provenance` column, defaulting existing rows to `authored`. Runtime tuning is typed under `[character_identity]` in `nexus.toml`. The coordinator must apply migration 123 at land time; no fleet or template migration was performed.

The census does not merge or modify existing identities. This v1 rejects ambiguous declarations and records the review requirement; an interactive adjudication surface and applying explicit `same_as` / `create_new` / `distinct_from` rulings remain follow-on work. No gateway or worker service was started, and no application listener needs cleanup.


## Coordinator Questions

No blocking implementation questions. Migration 123 remains a coordinator land-time action. The maturation failure class is stored in the existing versioned JSON result manifest because the live repository has no dedicated class column; a later uniform jobs-status projection can expose that field if desired. No PR merge, fleet migration, live gateway start, or paid inference was performed.
